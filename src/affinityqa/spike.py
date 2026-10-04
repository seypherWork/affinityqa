from __future__ import annotations

from itertools import product
import statistics
from typing import Any

from .errors import AffinityQAError, SchemaError
from .evaluation import METRIC_VERSION, compare_evaluations, evaluate_replay
from .evidence import fingerprint
from .metrics import max_repeat_jitter, rank_distance, top_k_overlap
from .models import context_issues, parse_entities, resolve_seed
from .qloo import QlooClient


def run_case(client: QlooClient, scenario: dict[str, Any], config: dict[str, Any],
             personas: dict[str, list[str]]) -> dict[str, Any]:
    excluded = sorted(set(personas["A"] + personas["B"]))
    fixed_params = {"filter.type": scenario["filter_type"], "bias.trends": "off",
                    "filter.exclude.entities": ",".join(excluded), **scenario["filters"]}
    candidates = set()
    for persona in ("A", "B"):
        params = {**fixed_params, "signal.interests.entities": ",".join(personas[persona]), "take": config["discovery_take"]}
        entities = parse_entities(client.get("/v2/insights", params), insights=True, synthetic=client.synthetic)
        if len(entities) < config["top_k"]:
            raise SchemaError("Qloo returned fewer than top_k entities; an empty/short result cannot validate personalization.")
        issues = context_issues(entities, scenario, set(excluded))
        if issues:
            raise SchemaError("Discovery context could not be verified: " + "; ".join(issues[:5]))
        candidates.update(entity.entity_id for entity in entities)
    candidate_ids = sorted(candidates)
    if len(candidate_ids) > 50:
        raise SchemaError("Candidate pool exceeds the documented take limit; do not silently truncate it.")
    lookup = parse_entities(client.get("/entities", {"entity_ids": ",".join(candidate_ids)}), insights=False, synthetic=client.synthetic)
    if {entity.entity_id for entity in lookup} != candidates:
        raise SchemaError("The fixed catalog did not resolve completely through /entities.")
    issues = context_issues(lookup, scenario, set(excluded))
    if issues:
        raise SchemaError("Catalog context could not be verified: " + "; ".join(issues[:5]))
    fixed_params.update({"filter.results.entities": ",".join(candidate_ids), "take": len(candidate_ids)})
    rankings: dict[str, list[list[str]]] = {"A": [], "B": []}
    affinity_observed = []
    # Interleave A/B to avoid conflating persona effect with a time-ordered backend change.
    for repeat in range(config["repeats"]):
        for persona in ("A", "B"):
            params = {**fixed_params, "signal.interests.entities": ",".join(personas[persona])}
            entities = parse_entities(client.get("/v2/insights", params, cache=False), insights=True, synthetic=client.synthetic)
            ids = [entity.entity_id for entity in entities]
            if set(ids) != candidates or len(ids) != len(candidates):
                raise SchemaError("Qloo did not return a complete fixed-catalog ranking. Missing candidates are unknown, not irrelevant.")
            issues = context_issues(entities, scenario, set(excluded))
            if issues:
                raise SchemaError("Ranking context could not be verified: " + "; ".join(issues[:5]))
            rankings[persona].append(ids)
            affinity_observed.append({"persona": persona, "repeat": repeat + 1,
                                      "with_affinity": sum(entity.affinity is not None for entity in entities),
                                      "total": len(entities)})
    k = config["top_k"]
    deltas = [rank_distance(a, b, k) for a, b in product(rankings["A"], rankings["B"])]
    jitter = max(max_repeat_jitter(rankings["A"], k), max_repeat_jitter(rankings["B"], k))
    minimum_delta = min(deltas)
    thresholds = config["thresholds"]
    if jitter > thresholds["max_reference_jitter"]:
        verdict = "UNSTABLE_REFERENCE"
    elif minimum_delta > jitter + thresholds["reference_margin"]:
        verdict = "MEASURABLE_MUTATION"
    else:
        verdict = "NO_MEASURABLE_SHIFT"
    reference = {"case_id": scenario["id"], "required": scenario["required"], "task": scenario["task"],
                 "filter_type": scenario["filter_type"], "constraints": scenario["filters"],
                 "task_fingerprint": fingerprint({"task": scenario["task"], "params": fixed_params}),
                 "candidate_ids": candidate_ids, "entities": [entity.as_dict() for entity in lookup],
                 "rankings": rankings, "top_k": k, "reference_delta": minimum_delta,
                 "reference_delta_mean": statistics.mean(deltas), "reference_jitter": jitter,
                 "reference_top_k_overlap": top_k_overlap(rankings["A"][0], rankings["B"][0], k),
                 "reference_verdict": verdict, "affinity_observed": affinity_observed,
                 "source": "synthetic" if client.synthetic else "qloo-live", "metric_version": METRIC_VERSION,
                 "context_compliance": 1.0, "catalog_resolved_through_entities": True}
    reference["reference_id"] = fingerprint(reference)
    client.ledger.record("reference_measurement", {key: reference[key] for key in
                         ("case_id", "task_fingerprint", "reference_id", "reference_delta", "reference_jitter", "reference_verdict")})
    return reference


