from __future__ import annotations

import math
from typing import Any

from .errors import SchemaError
from .evidence import fingerprint
from .metrics import directional_alignment, ndcg_at_k, rank_distance, top_k_overlap, validate_ranking
from .models import canonical_id

METRIC_VERSION = "ordinal-ndcg-linear-v0.1-provisional"


def validate_frozen_reference(references: dict[str, Any]) -> None:
    if references.get("source") not in ("synthetic", "qloo-live") or references.get("metric_version") != METRIC_VERSION:
        raise SchemaError("Unknown reference provenance or metric version.")
    expected_bundle = fingerprint({key: value for key, value in references.items() if key != "reference_bundle_id"})
    if references.get("reference_bundle_id") != expected_bundle:
        raise SchemaError("Frozen reference content hash does not match. The oracle changed or the artifact is damaged.")
    seen = set()
    for case in references.get("cases", []):
        if case.get("case_id") in seen:
            raise SchemaError("Duplicate cases in the frozen reference.")
        seen.add(case["case_id"])
        expected_case = fingerprint({key: value for key, value in case.items() if key != "reference_id"})
        if case.get("reference_id") != expected_case or case.get("source") != references["source"]:
            raise SchemaError("Per-case reference hash or provenance does not match.")
        if case.get("catalog_resolved_through_entities") is not True or case.get("context_compliance") != 1.0:
            raise SchemaError("The reference catalog is not grounded and context-verified.")
        validate_ranking(case["candidate_ids"], minimum=case["top_k"])
        for entity_id in case["candidate_ids"]:
            canonical_id(entity_id, synthetic=references["source"] == "synthetic")
        for persona in ("A", "B"):
            if len(case["rankings"][persona]) < 2:
                raise SchemaError("The reference has no uncached repeat evidence.")
            for ranking in case["rankings"][persona]:
                validate_ranking(ranking, minimum=case["top_k"])
                if set(ranking) != set(case["candidate_ids"]):
                    raise SchemaError("Frozen reference rankings use different candidate universes.")


def evaluate_case(reference: dict[str, Any], agent_a: list[str], agent_b: list[str],
                  thresholds: dict[str, float]) -> dict[str, Any]:
    k = reference["top_k"]
    catalog = set(reference["candidate_ids"])
    for ranking in (agent_a, agent_b):
        validate_ranking(ranking, minimum=k)
        if set(ranking) - catalog:
            raise SchemaError("Agent outputs leave the fixed catalog. Resolve and extend the reference before evaluating them; unknown does not mean hallucinated.")
    ref_a, ref_b = reference["rankings"]["A"][0], reference["rankings"]["B"][0]
    fidelity_a, fidelity_b = ndcg_at_k(agent_a, ref_a, k), ndcg_at_k(agent_b, ref_b, k)
    alignment = directional_alignment(agent_a, agent_b, ref_a, ref_b, k)
    change = rank_distance(agent_a, agent_b, k) if set(agent_a) == set(agent_b) and len(agent_a) == len(agent_b) else None
    unchanged = agent_a[:k] == agent_b[:k]
    if reference["reference_verdict"] != "MEASURABLE_MUTATION":
        diagnosis = "REFERENCE_INCONCLUSIVE"
    elif unchanged and alignment <= thresholds["insensitivity_ceiling"]:
        diagnosis = "TASTE_INSENSITIVE"
    elif alignment <= thresholds["insensitivity_ceiling"]:
        diagnosis = "MISALIGNED_MUTATION"
    else:
        diagnosis = "DIRECTIONALLY_ALIGNED"
    return {"case_id": reference["case_id"], "reference_id": reference["reference_id"],
            "task_fingerprint": reference["task_fingerprint"], "metric_version": METRIC_VERSION,
            "taste_fidelity_a": fidelity_a, "taste_fidelity_b": fidelity_b,
            "taste_fidelity_worst_persona": min(fidelity_a, fidelity_b),
            "taste_sensitivity_directional": alignment,
            "agent_rank_distance": change, "agent_top_k_overlap": top_k_overlap(agent_a, agent_b, k),
            "reference_delta": reference["reference_delta"], "reference_jitter": reference["reference_jitter"],
            "verified_catalog_coverage": 1.0, "context_compliance": 1.0,
            "diagnosis": diagnosis, "required": reference["required"]}


