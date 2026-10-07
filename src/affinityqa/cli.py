from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

from .config import load_config
from .errors import AffinityQAError, SchemaError
from .evaluation import compare_evaluations, evaluate_replay
from .evidence import Ledger
from .fixtures import FixtureTransport
from .qloo import LiveTransport, QlooClient, Settings
from .spike import run_spike
from .agents import LocalHttpJsonAdapter, ProcessJsonAdapter, execute_agent
from .access import probe_access
from .film_protocol import capture_movie_pilot, import_lookup_samples, load_suite

_SOURCE_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = _SOURCE_ROOT if (_SOURCE_ROOT / "evals/qloo.json").exists() else Path.cwd()


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(prog="affinityqa", description="Test whether personalization actually changes the decision.")
    sub = cli.add_subparsers(dest="command", required=True)
    doctor = sub.add_parser("doctor", help="Show readiness without displaying secrets or calling Qloo.")
    doctor.add_argument("--env-file", type=Path, default=PROJECT_ROOT / ".env")
    access = sub.add_parser("access-probe", help="One Qloo request after confirming the local key was issued by Qloo.")
    access.add_argument("--env-file", type=Path, default=PROJECT_ROOT / ".env")
    access.add_argument("--credential-issued-by-qloo", action="store_true")
    access.add_argument("--out", type=Path, default=PROJECT_ROOT / "runs")
    pilot = sub.add_parser("movie-pilot", help="Capture one-signal references over an independently selected movie catalog.")
    pilot.add_argument("--suite", type=Path, default=PROJECT_ROOT / "evals/film-suite.json")
    pilot.add_argument("--env-file", type=Path, default=PROJECT_ROOT / ".env")
    pilot.add_argument("--credential-issued-by-qloo", action="store_true")
    pilot.add_argument("--max-requests", type=int, default=30)
    pilot.add_argument("--reuse-lookups-from", type=Path, help="Reuse verified local entity lookups, never affinity rankings.")
    pilot.add_argument("--out", type=Path, default=PROJECT_ROOT / "runs")
    incident = sub.add_parser("movie-incident", help="Run a real local model, an explicit cache fault and one bounded repair on the development pilot.")
    incident.add_argument("--reference", type=Path, required=True)
    incident.add_argument("--suite", type=Path, required=True)
    incident.add_argument("--ollama-url", required=True, help="Explicit numeric interface of this computer; never a remote model endpoint.")
    incident.add_argument("--model", required=True, help="An already installed local model; no downloads.")
    incident.add_argument("--model-timeout", type=float, default=30, help="Bounded local inference timeout, at most 45 seconds.")
    incident.add_argument("--out", type=Path, default=PROJECT_ROOT / "runs")
    local_suite = sub.add_parser("local-suite", help="Freeze local development calibration, then execute all six reserved pairs without new Qloo calls.")
    local_suite.add_argument("--catalog-reference", type=Path, required=True)
    local_suite.add_argument("--suite", type=Path, required=True)
    local_suite.add_argument("--ollama-url", required=True)
    local_suite.add_argument("--model", required=True)
    local_suite.add_argument("--model-timeout", type=float, default=45)
    local_suite.add_argument("--max-model-calls", type=int, default=98)
    local_suite.add_argument("--out", type=Path, default=PROJECT_ROOT / "runs")
    reserved = sub.add_parser("reserved-reference", help="Capture six reserved Qloo references and compare sealed local decisions; no model calls.")
    reserved.add_argument("--local-run", type=Path, required=True)
    reserved.add_argument("--verification", type=Path, required=True)
    reserved.add_argument("--env-file", type=Path, default=PROJECT_ROOT / ".env")
    reserved.add_argument("--credential-issued-by-qloo", action="store_true")
    reserved.add_argument("--max-requests", type=int, default=49)
    reserved.add_argument("--out", type=Path, default=PROJECT_ROOT / "runs")
    context_capture = sub.add_parser("context-capture", help="Capture disjoint context and references for two development pairs; 21 requests maximum.")
    context_capture.add_argument("--local-run", type=Path, required=True)
    context_capture.add_argument("--verification", type=Path, required=True)
    context_capture.add_argument("--study", type=Path, default=PROJECT_ROOT / "evals/context-study-v1.json")
    context_capture.add_argument("--env-file", type=Path, default=PROJECT_ROOT / ".env")
    context_capture.add_argument("--credential-issued-by-qloo", action="store_true")
    context_capture.add_argument("--out", type=Path, default=PROJECT_ROOT / "runs")
    context_eval = sub.add_parser("context-eval", help="Compare four model variants against captured development references; no Qloo calls.")
    context_eval.add_argument("--capture-run", type=Path, required=True)
    context_eval.add_argument("--ollama-url", required=True)
    context_eval.add_argument("--model", required=True)
    context_eval.add_argument("--candidate-index", type=int, choices=(1,2), default=1)
    context_eval.add_argument("--out", type=Path, default=PROJECT_ROOT / "runs")
    spike = sub.add_parser("spike", help="Run the controlled Qloo feasibility experiment.")
    spike.add_argument("--mode", choices=("synthetic", "live"), required=True)
    spike.add_argument("--config", type=Path, default=PROJECT_ROOT / "evals/qloo.json")
    spike.add_argument("--fixture", type=Path, default=PROJECT_ROOT / "fixtures/synthetic.json")
    spike.add_argument("--env-file", type=Path, default=PROJECT_ROOT / ".env")
    spike.add_argument("--out", type=Path, default=PROJECT_ROOT / "runs")
    spike.add_argument("--max-requests", type=int, default=60)
    spike.add_argument("--credential-issued-by-qloo", action="store_true")
    evaluation = sub.add_parser("eval", help="Evaluate structured observable decisions against a frozen reference.")
    evaluation.add_argument("reference", type=Path)
    evaluation.add_argument("agent", type=Path)
    evaluation.add_argument("--config", type=Path, default=PROJECT_ROOT / "evals/qloo.json")
    evaluation.add_argument("--out", type=Path, default=PROJECT_ROOT / "runs")
    comparison = sub.add_parser("compare", help="Detect a regression between two agent versions on the same oracle.")
    comparison.add_argument("baseline", type=Path)
    comparison.add_argument("candidate", type=Path)
    comparison.add_argument("--max-fidelity-drop", type=float, default=0.05)
    comparison.add_argument("--out", type=Path, default=PROJECT_ROOT / "runs")
    pack = sub.add_parser("regression-export", help="Export a verified local regression pack; no provider or model calls.")
    pack.add_argument("--baseline", choices=("candidate","repaired"), default="repaired")
    pack.add_argument("--case", action="append", dest="case_ids")
    pack.add_argument("--max-profile-drop", type=float, default=0)
    pack.add_argument("--output", type=Path, required=True)
    check = sub.add_parser("regression-check", help="Check complete independently executed decisions against a local pack.")
    check.add_argument("--pack", type=Path, required=True)
    check.add_argument("--decisions", type=Path, required=True)
    check.add_argument("--output", type=Path, required=True)
    repair_export = sub.add_parser("repair-export", help="Export all six verified repair cases and sealed candidate decisions; evaluator-only local files.")
    repair_export.add_argument("--directory", type=Path, required=True, help="New directory; existing files are never overwritten.")
    repair_check = sub.add_parser("repair-check", help="Recompute every frozen repair control and retain baseline if any case fails; no deployment.")
    repair_check.add_argument("--contract", type=Path, required=True)
    repair_check.add_argument("--decisions", type=Path, required=True)
    repair_check.add_argument("--output", type=Path, required=True)
    execution = sub.add_parser("execute", help="Run a trusted local agent on observable inputs, without exposing reference answers.")
    execution.add_argument("--reference", type=Path, required=True)
    execution.add_argument("--config", type=Path, default=PROJECT_ROOT / "evals/qloo.json")
    execution.add_argument("--agent-name", required=True)
    execution.add_argument("--agent-version", required=True)
    execution.add_argument("--adapter", choices=("process-json", "local-http-json"), required=True)
    execution.add_argument("--url", help="Explicit numeric loopback HTTP endpoint for local-http-json.")
    execution.add_argument("--timeout", type=float, default=15)
    execution.add_argument("--cwd", type=Path, default=PROJECT_ROOT)
    execution.add_argument("--out", type=Path, default=PROJECT_ROOT / "runs")
    execution.add_argument("agent_command", nargs=argparse.REMAINDER, help="Trusted executable and arguments after -- (process-json only).")
    server = sub.add_parser("serve", help="Start the optional FastAPI backend on numeric loopback only.")
    server.add_argument("--port", type=int, default=8765)
    server.add_argument("--store", type=Path, default=PROJECT_ROOT / "runs/backend")
    server.add_argument("--live-local-enabled", action="store_true", help="Enable only the fixed Sade/NIN local incident and profile-cache repair.")
    server.add_argument("--ollama-url", help="Numeric address of this computer's installed Ollama server.")
    server.add_argument('--individual-template', type=Path, help='Explicit request template with 20 movie identities and reviewed operator; no historical defaults.')
    server.add_argument('--individual-provider', choices=('local', 'groq'), default='local', help='Server-owned operator; separate local v1 or remote v2 template.')
    server.add_argument('--individual-output', type=Path, default=PROJECT_ROOT/'runs/individual-panel', help='Owner-selected new or inspected private job storage.')
    server.add_argument('--individual-local-enabled', action='store_true', help='Allow explicitly reviewed new individual plans to execute on this PC.')
    server.add_argument('--individual-remote-enabled', action='store_true', help='Allow explicitly reviewed new individual plans to call the remote provider.')
    server.add_argument('--remote-model-minimum-interval', type=float,
                        help='Owner-reviewed remote dispatch interval (0-65 seconds); required to enable real remote execution.')
    server.add_argument('--groq-env-file', type=Path, help='Private remote provider file, read only at deliberate execution; no key in command arguments.')
    server.add_argument('--env-file', type=Path, help='Local Qloo credential file, read only at deliberate execution.')
    return cli


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise SchemaError("Expected a JSON object.")
    return value


