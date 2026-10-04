from __future__ import annotations

import copy
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
import time
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from .errors import AffinityQAError, SchemaError
from .evaluation import evaluate_replay, validate_frozen_reference
from .evidence import Ledger, fingerprint
from .metrics import validate_ranking

CONTRACT_VERSION = "ranked-catalog-v1"
MAX_OUTPUT_BYTES = 262144


class AgentError(AffinityQAError):
    pass


class AgentAdapter(Protocol):
    name: str
    version: str
    kind: str
    source: str

    def rank(self, request: dict[str, Any]) -> dict[str, Any]: ...


def strict_json(raw: bytes) -> dict[str, Any]:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result

    def nonfinite(value):
        raise ValueError("Nonfinite JSON number")

    try:
        value = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=pairs, parse_constant=nonfinite)
        if not isinstance(value, dict):
            raise ValueError("Not an object")
        return value
    except (ValueError, UnicodeError, RecursionError):
        raise AgentError("Agent must return one strict JSON object; no prose or private reasoning is accepted.") from None


def _timeout(value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0.1 <= value <= 30:
        raise SchemaError("Agent timeout must be finite and between 0.1 and 30 seconds.")
    return value


class ProcessJsonAdapter:
    """Explicit CLI command, JSON over stdin/stdout; never selectable through the API.

    This is not an OS sandbox. Only run a trusted executable you intentionally select.
    The Qloo key and other application credentials are not inherited by the child.
    """
    kind = "process-json"
    source = "user-replay"

    def __init__(self, name: str, version: str, command: list[str], *, cwd: Path, timeout: float = 15) -> None:
        if not command or any(not isinstance(item, str) or not item or "\x00" in item for item in command):
            raise SchemaError("Agent command needs a nonempty executable/argument array.")
        self.name, self.version, self.command = name, version, list(command)
        self.cwd, self.timeout = cwd, _timeout(timeout)

    def rank(self, request: dict[str, Any]) -> dict[str, Any]:
        # Minimal inherited OS/runtime environment, not the parent application's credentials.
        allowed = {"path", "systemroot", "windir", "temp", "tmp", "tmpdir", "lang", "lc_all"}
        environment = {key: value for key, value in os.environ.items() if key.lower() in allowed}
        environment.update({"PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"})
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        # Private temporary handles prevent unbounded stdout from being collected in RAM.
        with tempfile.TemporaryFile() as input_file, tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
            input_file.write(json.dumps(request, ensure_ascii=False, allow_nan=False).encode("utf-8"))
            input_file.seek(0)
            try:
                with subprocess.Popen(self.command, stdin=input_file, stdout=output, stderr=errors,
                                      cwd=self.cwd, env=environment, shell=False, creationflags=flags) as process:
                    try:
                        code = process.wait(timeout=self.timeout)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                        raise AgentError("Agent timed out; the direct child was stopped and no evaluation passed.") from None
            except OSError:
                raise AgentError("Agent executable could not start. Review the trusted command and working directory.") from None
            if code != 0:
                raise AgentError("Agent exited unsuccessfully; raw stderr is not recorded.")
            output.seek(0)
            raw = output.read(MAX_OUTPUT_BYTES + 1)
            if len(raw) > MAX_OUTPUT_BYTES:
                raise AgentError("Agent JSON output exceeds the bounded response size.")
            return strict_json(raw)


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class LocalHttpJsonAdapter:
    """Explicit loopback HTTP contract; no DNS, proxy, redirects, or credential headers."""
    kind = "local-http-json"
    source = "user-replay"

    def __init__(self, name: str, version: str, url: str, *, timeout: float = 15) -> None:
        try:
            parsed = urlsplit(url)
            if (parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "::1")
                    or parsed.username or parsed.password or parsed.query or parsed.fragment or not parsed.port):
                raise ValueError("Not an explicit numeric loopback endpoint")
        except ValueError:
            raise SchemaError("Agent endpoint must be http://127.0.0.1:PORT/PATH or http://[::1]:PORT/PATH without credentials or query.") from None
        self.name, self.version, self.url, self.timeout = name, version, url, _timeout(timeout)
        self.opener = build_opener(ProxyHandler({}), _RejectRedirects())

    def rank(self, request: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(request, ensure_ascii=False, allow_nan=False).encode("utf-8")
        try:
            with self.opener.open(Request(self.url, data=body, headers={"Content-Type": "application/json"}, method="POST"),
                                  timeout=self.timeout) as response:
                if response.status != 200 or response.headers.get_content_type() != "application/json":
                    raise AgentError("Local agent must return HTTP 200 and application/json.")
                raw = response.read(MAX_OUTPUT_BYTES + 1)
                if len(raw) > MAX_OUTPUT_BYTES:
                    raise AgentError("Agent JSON output exceeds the bounded response size.")
                return strict_json(raw)
        except (HTTPError, URLError, TimeoutError, OSError):
            raise AgentError("Local agent HTTP request failed; redirects and automatic retries are disabled.") from None


class SyntheticControlAdapter:
    kind = "synthetic-control"
    source = "synthetic-control"
    name = "synthetic-demo-agent"

    def __init__(self, behavior: str) -> None:
        if behavior not in ("taste-aware", "taste-insensitive"):
            raise SchemaError("Unknown synthetic control behavior.")
        self.behavior = behavior
        self.version = "v1-taste-aware-control" if behavior == "taste-aware" else "v2-taste-insensitive-control"

    def rank(self, request: dict[str, Any]) -> dict[str, Any]:
        if request["reference_source"] != "synthetic":
            raise AgentError("Engineered fixture controls cannot be executed against a live Qloo reference.")
        ids = sorted(item["entity_id"] for item in request["catalog"])
        if self.behavior == "taste-aware" and request["persona"]["tastes"][0]["name"] == "Bad Bunny":
            ids.reverse()
        return {"schema_version": 1, "request_id": request["request_id"], "ranked_entity_ids": ids}


def build_requests(references: dict[str, Any], config: dict[str, Any]) -> list[dict[str, Any]]:
    validate_frozen_reference(references)
    if references.get("config_sha256") != fingerprint(config):
        raise SchemaError("Agent inputs must use the exact configuration captured with the frozen reference.")
    if not references.get("cases") or {case["case_id"] for case in references["cases"]} != {s["id"] for s in config["scenarios"]}:
        raise SchemaError("Execute agents only after every configured reference case was captured.")
    requests = []
    for case in references["cases"]:
        # Only reviewed catalog metadata. No reference ranking, affinity, diagnosis or threshold.
        catalog = [{"entity_id": entity["entity_id"], "name": entity["name"], "types": entity["types"],
                    "publication_year": entity.get("metadata", {}).get("publication_year")}
                   for entity in sorted(case["entities"], key=lambda item: item["entity_id"])]
        if len(catalog) != len(case["candidate_ids"]) or {item["entity_id"] for item in catalog} != set(case["candidate_ids"]):
            raise SchemaError("Agent catalog does not match the frozen candidate universe.")
        shared = {"schema_version": 1, "contract_version": CONTRACT_VERSION, "case_id": case["case_id"],
                  "task": case["task"], "entity_type": case["filter_type"], "constraints": case["constraints"],
                  "top_k": case["top_k"], "catalog": catalog, "reference_source": references["source"],
                  "output_policy": "Return only JSON: schema_version=1, request_id echoed, ranked_entity_ids. Rank at least top_k distinct catalog IDs. No reasoning."}
        for persona in ("A", "B"):
            request = copy.deepcopy(shared)
            request["persona"] = {"tastes": [{"name": seed["name"], "type": seed["search_type"]}
                                             for seed in config["personas"][persona]]}
            request["request_id"] = fingerprint(request)
            requests.append({"persona_label": persona, "request": request})
    return requests


def validate_response(request: dict[str, Any], response: dict[str, Any]) -> list[str]:
    if not isinstance(response, dict) or set(response) != {"schema_version", "request_id", "ranked_entity_ids"}:
        raise AgentError("Agent response must contain only schema_version, request_id, ranked_entity_ids.")
    if type(response["schema_version"]) is not int or response["schema_version"] != 1 or response["request_id"] != request["request_id"]:
        raise AgentError("Agent response version or request_id does not match the observable input.")
    ids = response["ranked_entity_ids"]
    if not isinstance(ids, list) or len(ids) > len(request["catalog"]):
        raise AgentError("Agent rankings must be a bounded array of catalog IDs.")
    validate_ranking(ids, minimum=request["top_k"])
    if set(ids) - {entity["entity_id"] for entity in request["catalog"]}:
        raise AgentError("Agent returned IDs outside the fixed catalog; no evaluation was created.")
    return list(ids)


def execute_agent(references: dict[str, Any], config: dict[str, Any], adapter: AgentAdapter, ledger: Ledger) -> dict[str, Any]:
    for value in (adapter.name, adapter.version):
        if not isinstance(value, str) or not value.strip() or len(value) > 120:
            raise SchemaError("Agent name/version must be nonempty strings of at most 120 characters.")
    requests = build_requests(references, config)
    if ledger.source != references["source"] or adapter.source not in ("synthetic-control", "user-replay"):
        raise SchemaError("Execution provenance does not match the frozen reference.")
    ledger.write("config.json", config)
    ledger.write("reference.json", references)
    decisions: dict[str, Any] = {}
    calls = 0
    error = None
    for item in requests:
        request = item["request"]
        case_id, persona = request["case_id"], item["persona_label"]
        ledger.write(f"agent-input-{calls + 1:04d}.json", request)
        start = time.monotonic()
        try:
            # Give adapters their own copy, preserving the auditable input on mutation.
            response = adapter.rank(copy.deepcopy(request))
            ranking = validate_response(request, response)
        except AffinityQAError as exc:
            error = str(exc)
        except Exception:
            error = "Agent adapter failed; untrusted exception text is not recorded."
        calls += 1
        if error:
            ledger.record("agent_failed", {"case_id": case_id, "persona": persona, "request_id": request["request_id"],
                                          "elapsed_ms": round((time.monotonic() - start) * 1000, 3), "reason": error})
            break
        ledger.write(f"agent-output-{calls:04d}.json", response)
        decisions.setdefault(case_id, {})[persona] = ranking
        ledger.record("agent_decision", {"case_id": case_id, "persona": persona, "request_id": request["request_id"],
                                        "output_sha256": fingerprint(response), "adapter_kind": adapter.kind,
                                        "elapsed_ms": round((time.monotonic() - start) * 1000, 3)})
    evaluation = None
    if not error:
        replay = {"schema_version": 1, "source": adapter.source, "agent_name": adapter.name, "agent_version": adapter.version,
                  "reference_bundle_id": references["reference_bundle_id"], "cases": decisions}
        evaluation = evaluate_replay(references, replay, config["thresholds"])
        ledger.write("agent-replay.json", replay)
        ledger.write("evaluation.json", evaluation)
    report = {"schema_version": 1, "run_id": ledger.run_id, "source": references["source"], "adapter_kind": adapter.kind,
              "agent_name": adapter.name, "agent_version": adapter.version, "agent_source": adapter.source,
              "reference_bundle_id": references["reference_bundle_id"], "execution_status": "FAILED" if error else "COMPLETED",
              "agent_calls": calls, "planned_calls": len(requests), "real_qloo_requests": 0, "error": error,
              "ci_gate": evaluation["ci_gate"] if evaluation else "NOT_VALIDATED",
              "notice": "Actual adapter calls are recorded. Synthetic controls are engineered demonstrations; they are not LLM or Qloo validation."}
    ledger.write("report.json", report)
    return report
