from __future__ import annotations

import json
from pathlib import Path
import re
from threading import RLock
from typing import Any

from .agents import SyntheticControlAdapter, execute_agent
from .config import load_config
from .errors import SchemaError
from .evaluation import compare_evaluations, evaluate_replay
from .evidence import Ledger, fingerprint
from .fixtures import FixtureTransport
from .qloo import QlooClient
from .spike import run_spike

RUN_ID = re.compile(r"\d{8}T\d{6}Z-[a-f0-9]{8}\Z")
ARTIFACTS = frozenset({"manifest.json", "report.json", "reference.json", "config.json", "agent-replay.json",
                       "evaluation.json", "regression.json"})


class RunStore:
    """Local append-only run store. HTTP clients supply run IDs, never filesystem paths."""
    def __init__(self, root: Path, config_path: Path, fixture_path: Path) -> None:
        self.root = root.resolve()
        self.config_path, self.fixture_path = config_path, fixture_path
        self.lock = RLock()
        self.root.mkdir(parents=True, exist_ok=True)

    def directory(self, run_id: str) -> Path:
        if not isinstance(run_id, str) or not RUN_ID.fullmatch(run_id):
            raise SchemaError("Invalid local run ID.")
        directory = self.root / run_id
        if directory.is_symlink() or directory.resolve().parent != self.root or not directory.is_dir():
            raise FileNotFoundError("Run not found")
        return directory

    def read(self, run_id: str, artifact: str) -> dict[str, Any]:
        if artifact not in ARTIFACTS:
            raise SchemaError("Artifact is not part of the public local contract.")
        path = self.directory(run_id) / artifact
        if path.is_symlink() or path.resolve().parent != self.root / run_id:
            raise SchemaError("Artifact leaves the local run directory.")
        if path.stat().st_size > 5 * 1024 * 1024:
            raise SchemaError("Artifact exceeds the local size limit.")
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise SchemaError("Damaged local artifact.")
        if artifact == "manifest.json":
            expected = fingerprint({key: item for key, item in value.items() if key != "manifest_id"})
            if value.get("manifest_id") != expected or value.get("run_id") != run_id:
                raise SchemaError("Local run manifest integrity check failed.")
        return value

    def manifest(self, ledger: Ledger, kind: str, status: str, gate: str, **data) -> dict[str, Any]:
        value = {"schema_version": 1, "run_id": ledger.run_id, "kind": kind, "status": status, "source": ledger.source,
                 "ci_gate": gate, "artifacts": sorted(path.name for path in ledger.directory.iterdir() if path.name in ARTIFACTS), **data}
        value["manifest_id"] = fingerprint(value)
        ledger.write("manifest.json", value)
        return value

    def list_runs(self) -> list[dict[str, Any]]:
        values = []
        for directory in sorted(self.root.iterdir(), reverse=True):
            if RUN_ID.fullmatch(directory.name) and (directory / "manifest.json").is_file():
                values.append(self.read(directory.name, "manifest.json"))
        return values

    def ledger(self, run_id: str) -> list[dict[str, Any]]:
        # Resolve a fixed filename; never accept a client-supplied path.
        self.read(run_id, "manifest.json")
        path = self.directory(run_id) / "ledger.jsonl"
        if path.is_symlink() or path.resolve().parent != self.root / run_id or path.stat().st_size > 5 * 1024 * 1024:
            raise SchemaError("Observable ledger leaves the run directory or exceeds the size limit.")
        events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        if any(not isinstance(event, dict) or event.get("sequence") != index for index, event in enumerate(events, 1)):
            raise SchemaError("Observable ledger sequence is invalid.")
        return events

    def synthetic_reference(self) -> dict[str, Any]:
        with self.lock:
            config = load_config(self.config_path)
            ledger = Ledger(self.root, "synthetic")
            client = QlooClient(FixtureTransport(self.fixture_path), ledger, synthetic=True)
            report = run_spike(client, config)
            return self.manifest(ledger, "reference", "FAILED" if report["error"] else "COMPLETED", report["feasibility_gate"],
                                 reference_bundle_id=report["reference_bundle_id"], real_qloo_requests=0)

    def reference(self, run_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
        manifest = self.read(run_id, "manifest.json")
        if manifest["kind"] != "reference" or manifest["status"] != "COMPLETED":
            raise SchemaError("A completed reference run is required.")
        reference, config = self.read(run_id, "reference.json"), self.read(run_id, "config.json")
        if reference["reference_bundle_id"] != manifest["reference_bundle_id"] or reference.get("config_sha256") != fingerprint(config):
            raise SchemaError("Reference/config does not match its captured manifest.")
        return reference, config

    def control(self, reference_run_id: str, behavior: str) -> dict[str, Any]:
        with self.lock:
            reference, config = self.reference(reference_run_id)
            if reference["source"] != "synthetic":
                raise SchemaError("The API's engineered controls require an explicitly synthetic reference.")
            adapter = SyntheticControlAdapter(behavior)
            ledger = Ledger(self.root, reference["source"])
            report = execute_agent(reference, config, adapter, ledger)
            return self.manifest(ledger, "agent", report["execution_status"], report["ci_gate"],
                                 reference_run_id=reference_run_id, reference_bundle_id=reference["reference_bundle_id"],
                                 agent_name=adapter.name, agent_version=adapter.version, agent_source=adapter.source,
                                 real_qloo_requests=0)

    def replay(self, reference_run_id: str, name: str, version: str, cases: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            reference, config = self.reference(reference_run_id)
            replay = {"schema_version": 1, "source": "user-replay", "agent_name": name, "agent_version": version,
                      "reference_bundle_id": reference["reference_bundle_id"], "cases": cases}
            evaluation = evaluate_replay(reference, replay, config["thresholds"])
            ledger = Ledger(self.root, reference["source"])
            ledger.write("agent-replay.json", replay)
            ledger.write("evaluation.json", evaluation)
            ledger.record("replay_evaluated", {"evaluation_id": evaluation["evaluation_id"], "reference_run_id": reference_run_id})
            return self.manifest(ledger, "replay", "COMPLETED", evaluation["ci_gate"], reference_run_id=reference_run_id,
                                 reference_bundle_id=reference["reference_bundle_id"], agent_name=name, agent_version=version,
                                 agent_source="user-replay", real_qloo_requests=0)

    def compare(self, baseline_run_id: str, candidate_run_id: str) -> dict[str, Any]:
        with self.lock:
            for run_id in (baseline_run_id, candidate_run_id):
                manifest = self.read(run_id, "manifest.json")
                if manifest["kind"] not in ("agent", "replay") or manifest["status"] != "COMPLETED":
                    raise SchemaError("Comparison needs two completed agent/replay runs.")
            baseline, candidate = self.read(baseline_run_id, "evaluation.json"), self.read(candidate_run_id, "evaluation.json")
            max_drop = baseline["thresholds"]["max_fidelity_drop"]
            report = compare_evaluations(baseline, candidate, max_drop)
            ledger = Ledger(self.root, report["source"])
            ledger.write("regression.json", report)
            ledger.record("regression_compared", {"baseline_run_id": baseline_run_id, "candidate_run_id": candidate_run_id,
                                                   "ci_gate": report["ci_gate"]})
            return self.manifest(ledger, "comparison", "COMPLETED", report["ci_gate"], baseline_run_id=baseline_run_id,
                                 candidate_run_id=candidate_run_id, cultural_regression_detected=report["cultural_regression_detected"],
                                 real_qloo_requests=0)
