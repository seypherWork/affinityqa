from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any
from uuid import uuid4


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def fingerprint(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


SENSITIVE_KEYS = {"x-api-key", "api_key", "apikey", "qloo_api_key", "authorization", "cookie", "set-cookie",
                  "password", "secret", "token", "chain_of_thought", "reasoning", "thoughts", "scratchpad"}


def redact(value: Any, secrets: tuple[str, ...] = ()) -> Any:
    if isinstance(value, dict):
        return {redact(str(key), secrets): ("[REDACTED]" if str(key).lower() in SENSITIVE_KEYS else redact(item, secrets))
                for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(item, secrets) for item in value]
    if isinstance(value, str):
        for secret in secrets:
            if secret:
                value = value.replace(secret, "[REDACTED]")
        return value
    return value


class Ledger:
    def __init__(self, parent: Path, source: str, secrets: tuple[str, ...] = ()) -> None:
        self.source = source
        self.secrets = secrets
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.run_id = f"{timestamp}-{uuid4().hex[:8]}"
        self.directory = parent / self.run_id
        self.directory.mkdir(parents=True, exist_ok=False)
        self.events: list[dict[str, Any]] = []
        self.live_requests = 0

    def write(self, name: str, value: Any) -> Path:
        destination = self.directory / name
        # Exclusive creation: evidence from an existing run is never overwritten.
        with destination.open("x", encoding="utf-8") as handle:
            json.dump(redact(value, self.secrets), handle, indent=2, ensure_ascii=False, allow_nan=False)
            handle.write("\n")
        return destination

    def record(self, kind: str, data: dict[str, Any]) -> dict[str, Any]:
        event = {"sequence": len(self.events) + 1, "timestamp_utc": utc_now(), "source": self.source,
                 "kind": kind, "data": redact(data, self.secrets)}
        self.events.append(event)
        with (self.directory / "ledger.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, allow_nan=False) + "\n")
        return event

    def sample(self, request: dict[str, Any], status: int, body: Any, headers: dict[str, str],
               elapsed_ms: float, *, live: bool, attempt: int) -> None:
        safe_body = redact(body, self.secrets)
        sample = {"source": self.source, "request": request, "status": status, "response": safe_body,
                  "response_sha256": fingerprint(safe_body), "response_headers": headers,
                  "elapsed_ms": round(elapsed_ms, 3), "attempt": attempt, "live_network_request": live}
        name = f"http-{len(self.events) + 1:04d}.json"
        self.write(name, sample)
        self.record("tool_call", {"sample": name, **{key: value for key, value in sample.items() if key != "response"}})

