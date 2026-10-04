from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import json
import os
from pathlib import Path
import random
import ssl
import time
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener

from .errors import BudgetError, SchemaError, TransportError
from .evidence import Ledger, fingerprint, redact
from .models import canonical_id, validate_response_envelope

BASE_URL = "https://hackathon.api.qloo.com"
SAFE_RESPONSE_HEADERS = {"retry-after", "x-request-id", "x-ratelimit-limit", "x-ratelimit-remaining",
                         "x-ratelimit-reset", "ratelimit-limit", "ratelimit-remaining", "ratelimit-reset"}
INSIGHTS_COMMON = {"filter.type", "bias.trends", "filter.exclude.entities", "filter.results.entities",
                   "signal.interests.entities", "take"}
INSIGHTS_EXTRA = {"urn:entity:movie": set(), "urn:entity:brand": set(),
                  "urn:entity:artist": set(),
                  "urn:entity:book": {"filter.publication_year.min", "filter.publication_year.max"}}


@dataclass(frozen=True, repr=False)
class Settings:
    api_key: str
    base_url: str = BASE_URL

    def __post_init__(self) -> None:
        if self.base_url != BASE_URL:
            raise TransportError("Hackathon API calls are restricted to https://hackathon.api.qloo.com.")

    @classmethod
    def from_environment(cls, env_file: Path | None = None, *, use_process_environment: bool = True) -> "Settings":
        values: dict[str, str] = {}
        if env_file and env_file.exists():
            for line in env_file.read_text(encoding="utf-8-sig").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                key, separator, value = line.partition("=")
                if separator and key.strip() in {"QLOO_API_KEY", "QLOO_BASE_URL"}:
                    values[key.strip()] = value.strip().strip("\"'")
        process_values = os.environ if use_process_environment else {}
        return cls(process_values.get("QLOO_API_KEY") or values.get("QLOO_API_KEY", ""),
                   process_values.get("QLOO_BASE_URL") or values.get("QLOO_BASE_URL", BASE_URL))


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise HTTPError(req.full_url, code, "Redirect rejected to protect the API key", headers, fp)


@dataclass
class Response:
    status: int
    body: Any
    headers: dict[str, str]
    elapsed_ms: float = 0


class Transport(Protocol):
    def send(self, path: str, params: dict[str, Any]) -> Response: ...


class LiveTransport:
    def __init__(self, settings: Settings, timeout: float = 12) -> None:
        if not settings.api_key.strip():
            raise TransportError("QLOO_API_KEY is missing. Configure it locally in .env; do not paste it in chat.")
        self.settings = settings
        self.timeout = timeout
        self.opener = build_opener(NoRedirect(), HTTPSHandler(context=ssl.create_default_context()))

    def send(self, path: str, params: dict[str, Any]) -> Response:
        started = time.monotonic()
        request = Request(self.settings.base_url + path + "?" + urlencode(params),
                          headers={"X-Api-Key": self.settings.api_key, "Accept": "application/json"}, method="GET")
        try:
            stream = self.opener.open(request, timeout=self.timeout)
        except HTTPError as exc:
            stream = exc
        except (URLError, TimeoutError, OSError) as exc:
            # Exception strings and request headers can contain credentials; never echo them.
            raise TransportError("Qloo network/TLS request failed. Certificate checks remain enabled.") from None
        try:
            with stream:
                status = stream.code
                headers = {key.lower(): value for key, value in stream.headers.items() if key.lower() in SAFE_RESPONSE_HEADERS}
                raw = stream.read(5_000_001)
        except (OSError, TimeoutError):
            raise TransportError("Qloo response read failed. Inspect the recorded attempt and rerun later.") from None
        if len(raw) > 5_000_000:
            raise TransportError("Qloo response exceeds the 5 MB recording limit.")
        try:
            def reject_constant(value):
                raise ValueError("Nonfinite JSON number")
            body = json.loads(raw, parse_constant=reject_constant)
        except (ValueError, UnicodeDecodeError):
            # An HTML error may echo a key. Record only a safe description of non-JSON content.
            body = {"non_json_response": True, "bytes": len(raw)}
        return Response(status, body, headers, (time.monotonic() - started) * 1000)