def emit(value: dict) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=True, allow_nan=False), flush=True)


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "repair-export":
            from .repair_gate import load_recorded_validation
            contract, decisions, report, _ = load_recorded_validation(PROJECT_ROOT)
            args.directory.mkdir(parents=True, exist_ok=False)
            for name, value in (("contract.json",contract),("candidate-decisions.json",decisions)):
                with (args.directory/name).open("x",encoding="utf-8") as handle:
                    json.dump(value,handle,indent=2,ensure_ascii=False,allow_nan=False)
                    handle.write("\n")
            emit({"directory":str(args.directory),"cases":6,"sample_gate":report['sample_gate'],
                  "new_qloo_requests":0,"new_model_calls":0,"evaluator_only":True})
            return 0
        if args.command == "repair-check":
            from .repair_gate import evaluate_repair
            result=evaluate_repair(read_json(args.contract),read_json(args.decisions))
            args.output.parent.mkdir(parents=True,exist_ok=True)
            with args.output.open("x",encoding="utf-8") as handle:
                json.dump(result,handle,indent=2,ensure_ascii=False,allow_nan=False)
                handle.write("\n")
            emit({k:v for k,v in result.items() if k not in ('cases','selected_decisions')})
            return 0 if result['sample_gate']=='PASS' else 1
        if args.command in ("regression-export","regression-check"):
            from .regression_pack import export_pack, evaluate_pack
            result = (export_pack(PROJECT_ROOT, baseline=args.baseline, case_ids=args.case_ids,
                                  max_profile_drop=args.max_profile_drop)
                      if args.command == "regression-export" else evaluate_pack(read_json(args.pack),read_json(args.decisions)))
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x", encoding="utf-8") as handle:
                json.dump(result,handle,indent=2,ensure_ascii=False,allow_nan=False)
                handle.write("\n")
            emit({"artifact":str(args.output),"regression_gate":result.get("regression_gate","EXPORTED"),
                  "ci_gate":"NOT_VALIDATED","new_qloo_requests":0,"new_model_calls":0})
            return 1 if result.get("regression_gate") != "PASS" and args.command == "regression-check" else 0
        if args.command in ("access-probe", "movie-pilot"):
            if not args.credential_issued_by_qloo:
                emit({"status": "BLOCKED_PROVENANCE", "network_requests": 0,
                      "message": "Confirm the local credential was issued by Qloo; never send an Apertus or other-service key."})
                return 2
            suite = load_suite(args.suite) if args.command == "movie-pilot" else None
            if args.command == "movie-pilot" and not 1 <= args.max_requests <= 40:
                raise SchemaError("The movie pilot request cap must be 1..40; no bulk suite is run.")
            # The user selected this file; a stale global environment key cannot override it.
            settings = Settings.from_environment(args.env_file, use_process_environment=False)
            if not settings.api_key.strip():
                emit({"status": "BLOCKED_KEY", "network_requests": 0, "message": "Save a Qloo-issued key in the selected local file."})
                return 2
            ledger = Ledger(args.out, "qloo-live", (settings.api_key,))
            client = QlooClient(LiveTransport(settings), ledger, max_requests=1 if args.command == "access-probe" else args.max_requests,
                                max_attempts=1)
            if suite is not None and args.reuse_lookups_from:
                import_lookup_samples(client, args.reuse_lookups_from)
            report = probe_access(client) if suite is None else capture_movie_pilot(client, suite)
            gate_name = "access_gate" if suite is None else "reference_gate"
            emit({"report": str(ledger.directory / ("access-report.json" if suite is None else "report.json")),
                  gate_name: report[gate_name], "ci_gate": report["ci_gate"],
                  "real_qloo_requests": report["real_qloo_requests"], "error": report["error"]})
            return 0 if report[gate_name] == "PASS" else 2
        if args.command == "doctor":
            settings = Settings.from_environment(args.env_file)
            emit({"project": "AffinityQA", "key_configured": bool(settings.api_key.strip()),
                  "qloo_host": settings.base_url, "real_qloo_test": "NOT_RUN", "network_requests": 0})
            return 0
        if args.command == "context-capture":
            from .reserved_reference import load_sealed_run
            from .context_study import capture_context_study, validate_study
            if not args.credential_issued_by_qloo:
                emit({"status": "BLOCKED_PROVENANCE", "network_requests": 0})
                return 2
            values = load_sealed_run(args.local_run, args.verification)
            study = read_json(args.study)
            validate_study(study, values[2])
            settings = Settings.from_environment(args.env_file, use_process_environment=False)
            transport = LiveTransport(settings)
            ledger = Ledger(args.out, "qloo-live-context-development", (settings.api_key,))
            client = QlooClient(transport, ledger, max_requests=21, max_attempts=1)
            report = capture_context_study(client, values, study,
                progress=lambda pair, count: emit({"pair_id": pair, "qloo_requests_so_far": count, "request_cap": 21}))
            emit({"report": str(ledger.directory / "capture-report.json"), **report})
            return 0 if report["status"] == "COMPLETE_CONTEXT_CAPTURE" else 2
        if args.command == "context-eval":
            from .context_study import evaluate_context_study, validate_study
            from .context_agent import ContextMovieAgent, ContextReviewAgent
            from .ollama_agent import OllamaMovieAgent
            from .evidence import fingerprint
            capture = read_json(args.capture_run / "capture-report.json")
            bundle = read_json(args.capture_run / "context-bundle.json")
            study = read_json(args.capture_run / "study.json")
            suite = read_json(args.capture_run / "suite.json")
            plan = read_json(args.capture_run / "capture-plan.json")
            if (capture.get("status") != "COMPLETE_CONTEXT_CAPTURE" or capture.get("bundle_sha256") != bundle.get("bundle_sha256")
                    or bundle.get("bundle_sha256") != fingerprint({k:v for k,v in bundle.items() if k != "bundle_sha256"})
                    or plan.get("plan_sha256") != fingerprint({k:v for k,v in plan.items() if k != "plan_sha256"})
                    or plan.get("suite_sha256") != fingerprint(suite) or plan.get("study_sha256") != fingerprint(study)
                    or bundle.get("plan_sha256") != plan.get("plan_sha256")):
                raise SchemaError("Context capture integrity failed before local inference.")
            validate_study(study, suite)
            original = OllamaMovieAgent(args.ollama_url, args.model, timeout=45, max_calls=12)
            contextual_class = ContextMovieAgent if args.candidate_index == 1 else ContextReviewAgent
            contextual = contextual_class(args.ollama_url, args.model, timeout=45, max_calls=36)
            ledger = Ledger(args.out, "qloo-context+local-llm")
            emit({"phase":"context-ablation", "inference_cap":48, "new_qloo_requests":0})
            report = evaluate_context_study(original, contextual, ledger, bundle, suite, study, candidate_index=args.candidate_index,
                progress=lambda pair, variant, call: emit({"pair_id":pair,"variant":variant,"local_inference_call":call}))
            emit({"report":str(ledger.directory / "context-ablation.json"),
                  **{key:report[key] for key in ("status","candidate_gate","local_inference_attempts","error")}})
            return 0 if report["status"] == "COMPLETE_CONTEXT_ABLATION" else 2
        if args.command == "reserved-reference":
            from .reserved_reference import load_sealed_run, capture_reserved
            if not args.credential_issued_by_qloo:
                emit({"status": "BLOCKED_PROVENANCE", "network_requests": 0})
                return 2
            if args.max_requests != 49:
                raise SchemaError("This fixed reserved capture requires an exact 49-request cap.")
            values = load_sealed_run(args.local_run, args.verification)
            settings = Settings.from_environment(args.env_file, use_process_environment=False)
            transport = LiveTransport(settings)
            ledger = Ledger(args.out, "qloo-live-reserved-evaluation", (settings.api_key,))
            client = QlooClient(transport, ledger, max_requests=49, max_attempts=1)
            report = capture_reserved(client, ledger, *values,
                progress=lambda pair, count: emit({"pair_id": pair, "qloo_requests_so_far": count, "request_cap": 49}))
            emit({"report": str(ledger.directory / "reserved-comparison.json"),
                  **{key: report[key] for key in ("status", "denominator", "outcome_counts", "real_qloo_requests", "ci_gate", "error")}})
            return 0 if report["status"] == "COMPLETE_RESERVED_COMPARISON" else 2
        if args.command == "movie-incident":
            from .movie_incident import movie_requests, run_movie_incident
            from .ollama_agent import OllamaMovieAgent
            reference, suite = read_json(args.reference), load_suite(args.suite)
            movie_requests(reference, suite)  # Validate bindings before contacting the local model.
            engine = OllamaMovieAgent(args.ollama_url, args.model, timeout=args.model_timeout)
            ledger = Ledger(args.out, "qloo-live+local-llm")
            report = run_movie_incident(engine, ledger, reference, suite,
                progress=lambda phase, call: emit({"phase": phase, "local_inference_call": call, "new_qloo_requests": 0}))
            emit({"report": str(ledger.directory / "incident-report.json"), "incident_gate": report["incident_gate"],
                  "repair_gate": report["repair_gate"], "ci_gate": report["ci_gate"],
                  "local_inference_calls": report["local_inference_calls"], "new_qloo_requests": 0, "error": report["error"]})
            return 0 if report["repair_gate"] == "OBSERVED_DEVELOPMENT_REPAIR" else 2
        if args.command == "local-suite":
            from .movie_incident import movie_requests
            from .local_suite import run_local_suite
            from .ollama_agent import OllamaMovieAgent
            reference, suite = read_json(args.catalog_reference), load_suite(args.suite)
            movie_requests(reference, suite)
            if not 98 <= args.max_model_calls <= 110:
                raise SchemaError("The full local suite requires an explicit 98..110 inference budget.")
            engine = OllamaMovieAgent(args.ollama_url, args.model, timeout=args.model_timeout, max_calls=args.max_model_calls)
            ledger = Ledger(args.out, "qloo-catalog+local-llm")
            emit({"phase": "model_preload", "load_timeout_seconds": 120, "inference_calls": 0})
            try:
                readiness = engine.warmup()
            except AffinityQAError as exc:
                readiness = {"status": "NOT_READY", "error": str(exc), "inference_calls": 0, "new_qloo_requests": 0}
                ledger.write("model-readiness.json", readiness)
                ledger.write("agent-manifest.json", engine.manifest)
                report = {"status": "INCOMPLETE", "phase": "model_preload", "ci_gate": "NOT_VALIDATED",
                          "local_inference_attempts": 0, "new_qloo_requests": 0, "error": str(exc)}
                ledger.write("suite-report.json", report)
                emit({"report": str(ledger.directory / "suite-report.json"), **report})
                return 2
            ledger.write("model-readiness.json", readiness)
            ledger.record("model_readiness", readiness)
            emit(readiness)
            report = run_local_suite(engine, ledger, reference, suite,
                progress=lambda phase, pair, call: emit({"phase": phase, "pair_id": pair, "local_inference_call": call, "new_qloo_requests": 0}))
            emit({"report": str(ledger.directory / "suite-report.json"), "status": report["status"],
                  "structural_passes": report.get("structural_passes"), "sensitivity_recoveries": report.get("sensitivity_recoveries"),
                  "denominator": report.get("denominator"), "ci_gate": report["ci_gate"],
                  "local_inference_attempts": report["local_inference_attempts"], "error": report["error"]})
            return 0 if report["status"] == "COMPLETE_LOCAL_SUITE" else 2
        if args.command == "spike":
            if not 1 <= args.max_requests <= 100:
                raise SchemaError("max-requests must be from 1 to 100; this is not a load test.")
            config = load_config(args.config)
            if args.mode == "live":
                settings = Settings.from_environment(args.env_file, use_process_environment=False)
                if not settings.api_key.strip():
                    emit({"feasibility_gate": "BLOCKED_KEY", "source": "qloo-live", "real_qloo_requests": 0,
                          "message": "Configure QLOO_API_KEY locally in .env after your request is approved."})
                    return 2
                if not args.credential_issued_by_qloo:
                    emit({"status": "BLOCKED_PROVENANCE", "network_requests": 0,
                          "message": "Confirm that the selected local credential was issued by Qloo before sending it."})
                    return 2
                ledger = Ledger(args.out, "qloo-live", (settings.api_key,))
                transport = LiveTransport(settings)
            else:
                ledger = Ledger(args.out, "synthetic")
                transport = FixtureTransport(args.fixture)
            client = QlooClient(transport, ledger, synthetic=args.mode == "synthetic", max_requests=args.max_requests)
            report = run_spike(client, config)
            emit({"report": str(ledger.directory / "report.json"), "source": report["source"],
                  "feasibility_gate": report["feasibility_gate"], "real_qloo_requests": report["real_qloo_requests"],
                  "synthetic_engineering_controls": report.get("controls"), "error": report["error"]})
            # Synthetic success means the engineering harness ran, never that Qloo passed.
            return 0 if not report["error"] and (args.mode == "synthetic" or report["feasibility_gate"] == "PASS") else 2
        if args.command == "eval":
            config = load_config(args.config)
            report = evaluate_replay(read_json(args.reference), read_json(args.agent), config["thresholds"])
            ledger = Ledger(args.out, report["source"])
            ledger.write("evaluation.json", report)
            emit({"evaluation": str(ledger.directory / "evaluation.json"), "ci_gate": report["ci_gate"]})
            return 0 if report["ci_gate"] == "PASS" else (1 if report["ci_gate"] == "FAIL" else 2)
        if args.command == "compare":
            if not math.isfinite(args.max_fidelity_drop) or not 0 <= args.max_fidelity_drop < 1:
                raise SchemaError("max-fidelity-drop must be finite and in [0,1).")
            report = compare_evaluations(read_json(args.baseline), read_json(args.candidate), args.max_fidelity_drop)
            ledger = Ledger(args.out, report["source"])
            ledger.write("regression.json", report)
            emit({"regression": str(ledger.directory / "regression.json"), "ci_gate": report["ci_gate"],
                  "cultural_regression_detected": report["cultural_regression_detected"]})
            return 0 if report["ci_gate"] == "PASS" else (1 if report["ci_gate"] == "FAIL" else 2)
        if args.command == "execute":
            config = load_config(args.config)
            reference = read_json(args.reference)
            command = args.agent_command[1:] if args.agent_command[:1] == ["--"] else args.agent_command
            if args.adapter == "process-json":
                if args.url:
                    raise SchemaError("A process adapter does not use --url.")
                adapter = ProcessJsonAdapter(args.agent_name, args.agent_version, command, cwd=args.cwd, timeout=args.timeout)
            else:
                if command or not args.url:
                    raise SchemaError("A local HTTP adapter needs --url and no executable arguments.")
                adapter = LocalHttpJsonAdapter(args.agent_name, args.agent_version, args.url, timeout=args.timeout)
            ledger = Ledger(args.out, reference.get("source", "unknown"))
            report = execute_agent(reference, config, adapter, ledger)
            emit({"report": str(ledger.directory / "report.json"), "execution_status": report["execution_status"],
                  "agent_calls": report["agent_calls"], "ci_gate": report["ci_gate"], "real_qloo_requests": 0,
                  "error": report["error"]})
            return 0 if report["ci_gate"] == "PASS" else (1 if report["ci_gate"] == "FAIL" else 2)
        if args.command == "serve":
            if not 1024 <= args.port <= 65535:
                raise SchemaError("Local preview port must be from 1024 to 65535.")
            try:
                import uvicorn
                from .api import create_app
            except ImportError:
                raise SchemaError("Install the optional backend dependencies in an isolated environment: pip install -e .[backend].") from None
            live_manager=None
            individual_manager=None
            if args.individual_local_enabled and not args.individual_template:
                raise SchemaError('New local execution needs an explicit individual template.')
            if args.individual_remote_enabled and (not args.individual_template or args.individual_provider!='groq'
                    or not args.groq_env_file or not args.env_file or args.remote_model_minimum_interval is None):
                raise SchemaError('Remote execution needs its v2 template, Groq operator, reviewed interval and two explicit private credential file paths.')
            if args.remote_model_minimum_interval is not None and (args.individual_provider!='groq' or not args.individual_template):
                raise SchemaError('Remote pacing needs the explicit Groq operator and its template.')
            if args.individual_provider=='groq' and (args.individual_local_enabled or args.live_local_enabled or args.ollama_url):
                raise SchemaError('The remote operator cannot be mixed with local inference configuration.')
            if args.individual_template:
                if args.live_local_enabled:
                    raise SchemaError('Use one local execution manager at a time.')
                if args.individual_provider=='local' and not args.ollama_url:
                    raise SchemaError('An explicit loopback Ollama address is required.')
                from .individual_jobs import IndividualJobManager
                if args.individual_provider=='groq':
                    from .individual_remote_capture import read_request, load_private_credential
                    individual_manager=IndividualJobManager(args.individual_output, read_request(args.individual_template), operator='groq',
                        execution_enabled=args.individual_remote_enabled,
                        remote_minimum_interval_seconds=args.remote_model_minimum_interval,
                        settings_loader=lambda:Settings.from_environment(args.env_file, use_process_environment=False),
                        remote_key_loader=lambda:load_private_credential(args.groq_env_file))
                else:
                    from .individual_capture import read_request
                    individual_manager=IndividualJobManager(args.individual_output, read_request(args.individual_template), args.ollama_url,
                        execution_enabled=args.individual_local_enabled,
                        settings_loader=lambda:Settings.from_environment(args.env_file, use_process_environment=False))
            if args.live_local_enabled:
                if not args.ollama_url:raise SchemaError('An explicit local Ollama address is required for live execution.')
                from .live_jobs import LiveJobManager
                live_manager=LiveJobManager(PROJECT_ROOT,args.ollama_url)
            try:
                uvicorn.run(create_app(PROJECT_ROOT, store_root=args.store, live_manager=live_manager,
                            individual_manager=individual_manager), host="127.0.0.1", port=args.port,
                            access_log=False, proxy_headers=False, server_header=False)
            finally:
                if individual_manager:
                    individual_manager.close()
            return 0
    except AffinityQAError as exc:
        emit({"status": "ERROR", "message": str(exc)})
        return 2
    except (OSError, ValueError, KeyError, TypeError):
        emit({"status": "ERROR", "message": "Invalid or unreadable input. No quality gate passed; review the input schema."})
        return 2
    return 2