def evaluate_replay(references: dict[str, Any], agent: dict[str, Any], thresholds: dict[str, float]) -> dict[str, Any]:
    if references.get("schema_version") != 1 or agent.get("schema_version") != 1:
        raise SchemaError("Expected reference and agent schema_version=1.")
    validate_frozen_reference(references)
    if references.get("thresholds") != thresholds:
        raise SchemaError("Evaluation thresholds changed after the oracle was frozen. Capture a reviewed reference/config bundle.")
    if agent.get("reference_bundle_id") != references.get("reference_bundle_id"):
        raise SchemaError("Replay reference fingerprint does not match. Use the template from this reference run.")
    if agent.get("source") not in ("synthetic-control", "user-replay"):
        raise SchemaError("Agent source must explicitly identify synthetic-control or user-replay.")
    for key in ("agent_name", "agent_version"):
        if not isinstance(agent.get(key), str) or not agent[key]:
            raise SchemaError(f"Agent {key} is missing.")
    if not references.get("cases"):
        raise SchemaError("No usable frozen reference cases are available.")
    expected = {case["case_id"] for case in references["cases"]}
    if not isinstance(agent.get("cases"), dict) or set(agent["cases"]) != expected:
        raise SchemaError("Replay must include every case in the frozen reference exactly once.")
    cases = []
    for reference in references["cases"]:
        value = agent["cases"][reference["case_id"]]
        if not isinstance(value, dict) or set(value) != {"A", "B"}:
            raise SchemaError("Replay cases must contain only observable rankings for A and B.")
        if not isinstance(value["A"], list) or not isinstance(value["B"], list):
            raise SchemaError("Observable replay rankings must be arrays.")
        cases.append(evaluate_case(reference, value["A"], value["B"], thresholds))
    live = references.get("source") == "qloo-live" and agent["source"] == "user-replay"
    required = [case for case in cases if case["required"]]
    if not live:
        gate = "NOT_VALIDATED"
    elif references.get("feasibility_gate") != "PASS" or any(c["diagnosis"] == "REFERENCE_INCONCLUSIVE" for c in required):
        gate = "INCONCLUSIVE"
    elif any(c["diagnosis"] != "DIRECTIONALLY_ALIGNED" for c in required):
        gate = "FAIL"
    else:
        # Alignment is the pilot gate only. Fidelity thresholds await real-data calibration.
        gate = "PASS"
    report = {"schema_version": 1, "source": references["source"], "agent_source": agent["source"],
              "agent_name": agent["agent_name"], "agent_version": agent["agent_version"],
              "reference_bundle_id": references["reference_bundle_id"], "metric_version": METRIC_VERSION,
              "thresholds": thresholds, "cases": cases, "ci_gate": gate,
              "notice": "Pilot thresholds, not a validated quality standard. Replay evaluates supplied decisions; it does not execute an LLM."}
    report["evaluation_id"] = fingerprint(report)
    return report


def compare_evaluations(baseline: dict[str, Any], candidate: dict[str, Any], max_drop: float) -> dict[str, Any]:
    if isinstance(max_drop, bool) or not isinstance(max_drop, (float, int)) or not math.isfinite(max_drop) or not 0 <= max_drop < 1:
        raise SchemaError("The regression threshold must be finite and in [0,1).")
    for report in (baseline, candidate):
        expected = fingerprint({key: value for key, value in report.items() if key != "evaluation_id"})
        if report.get("evaluation_id") != expected:
            raise SchemaError("Evaluation content hash does not match. Do not compare modified evidence.")
    for key in ("reference_bundle_id", "metric_version", "thresholds", "agent_name"):
        if baseline.get(key) != candidate.get(key) or baseline.get(key) is None:
            raise SchemaError(f"Regression comparison requires matching {key}; oracle/config drift is not an agent regression.")
    if baseline.get("agent_version") == candidate.get("agent_version"):
        raise SchemaError("Regression comparison needs two distinct agent versions.")
    before = {case["case_id"]: case for case in baseline["cases"]}
    after = {case["case_id"]: case for case in candidate["cases"]}
    if set(before) != set(after) or not before:
        raise SchemaError("Baseline and candidate must cover the same nonempty case set.")
    changes = []
    for key, old in before.items():
        new = after[key]
        if old["reference_id"] != new["reference_id"] or old["task_fingerprint"] != new["task_fingerprint"]:
            raise SchemaError("Per-case reference or task changed. Freeze the oracle before comparing agent versions.")
        drops = {persona: old[f"taste_fidelity_{persona}"] - new[f"taste_fidelity_{persona}"] for persona in ("a", "b")}
        worst = max(drops.values())
        changes.append({"case_id": key, "fidelity_before": old["taste_fidelity_worst_persona"],
                        "fidelity_after": new["taste_fidelity_worst_persona"], "drops_by_persona": drops,
                        "worst_persona_drop": worst, "regression": worst > max_drop, "required": old["required"]})
    regression = any(case["regression"] and case["required"] for case in changes)
    live = all(report.get("source") == "qloo-live" and report.get("agent_source") == "user-replay" for report in (baseline, candidate))
    if not live:
        gate = "NOT_VALIDATED"
    elif baseline.get("ci_gate") != "PASS" or candidate.get("ci_gate") == "INCONCLUSIVE":
        gate = "INCONCLUSIVE"
    elif regression or candidate.get("ci_gate") != "PASS":
        gate = "FAIL"
    else:
        gate = "PASS"
    return {"schema_version": 1, "source": baseline["source"], "reference_bundle_id": baseline["reference_bundle_id"],
            "baseline_version": baseline["agent_version"], "candidate_version": candidate["agent_version"],
            "metric_version": baseline["metric_version"], "max_fidelity_drop": max_drop, "cases": changes,
            "cultural_regression_detected": regression, "ci_gate": gate}

