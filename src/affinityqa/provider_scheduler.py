"""Private SQLite quota reservations. No network, sleeping, retries or clock reset guesses.

Rolling windows are deliberately conservative. Published defaults are planning
bounds, not evidence of actual account capacity; deployment must observe the account.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import timezone
from email.utils import parsedate_to_datetime
import json
import math
from pathlib import Path
import re
import sqlite3
import time

from .evidence import fingerprint


class ProviderDeferred(RuntimeError):
    def __init__(self, provider, next_eligible_at, reason, stage=None):
        self.provider, self.next_eligible_at = provider, next_eligible_at
        self.reason, self.stage = reason, stage
        super().__init__(f'{provider}: waiting for provider capacity ({reason}).')


class ProviderUncertain(RuntimeError):
    def __init__(self, provider, stage):
        self.provider, self.stage = provider, stage
        super().__init__(f'{provider}: a sent attempt has no accepted receipt; it will not be resent.')


class ProviderRequestTooLarge(RuntimeError):
    def __init__(self, provider, window, required, capacity):
        self.provider, self.window, self.required, self.capacity = provider, window, required, capacity
        super().__init__(f'{provider}: request needs {required} {window}; window capacity is {capacity}. No request sent.')


class ProviderRecordedFailure(RuntimeError):
    def __init__(self, provider, stage, status=None):
        self.provider, self.stage, self.status = provider, stage, status
        super().__init__(f'{provider}: recorded attempt failed' + (f' (HTTP{status})' if status else '') + '; no automatic retry.')


class ProviderAdmissionPaused(RuntimeError):
    """A durable safety fence; time or a process restart cannot clear it."""
    def __init__(self, provider, reason):
        self.provider, self.reason = provider, reason
        super().__init__(f'{provider}: admissions paused for owner review ({reason}). No new request sent.')


@dataclass(frozen=True)
class QuotaWindow:
    name: str
    capacity: int
    seconds: float
    metric: str = 'requests'
    basis: str = 'conservative'

    def __post_init__(self):
        if (not re.fullmatch(r'[a-z][a-z0-9_-]{0,63}', self.name)
                or type(self.capacity) is not int or not 1 <= self.capacity <= 2**63-1
                or type(self.seconds) not in (int, float) or not math.isfinite(self.seconds) or self.seconds <= 0
                or self.metric not in ('requests', 'tokens', 'input_tokens', 'output_tokens')
                or self.basis not in ('conservative', 'observed')):
            raise ValueError('Invalid explicit provider quota window.')


GROQ_FREE_CONSERVATIVE = (
    QuotaWindow('rpm', 30, 60), QuotaWindow('rpd', 1000, 86400),
    QuotaWindow('tpm', 8000, 60, 'tokens'), QuotaWindow('tpd', 200000, 86400, 'tokens'),
)


def _number(value):
    if isinstance(value, str) and re.fullmatch(r'[0-9]{1,19}', value.strip()):
        number = int(value)
        if number <= 2**63-1:
            return number
    return None


def _duration(value):
    """Groq's reset duration, never an inferred Unix time or midnight."""
    if not isinstance(value, str) or len(value) > 100:
        return None
    value = value.strip()
    if re.fullmatch(r'[0-9]+(?:\.[0-9]+)?', value):
        seconds = float(value)
    else:
        parts = re.findall(r'([0-9]+(?:\.[0-9]+)?)(ms|s|m|h|d)', value)
        if not parts or ''.join(n + unit for n, unit in parts) != value:
            return None
        scale = {'ms': .001, 's': 1, 'm': 60, 'h': 3600, 'd': 86400}
        seconds = sum(float(n) * scale[unit] for n, unit in parts)
    return seconds if math.isfinite(seconds) and 0 <= seconds <= 366 * 86400 else None