def validate_params(path: str, params: dict[str, Any], *, synthetic: bool) -> None:
    allowed = {"/search": {"query", "types", "take"}, "/entities": {"entity_ids"}}
    if path == "/v2/insights":
        entity_type = params.get("filter.type")
        if entity_type not in INSIGHTS_EXTRA:
            raise SchemaError("This spike supports only reviewed movie, artist, brand, and book parameters.")
        allowed[path] = INSIGHTS_COMMON | INSIGHTS_EXTRA[entity_type]
    if path not in allowed or set(params) - allowed[path]:
        raise SchemaError("Undocumented or unreviewed parameters are not sent to Qloo.")
    for key in ("entity_ids", "signal.interests.entities", "filter.results.entities", "filter.exclude.entities"):
        if key in params:
            if not isinstance(params[key], str) or not params[key]:
                raise SchemaError(f"{key} must be a nonempty comma-separated ID list.")
            for item in params[key].split(","):
                canonical_id(item, synthetic=synthetic)
    if "take" in params and (isinstance(params["take"], bool) or not isinstance(params["take"], int) or not 1 <= params["take"] <= 50):
        raise SchemaError("take must be an integer from 1 to 50.")


def retry_delay(value: str | None, attempt: int) -> float:
    if value:
        try:
            delay = float(value)
        except ValueError:
            try:
                date = parsedate_to_datetime(value)
                if date.tzinfo is None:
                    date = date.replace(tzinfo=timezone.utc)
                delay = max(0, (date - datetime.now(timezone.utc)).total_seconds())
            except (ValueError, TypeError):
                delay = 2 ** (attempt - 1)
    else:
        delay = 2 ** (attempt - 1)
    if delay > 5:
        raise TransportError("Qloo requests a Retry-After longer than five seconds. Stop and rerun later.")
    return max(0, delay) + random.uniform(0, 0.1)


class QlooClient:
    def __init__(self, transport: Transport, ledger: Ledger, *, synthetic: bool = False,
                 max_requests: int = 60, max_attempts: int = 3, sleeper=time.sleep) -> None:
        self.transport = transport
        self.ledger = ledger
        self.synthetic = synthetic
        self.max_requests = max_requests
        self.max_attempts = max_attempts
        self.sleeper = sleeper
        self.requests = 0
        self.cache: dict[str, Any] = {}
        if isinstance(max_requests, bool) or not isinstance(max_requests, int) or not 1 <= max_requests <= 100:
            raise BudgetError("Request budget must be an integer from 1 to 100.")
        if isinstance(max_attempts, bool) or not isinstance(max_attempts, int) or not 1 <= max_attempts <= 3:
            raise BudgetError("At most three attempts are allowed per request.")

    def get(self, path: str, params: dict[str, Any], *, cache: bool = True) -> Any:
        validate_params(path, params, synthetic=self.synthetic)
        request = {"method": "GET", "host": BASE_URL, "path": path, "params": dict(sorted(params.items()))}
        cache_key = fingerprint(request)
        if cache and cache_key in self.cache:
            self.ledger.record("cache_hit", {"request_sha256": cache_key})
            return self.cache[cache_key]
        for attempt in range(1, self.max_attempts + 1):
            if self.requests >= self.max_requests:
                raise BudgetError("Request budget exhausted; no further requests were made.")
            self.requests += 1
            if not self.synthetic:
                self.ledger.live_requests += 1
            try:
                response = self.transport.send(path, params)
            except TransportError:
                self.ledger.record("transport_failure", {"request": request, "attempt": attempt})
                if attempt < self.max_attempts:
                    self.sleeper(retry_delay(None, attempt))
                    continue
                raise
            self.ledger.sample(request, response.status, response.body, response.headers, response.elapsed_ms,
                               live=not self.synthetic, attempt=attempt)
            if response.status == 200:
                validate_response_envelope(response.body, insights=path == "/v2/insights")
                safe_body = redact(response.body, self.ledger.secrets)
                if cache:
                    self.cache[cache_key] = safe_body
                return safe_body
            if response.status in (401, 403):
                raise TransportError(f"Qloo returned HTTP {response.status}; check key, host, and endpoint access. No auth retry.")
            transient = response.status == 429 or 500 <= response.status < 600
            if transient and attempt < self.max_attempts:
                self.sleeper(retry_delay(response.headers.get("retry-after"), attempt))
                continue
            raise TransportError(f"Qloo returned HTTP {response.status}. Inspect the sanitized response sample.")
        raise TransportError("Qloo retry attempts exhausted.")

