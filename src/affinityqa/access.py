"""One-request access probe, after the operator confirms credential provenance."""
from __future__ import annotations

import json
from pathlib import Path
import re

from .errors import AffinityQAError, SchemaError
from .evidence import fingerprint
from .models import parse_entities
from .qloo import BASE_URL, QlooClient


def verify_saved_access(directory: Path, report: dict) -> bool:
    """Revalidate the captured request offline, preserving its original report."""
    sample_path = directory / "http-0001.json"
    if sample_path.is_symlink() or not sample_path.is_file() or sample_path.stat().st_size > 5_100_000:
        return False
    try:
        sample = json.loads(sample_path.read_text(encoding="utf-8"))
        if (sample.get("source") != "qloo-live" or sample.get("status") != 200
                or sample.get("live_network_request") is not True or sample.get("attempt") != 1
                or sample.get("request") != {"method": "GET", "host": BASE_URL, "path": "/search",
                    "params": {"query": "Brian Eno", "types": "urn:entity:artist", "take": 3}}
                or report.get("real_qloo_requests") != 1
                or fingerprint(sample.get("response")) != sample.get("response_sha256")):
            return False
        # Bind the sample to the originally recorded tool call, not a new run.
        events_path = directory / "ledger.jsonl"
        if events_path.is_symlink() or not events_path.is_file() or events_path.stat().st_size > 30_000:
            return False
        event = json.loads(events_path.read_text(encoding="utf-8").splitlines()[0])
        if (event.get("source") != "qloo-live" or event.get("kind") != "tool_call"
                or event.get("data", {}).get("response_sha256") != sample["response_sha256"]
                or event.get("data", {}).get("request") != sample["request"]
                or event.get("data", {}).get("status") != 200):
            return False
        rows = parse_entities(sample["response"], insights=False)
        return bool(rows) and any("urn:entity:artist" in row.types for row in rows)
    except (OSError, ValueError, TypeError, KeyError, IndexError, AttributeError, AffinityQAError):
        return False


def probe_access(client: QlooClient) -> dict:
    report = {"schema_version": 1, "run_id": client.ledger.run_id, "source": client.ledger.source,
              "access_gate": "INCONCLUSIVE", "ci_gate": "NOT_VALIDATED", "error": None,
              "notice": "Authentication and response shape only; personalization and agent repair are not validated."}
    try:
        body = client.get("/search", {"query": "Brian Eno", "types": "urn:entity:artist", "take": 3}, cache=False)
        rows = parse_entities(body, insights=False, synthetic=client.synthetic)
        if not rows or not any("urn:entity:artist" in row.types for row in rows):
            raise SchemaError("The authenticated response has no typed artist results.")
        report.update({"access_gate": "NOT_VALIDATED" if client.synthetic else "PASS",
                       "typed_results": len(rows)})
    except AffinityQAError as exc:
        report["error"] = str(exc)
        client.ledger.record("stopped", {"reason": str(exc)})
    report.update({"real_qloo_requests": client.ledger.live_requests, "transport_attempts": client.requests})
    client.ledger.write("access-report.json", report)
    return report


def public_access_state(runs_root: Path) -> dict:
    """Expose bounded state, never keys, response bodies or local file paths."""
    run_pattern = re.compile(r"\d{8}T\d{6}Z-[a-f0-9]{8}\Z")
    default = {"qloo_validation": "NOT_TESTED", "real_qloo_requests": 0,
               "request_count_scope": "latest-access-probe", "last_access_probe": None}
    if not runs_root.is_dir():
        return default
    for directory in sorted(runs_root.iterdir(), reverse=True):
        if directory.is_symlink() or not run_pattern.fullmatch(directory.name) or not directory.is_dir():
            continue
        path = directory / "access-report.json"
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 20_000:
            continue
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(report, dict) or report.get("run_id") != directory.name or report.get("source") != "qloo-live":
                continue
            count = report.get("real_qloo_requests")
            if isinstance(count, bool) or not isinstance(count, int) or not 0 <= count <= 1:
                continue
            error = report.get("error")
            state = "AUTHENTICATED_REFERENCE_NOT_VALIDATED" if verify_saved_access(directory, report) else "INCONCLUSIVE"
            if isinstance(error, str) and error.startswith(("Qloo returned HTTP 401;", "Qloo returned HTTP 403;")):
                state = "AUTH_REJECTED"
            return {"qloo_validation": state, "real_qloo_requests": count,
                    "request_count_scope": "latest-access-probe", "last_access_probe": directory.name}
        except (OSError, ValueError, TypeError):
            continue
    return default