def safe_quota_metadata(headers, *, now=None):
    """Closed numeric allowlist: auth, request IDs and arbitrary strings are absent."""
    now = time.time() if now is None else now
    result = {}
    for key, value in (headers or {}).items():
        key = str(key).lower()
        if key in ('x-ratelimit-limit-requests', 'x-ratelimit-remaining-requests',
                   'x-ratelimit-limit-tokens', 'x-ratelimit-remaining-tokens',
                   'x-ratelimit-limit', 'x-ratelimit-remaining', 'ratelimit-limit', 'ratelimit-remaining'):
            number = _number(value)
            if number is not None:
                result[key] = number
        elif key in ('x-ratelimit-reset-requests', 'x-ratelimit-reset-tokens',
                     'x-ratelimit-reset', 'ratelimit-reset'):
            seconds = _duration(value)
            if seconds is not None:
                result[key + '-seconds'] = seconds
        elif key == 'retry-after':
            seconds = _duration(value)
            if seconds is None and isinstance(value, str) and len(value) <= 100:
                try:
                    date = parsedate_to_datetime(value)
                    if date.tzinfo is None:
                        date = date.replace(tzinfo=timezone.utc)
                    seconds = date.timestamp() - now
                except (ValueError, TypeError, OverflowError):
                    pass
            if seconds is not None and math.isfinite(seconds) and 0 <= seconds <= 366 * 86400:
                result['retry-after-seconds'] = seconds
    return result