def replay_template(references: dict[str, Any], *, insensitive: bool) -> dict[str, Any]:
    return {"schema_version": 1, "source": "synthetic-control", "agent_name": "controlled-test-agent",
            "agent_version": "v2-insensitive" if insensitive else "v1-oracle-copy-positive-control",
            "reference_bundle_id": references["reference_bundle_id"],
            "notice": "Engineered control, not a measured or repaired LLM. Replace with observable agent decisions for a user-replay evaluation.",
            "cases": {case["case_id"]: {"A": case["rankings"]["A"][0],
                                        "B": case["rankings"]["A" if insensitive else "B"][0]}
                      for case in references["cases"]}}


def run_spike(client: QlooClient, config: dict[str, Any]) -> dict[str, Any]:
    ledger = client.ledger
    ledger.write("config.json", config)
    personas = {"A": [], "B": []}
    cases = []
    error = None
    try:
        for label, seeds in config["personas"].items():
            for seed in seeds:
                if seed.get("entity_id"):
                    body = client.get("/entities", {"entity_ids": seed["entity_id"]})
                else:
                    body = client.get("/search", {"query": seed["query"], "types": seed["search_type"], "take": 10})
                entity = resolve_seed(seed, parse_entities(body, insights=False, synthetic=client.synthetic), synthetic=client.synthetic)
                if entity.entity_id in personas[label]:
                    raise SchemaError("Two persona seeds resolved to the same entity; review the interests.")
                personas[label].append(entity.entity_id)
                ledger.record("entity_resolution", {"persona": label, "seed": seed["name"], "entity": entity.as_dict()})
        if set(personas["A"]) == set(personas["B"]):
            raise SchemaError("A and B resolve to the same taste profile.")
        for scenario in config["scenarios"]:
            cases.append(run_case(client, scenario, config, personas))
    except AffinityQAError as exc:
        error = str(exc)
        ledger.record("stopped", {"reason": error, "completed_cases": len(cases)})
    required_ids = {scenario["id"] for scenario in config["scenarios"] if scenario["required"]}
    required_cases = [case for case in cases if case["required"]]
    core_pass = ({case["case_id"] for case in required_cases} == required_ids
                 and all(case["reference_verdict"] == "MEASURABLE_MUTATION" for case in required_cases) and not error)
    gate = "NOT_VALIDATED" if client.synthetic else ("PASS" if core_pass else "INCONCLUSIVE")
    references = {"schema_version": 1, "source": ledger.source, "metric_version": METRIC_VERSION,
                  "config_sha256": fingerprint(config), "thresholds": config["thresholds"],
                  "cases": cases, "feasibility_gate": gate}
    references["reference_bundle_id"] = fingerprint(references)
    ledger.write("reference.json", references)
    report = {"schema_version": 1, "run_id": ledger.run_id, "source": ledger.source,
              "feasibility_gate": gate, "core_reference_policy_satisfied": core_pass,
              "real_qloo_requests": ledger.live_requests, "transport_attempts": client.requests,
              "config_sha256": fingerprint(config), "reference_bundle_id": references["reference_bundle_id"],
              "error": error, "cases": [{key: case[key] for key in ("case_id", "reference_verdict", "reference_delta",
                        "reference_jitter", "reference_top_k_overlap", "required")} for case in cases],
              "not_run": [s["id"] for s in config["scenarios"] if s["id"] not in {c["case_id"] for c in cases}],
              "metric_status": "PROVISIONAL — calibrate with live Qloo data before freezing formulas or thresholds",
              "notice": "Synthetic engineering controls cannot prove Qloo feasibility. Oracle-copy is a positive control, not automatic repair."}
    if cases:
        positive = replay_template(references, insensitive=False)
        negative = replay_template(references, insensitive=True)
        ledger.write("agent-positive-control.json", positive)
        ledger.write("agent-insensitive-control.json", negative)
        positive_eval = evaluate_replay(references, positive, config["thresholds"])
        negative_eval = evaluate_replay(references, negative, config["thresholds"])
        ledger.write("evaluation-positive-control.json", positive_eval)
        ledger.write("evaluation-insensitive-control.json", negative_eval)
        regression = compare_evaluations(positive_eval, negative_eval, config["thresholds"]["max_fidelity_drop"])
        ledger.write("regression-control.json", regression)
        report["controls"] = {"positive": {case["case_id"]: case["diagnosis"] for case in positive_eval["cases"]},
                              "negative": {case["case_id"]: case["diagnosis"] for case in negative_eval["cases"]},
                              "synthetic_regression_detected": regression["cultural_regression_detected"],
                              "ci_gate": "NOT_VALIDATED"}
    ledger.record("feasibility_gate", {"status": gate, "source": ledger.source, "real_qloo_requests": ledger.live_requests})
    ledger.write("report.json", report)
    return report