class ProviderScheduler:
    def __init__(self, db_path, *, limits, clock=time.time):
        self.path, self.clock = Path(db_path), clock
        self.limits = {name: tuple(windows) for name, windows in limits.items()}
        if not self.limits or any(not windows or len({w.name for w in windows}) != len(windows)
                                  for windows in self.limits.values()):
            raise ValueError('Every provider requires explicit distinct quota windows.')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        configuration = {p: [asdict(w) for w in ws] for p, ws in self.limits.items()}
        with self._transaction() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS configuration (id INTEGER PRIMARY KEY, sha TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS operations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, owner TEXT NOT NULL, job TEXT NOT NULL,
                    stage TEXT NOT NULL, provider TEXT NOT NULL, request_sha TEXT NOT NULL,
                    state TEXT NOT NULL, created REAL NOT NULL, reserved REAL, sent REAL,
                    tokens INTEGER NOT NULL, input_tokens INTEGER NOT NULL, output_tokens INTEGER NOT NULL,
                    next_at REAL NOT NULL DEFAULT 0, reason TEXT, status INTEGER, result TEXT,
                    metadata TEXT NOT NULL DEFAULT '{}', UNIQUE(owner, job, stage, provider));
                CREATE INDEX IF NOT EXISTS quota_operations ON operations(provider,reserved);
                CREATE TABLE IF NOT EXISTS observations (
                    provider TEXT NOT NULL, name TEXT NOT NULL, capacity INTEGER, remaining INTEGER,
                    expires REAL NOT NULL, PRIMARY KEY(provider,name));
                CREATE TABLE IF NOT EXISTS cooldowns (provider TEXT PRIMARY KEY, until_at REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS receipts (id INTEGER PRIMARY KEY AUTOINCREMENT,
                    owner TEXT NOT NULL, job TEXT NOT NULL, provider TEXT NOT NULL,
                    mode TEXT NOT NULL, recorded REAL NOT NULL, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS provider_pauses (
                    provider TEXT PRIMARY KEY, created REAL NOT NULL,
                    reason TEXT NOT NULL, binding TEXT NOT NULL, pause_sha TEXT NOT NULL);
            ''')
            sha = fingerprint(configuration)
            existing = db.execute('SELECT sha FROM configuration WHERE id=1').fetchone()
            if existing and existing['sha'] != sha:
                raise ValueError('Persisted quota configuration differs; explicit reviewed migration required.')
            db.execute('INSERT OR IGNORE INTO configuration VALUES(1,?)', (sha,))

    @contextmanager
    def _transaction(self):
        db = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            db.execute('PRAGMA busy_timeout=15000')
            db.execute('PRAGMA synchronous=FULL')
            db.execute('BEGIN IMMEDIATE')
            yield db
            if db.in_transaction:
                db.commit()
        except BaseException:
            if db.in_transaction:
                db.rollback()
            raise
        finally:
            db.close()

    def lookup(self, *, job_id, owner_id, stage, provider, request_sha256):
        with self._transaction() as db:
            row = db.execute('SELECT * FROM operations WHERE owner=? AND job=? AND stage=? AND provider=?',
                             (owner_id, job_id, stage, provider)).fetchone()
        if row and row['request_sha'] != request_sha256:
            raise RuntimeError('Exact provider reconstruction request differs; no request sent.')
        result = dict(row) if row else None
        if result and result['result'] is not None:
            result['result'] = json.loads(result['result'])
        return result

    def _eligibility(self, db, provider, costs, now, *, exclude_id=0, observed_remaining=True):
        pause = db.execute('SELECT reason FROM provider_pauses WHERE provider=?', (provider,)).fetchone()
        if pause:
            raise ProviderAdmissionPaused(provider, pause['reason'])
        eligible, reasons = now, []
        cooldown = db.execute('SELECT until_at FROM cooldowns WHERE provider=?', (provider,)).fetchone()
        if cooldown and cooldown['until_at'] > now:
            eligible, reasons = cooldown['until_at'], ['provider-reset']
        for window in self.limits[provider]:
            observed = db.execute('SELECT * FROM observations WHERE provider=? AND name=?',
                                  (provider, window.name)).fetchone()
            capacity = min(window.capacity, observed['capacity']) if observed and observed['capacity'] else window.capacity
            required = costs[window.metric]
            if required > capacity:
                raise ProviderRequestTooLarge(provider, window.name, required, capacity)
            rows = db.execute('''SELECT reserved, tokens, input_tokens, output_tokens FROM operations
                WHERE provider=? AND reserved>? AND state IN ('RESERVED','SENT','ACCEPTED','FAILED','UNKNOWN')
                AND id!=? ORDER BY reserved,id''', (provider, now-window.seconds, exclude_id)).fetchall()
            used = sum(1 if window.metric == 'requests' else row[window.metric] for row in rows)
            excess = used + required - capacity
            if excess > 0:
                for row in rows:
                    excess -= 1 if window.metric == 'requests' else row[window.metric]
                    if excess <= 0:
                        eligible = max(eligible, row['reserved'] + window.seconds)
                        reasons.append(window.name)
                        break
            if observed_remaining and observed and observed['expires'] > now and observed['remaining'] is not None and required > observed['remaining']:
                eligible = max(eligible, observed['expires'])
                reasons.append('observed-' + window.name)
        return eligible, ','.join(reasons) or 'queue'

    def reserve(self, *, job_id, owner_id, stage, provider, request_sha256, tokens=0, input_tokens=0, output_tokens=0):
        if provider not in self.limits or any(type(v) is not int or v < 0 for v in (tokens, input_tokens, output_tokens)):
            raise ValueError('Provider and conservative token reservations must be explicit.')
        if not all(isinstance(v, str) and v and len(v) <= 256 for v in (job_id, owner_id, stage)) or not re.fullmatch('[a-f0-9]{64}', request_sha256):
            raise ValueError('Invalid private operation identity.')
        now, deferred, oversized = self.clock(), None, None
        costs = dict(requests=1, tokens=tokens, input_tokens=input_tokens, output_tokens=output_tokens)
        with self._transaction() as db:
            row = db.execute('SELECT * FROM operations WHERE owner=? AND job=? AND stage=? AND provider=?',
                             (owner_id, job_id, stage, provider)).fetchone()
            if row:
                if row['request_sha'] != request_sha256:
                    raise RuntimeError('Exact provider reconstruction request differs; no request sent.')
                if row['state'] in ('SENT', 'UNKNOWN'):
                    raise ProviderUncertain(provider, stage)
                if row['state'] in ('FAILED', 'CANCELLED'):
                    if row['reason'] == 'oversized':
                        info = json.loads(row['metadata'])
                        raise ProviderRequestTooLarge(provider, info['window'], info['required'], info['capacity'])
                    raise ProviderRecordedFailure(provider, stage, row['status'])
                if row['state'] in ('ACCEPTED', 'CACHED', 'RESERVED'):
                    return dict(row)
            else:
                cursor = db.execute('''INSERT INTO operations(owner,job,stage,provider,request_sha,state,created,
                    tokens,input_tokens,output_tokens) VALUES(?,?,?,?,?,'PENDING',?,?,?,?)''',
                    (owner_id, job_id, stage, provider, request_sha256, now, tokens, input_tokens, output_tokens))
                row = db.execute('SELECT * FROM operations WHERE id=?', (cursor.lastrowid,)).fetchone()
            try:
                next_at, reason = self._eligibility(db, provider, costs, now)
                # Eligible FIFO only: oversize or long-waiting work never blocks another window.
                earlier = db.execute("SELECT * FROM operations WHERE provider=? AND state='PENDING' AND id<? ORDER BY id",
                                     (provider, row['id'])).fetchall()
                for other in earlier:
                    other_costs = dict(requests=1, tokens=other['tokens'], input_tokens=other['input_tokens'], output_tokens=other['output_tokens'])
                    try:
                        when, _ = self._eligibility(db, provider, other_costs, now)
                    except ProviderRequestTooLarge:
                        continue
                    if when <= now:
                        next_at, reason = max(next_at, now + 1), 'eligible-queue-position'
                        break
                if next_at > now:
                    db.execute('UPDATE operations SET next_at=?,reason=? WHERE id=?', (next_at, reason, row['id']))
                    deferred = ProviderDeferred(provider, next_at, reason, stage)
                else:
                    db.execute("UPDATE operations SET state='RESERVED',reserved=?,next_at=0,reason=NULL WHERE id=?", (now, row['id']))
                    for window in self.limits[provider]:
                        db.execute('UPDATE observations SET remaining=max(0,remaining-?) WHERE provider=? AND name=? AND expires>?',
                                   (costs[window.metric], provider, window.name, now))
            except ProviderRequestTooLarge as exc:
                db.execute("UPDATE operations SET state='FAILED',reason='oversized',metadata=? WHERE id=?",
                           (json.dumps(dict(window=exc.window, required=exc.required, capacity=exc.capacity)), row['id']))
                oversized = exc
            result = dict(db.execute('SELECT * FROM operations WHERE id=?', (row['id'],)).fetchone())
        if oversized:
            raise oversized
        if deferred:
            raise deferred
        return result

    def mark_sent(self, operation_id):
        deferred = None
        with self._transaction() as db:
            row = db.execute('SELECT * FROM operations WHERE id=?', (operation_id,)).fetchone()
            if row is None or row['state'] != 'RESERVED':
                raise RuntimeError('Attempt already dispatched or lacks a durable reservation; no request sent.')
            now = self.clock()
            costs = dict(requests=1, tokens=row['tokens'], input_tokens=row['input_tokens'], output_tokens=row['output_tokens'])
            when, reason = self._eligibility(db, row['provider'], costs, now,
                                             exclude_id=operation_id, observed_remaining=False)
            if when > now:
                db.execute("UPDATE operations SET state='PENDING',reserved=NULL,next_at=?,reason=? WHERE id=?", (when, reason, operation_id))
                deferred = ProviderDeferred(row['provider'], when, reason, row['stage'])
            else:
                # A pre-send process interruption can make an old reservation
                # stale. Recheck atomically and charge the actual dispatch time.
                db.execute("UPDATE operations SET state='SENT',reserved=?,sent=? WHERE id=?", (now, now, operation_id))
        if deferred:
            raise deferred

    def _observe(self, db, provider, status, metadata, now):
        # Groq explicitly documents requests headers as RPD and tokens as TPM.
        if provider == 'groq':
            mapping = [('rpd', 'requests'), ('tpm', 'tokens')]
        else:
            mapping = []
        for name, suffix in mapping:
            window = next((w for w in self.limits[provider] if w.name == name), None)
            if window is None:
                continue
            capacity = metadata.get('x-ratelimit-limit-' + suffix)
            remaining = metadata.get('x-ratelimit-remaining-' + suffix)
            seconds = metadata.get('x-ratelimit-reset-' + suffix + '-seconds', window.seconds)
            if capacity is not None or remaining is not None:
                # Limits stay conservative after reset; remaining expires only by observed/fallback duration.
                old = db.execute('SELECT capacity FROM observations WHERE provider=? AND name=?', (provider, name)).fetchone()
                capacities = [v for v in (capacity, old['capacity'] if old else None) if v is not None]
                db.execute('INSERT OR REPLACE INTO observations VALUES(?,?,?,?,?)',
                           (provider, name, min(capacities) if capacities else None, remaining, now + max(1, seconds)))
        if status == 429:
            durations = [v for k, v in metadata.items() if k.endswith('-seconds')]
            until = now + max([60.0] + durations)
            db.execute('INSERT INTO cooldowns VALUES(?,?) ON CONFLICT(provider) DO UPDATE SET until_at=max(until_at,excluded.until_at)',
                       (provider, until))

    def finish(self, operation_id, *, result=None, status=None, headers=None, tokens=None,
               input_tokens=None, output_tokens=None, unknown=False):
        now = self.clock()
        metadata = safe_quota_metadata(headers, now=now)
        if any(value is not None and (type(value) is not int or value < 0)
               for value in (tokens, input_tokens, output_tokens)):
            raise ValueError('Invalid accepted token usage.')
        encoded = json.dumps(result, ensure_ascii=False, allow_nan=False) if result is not None else None
        with self._transaction() as db:
            row = db.execute('SELECT * FROM operations WHERE id=?', (operation_id,)).fetchone()
            if row is None or row['state'] != 'SENT':
                raise RuntimeError('Only the original dispatched attempt can accept a receipt.')
            state = 'UNKNOWN' if unknown else 'ACCEPTED' if encoded is not None else 'FAILED'
            inputs, outputs = max(row['input_tokens'], input_tokens or 0), max(row['output_tokens'], output_tokens or 0)
            total = max(row['tokens'], tokens or 0, inputs + outputs)
            exceeded = any(actual is not None and actual > row[name] for name, actual in
                           (('tokens', tokens), ('input_tokens', input_tokens), ('output_tokens', output_tokens)))
            db.execute('UPDATE operations SET state=?,status=?,result=?,metadata=?,tokens=?,input_tokens=?,output_tokens=? WHERE id=?',
                       (state, status, encoded, json.dumps(metadata), total, inputs, outputs, operation_id))
            if exceeded:
                binding = {'schema_version': 1, 'provider': row['provider'], 'operation_id': operation_id,
                    'reason': 'token-reservation-exceeded', 'created_epoch': now,
                    'reserved': {name: row[name] for name in ('tokens', 'input_tokens', 'output_tokens')},
                    'observed': {'tokens': tokens, 'input_tokens': input_tokens, 'output_tokens': output_tokens}}
                db.execute('INSERT OR IGNORE INTO provider_pauses VALUES(?,?,?,?,?)',
                    (row['provider'], now, binding['reason'], json.dumps(binding, sort_keys=True), fingerprint(binding)))
            self._observe(db, row['provider'], status, metadata, now)
        return {'reservation_exceeded': exceeded}

    def paused_providers(self):
        """Numeric safety metadata only; no credential or raw provider envelope."""
        with self._transaction() as db:
            rows = db.execute('SELECT provider,created,reason,pause_sha FROM provider_pauses').fetchall()
        return {row['provider']: {'since_epoch': row['created'], 'reason': row['reason'],
                                 'pause_sha256': row['pause_sha']} for row in rows}

    def cache_accept(self, *, job_id, owner_id, stage, provider, request_sha256, result):
        encoded = json.dumps(result, ensure_ascii=False, allow_nan=False)
        with self._transaction() as db:
            row = db.execute('SELECT * FROM operations WHERE owner=? AND job=? AND stage=? AND provider=?',
                             (owner_id, job_id, stage, provider)).fetchone()
            if row:
                if row['request_sha'] != request_sha256 or row['state'] not in ('PENDING', 'CACHED'):
                    raise RuntimeError('Cache cannot overwrite a provider attempt.')
                db.execute("UPDATE operations SET state='CACHED',result=?,next_at=0 WHERE id=?", (encoded, row['id']))
            else:
                db.execute('''INSERT INTO operations(owner,job,stage,provider,request_sha,state,created,
                    tokens,input_tokens,output_tokens,result) VALUES(?,?,?,?,?,'CACHED',?,0,0,0,?)''',
                    (owner_id, job_id, stage, provider, request_sha256, self.clock(), encoded))

    def recover_sent(self, *, job_id=None, owner_id=None):
        """Call after exclusive worker recovery, never while another worker runs."""
        if (job_id is None) != (owner_id is None):
            raise ValueError('Recovery requires both owner and job identity.')
        with self._transaction() as db:
            where = '' if job_id is None else ' AND job=? AND owner=?'
            return db.execute("UPDATE operations SET state='UNKNOWN' WHERE state='SENT'" + where,
                              () if job_id is None else (job_id, owner_id)).rowcount

    def stats(self, *, job_id, owner_id):
        with self._transaction() as db:
            rows = db.execute('SELECT provider,state,sent FROM operations WHERE job=? AND owner=?', (job_id, owner_id)).fetchall()
        result = {}
        for row in rows:
            stats = result.setdefault(row['provider'], dict(network_attempts=0, accepted=0, cache_hits=0, failed=0, unknown=0))
            stats['network_attempts'] += int(row['sent'] is not None)
            field = {'ACCEPTED': 'accepted', 'CACHED': 'cache_hits', 'FAILED': 'failed', 'UNKNOWN': 'unknown', 'SENT': 'unknown'}.get(row['state'])
            if field:
                stats[field] += 1
        return result

    def record_receipt(self, receipt):
        with self._transaction() as db:
            db.execute('INSERT INTO receipts(owner,job,provider,mode,recorded,value) VALUES(?,?,?,?,?,?)',
                       (receipt['owner_id'], receipt['job_id'], receipt['provider'], receipt['operation_mode'],
                        self.clock(), json.dumps(receipt, ensure_ascii=False, allow_nan=False)))

    def job_stats(self, job_id, owner_id=None):
        with self._transaction() as db:
            suffix = '' if owner_id is None else ' AND owner=?'
            values = (job_id,) if owner_id is None else (job_id, owner_id)
            rows = db.execute('SELECT provider,state,sent FROM operations WHERE job=?' + suffix, values).fetchall()
            receipts = db.execute('SELECT provider,mode FROM receipts WHERE job=?' + suffix, values).fetchall()
        result = {}
        def entry(provider):
            return result.setdefault(provider, dict(http_attempts=0, cache_hits=0, reconstructed_steps=0,
                                                   unknown_attempts=0, failed_attempts=0, accepted_steps=0))
        for row in rows:
            stats = entry(row['provider'])
            stats['http_attempts'] += int(row['sent'] is not None)
            stats['unknown_attempts'] += int(row['state'] in ('UNKNOWN', 'SENT'))
            stats['failed_attempts'] += int(row['state'] == 'FAILED' and row['sent'] is not None)
            stats['accepted_steps'] += int(row['state'] in ('ACCEPTED', 'CACHED'))
        for row in receipts:
            stats = entry(row['provider'])
            stats['cache_hits'] += int(row['mode'] == 'private-cache')
            stats['reconstructed_steps'] += int(row['mode'] == 'accepted-reconstruction')
        return result

    def job_receipts(self, job_id, owner_id=None):
        with self._transaction() as db:
            suffix = '' if owner_id is None else ' AND owner=?'
            values = (job_id,) if owner_id is None else (job_id, owner_id)
            rows = db.execute('SELECT value FROM receipts WHERE job=?' + suffix + ' ORDER BY id', values).fetchall()
        return [json.loads(row['value']) for row in rows]

    def abandon_pending(self, job_id, owner_id):
        """Release only unsent work of a terminal owned job; retain its audit rows."""
        with self._transaction() as db:
            return db.execute("UPDATE operations SET state='CANCELLED',reason='job-terminal' WHERE job=? AND owner=? AND state IN ('PENDING','RESERVED')",
                              (job_id, owner_id)).rowcount
