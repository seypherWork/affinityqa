"""Calibrate on development inputs, freeze a policy, then execute held-out inputs.

Only catalog metadata is reused from Qloo. Missing per-pair references cannot be
replaced with invented ranks, and the cultural release gate remains unvalidated.
"""
from __future__ import annotations

import copy
from itertools import combinations, product
import json
import unicodedata

from .agents import AgentError, validate_response
from .errors import AffinityQAError, SchemaError
from .evidence import fingerprint, utc_now
from .metrics import rank_distance
from .movie_incident import CachedMovieAgent, movie_requests

CONTRACT_VERSION = "movie-suite-v2-normalized-input"
CONTROL_NAMES = ("signal-order", "json-key-order", "equivalent-whitespace", "request-id-change", "irrelevant-comment", "fresh-session")


def normalize_request(request):
    """Canonical declared interests; comments/IDs are not personalization signals."""
    value = {key: copy.deepcopy(request[key]) for key in ("schema_version", "task", "top_k", "catalog")}
    profile = request.get("profile")
    if not isinstance(profile, list) or not profile:
        raise SchemaError("A model request needs explicit interests.")
    normalized = []
    for signal in profile:
        if not isinstance(signal, dict) or set(signal) != {"name", "type"} or signal["type"] != "urn:entity:artist":
            raise SchemaError("Unsupported declared interest.")
        if not isinstance(signal["name"], str):
            raise SchemaError("An interest must have a name.")
        name = " ".join(unicodedata.normalize("NFKC", signal["name"]).split())
        if not name or len(name) > 200:
            raise SchemaError("Invalid declared interest name.")
        normalized.append({"name": name, "type": signal["type"]})
    normalized.sort(key=lambda row: (row["type"], row["name"].casefold()))
    if len({(row["name"].casefold(), row["type"]) for row in normalized}) != len(normalized):
        raise SchemaError("Duplicate declared interests are not a separate signal.")
    value["profile"] = normalized
    value["request_id"] = fingerprint(value)
    return value


def requests_for_pair(template, pair):
    result = {}
    for label in ("A", "B"):
        value = copy.deepcopy(template)
        value["profile"] = [{"name": seed["name"], "type": seed["search_type"]} for seed in pair[label]]
        result[label] = normalize_request(value)
    return result


def noise_and_effect(rankings, k):
    within = [rank_distance(a, b, k) for rows in rankings.values() for a, b in combinations(rows, 2)]
    cross = [rank_distance(a, b, k) for a, b in product(rankings["A"], rankings["B"])]
    return {"noise_max": max(within), "cross_distance_min": min(cross), "cross_distance_max": max(cross)}


def validate_policy(policy, *, suite, manifest, catalog):
    if (not isinstance(policy, dict) or policy.get("policy_sha256") != fingerprint({k: v for k, v in policy.items() if k != "policy_sha256"})
            or policy.get("suite_sha256") != fingerprint(suite) or policy.get("model_manifest_sha256") != fingerprint(manifest)
            or policy.get("catalog_sha256") != fingerprint(catalog) or policy.get("contract_version") != CONTRACT_VERSION):
        raise SchemaError("Frozen development policy, model, catalog or suite changed.")
    expected = [p["id"] for p in suite["pairs"] if p["split"] == "development"]
    if policy.get("development_pair_ids") != expected or policy.get("reserved_cases_seen") != 0:
        raise SchemaError("Development policy used the wrong split.")
    threshold = policy.get("observed_noise_barrier")
    if type(threshold) not in (int, float) or not 0 <= threshold < 2:
        raise SchemaError("Invalid frozen observed-noise barrier.")


def _rank(engine, ledger, request, *, phase, pair_id, label, repeat, progress):
    if progress:
        progress(phase, pair_id, engine.calls + 1)
    response = engine.rank(request)
    ranking = validate_response(request, response)
    if len(ranking) != len(request["catalog"]):
        raise AgentError("Suite decisions must rank the complete catalog.")
    ledger.record("model_decision", {"phase": phase, "pair_id": pair_id, "profile": label, "repeat": repeat,
        "request_sha256": fingerprint(request), "ranked_entity_ids": ranking, "inference_call": engine.calls})
    return ranking


def run_local_suite(engine, ledger, reference, suite, *, progress=None):
    pilot_inputs = movie_requests(reference, suite)
    if reference.get("source") != "qloo-live" or ledger.source != "qloo-catalog+local-llm":
        raise SchemaError("The suite requires a verified real catalog and declared local-model provenance.")
    template = normalize_request(pilot_inputs["A"])
    development = [p for p in suite["pairs"] if p["split"] == "development"]
    reserved = [p for p in suite["pairs"] if p["split"] == "reserved"]
    if len(development) != 6 or len(reserved) != 6 or suite.get("invariance_controls") != list(CONTROL_NAMES):
        raise SchemaError("This bounded suite expects six development, six reserved pairs and six declared controls.")
    # 36 calibration + 8 controls + 54 held-out calls. No new Qloo request.
    if engine.max_calls - engine.calls < 98:
        raise SchemaError("The complete local suite requires a predeclared budget of 98 inference attempts.")
    report = {"schema_version": 2, "run_id": ledger.run_id, "source": ledger.source,
        "contract_version": CONTRACT_VERSION, "suite_sha256": fingerprint(suite),
        "catalog_reference_sha256": reference["reference_sha256"], "model_manifest_sha256": fingerprint(engine.manifest),
        "development": [], "invariance": [], "reserved": [], "status": "INCOMPLETE", "error": None,
        "ci_gate": "NOT_VALIDATED", "new_qloo_requests": 0,
        "notice": "Structural cache generalization and model stability only. Reserved Qloo rankings are not available; no cultural release gate is certified."}
    ledger.write("suite.json", suite)
    ledger.write("agent-manifest.json", engine.manifest)
    ledger.write("catalog.json", template["catalog"])
    try:
        for pair in development:
            inputs = requests_for_pair(template, pair)
            rankings = {"A": [], "B": []}
            for repeat in range(3):
                for label in (("A", "B") if repeat % 2 == 0 else ("B", "A")):
                    rankings[label].append(_rank(engine, ledger, inputs[label], phase="development", pair_id=pair["id"],
                        label=label, repeat=repeat + 1, progress=progress))
            row = {"pair_id": pair["id"], "split": "development", "rankings": rankings,
                   **noise_and_effect(rankings, suite["top_k"])}
            ledger.write("development-" + pair["id"] + ".json", row)
            report["development"].append(row)
        base = requests_for_pair(template, development[0])["A"]
        base_rank = report["development"][0]["rankings"]["A"][0]
        # Each control produces a model decision. The two-interest order control
        # gets its own baseline instead of pretending a one-item reorder is useful.
        for control in CONTROL_NAMES:
            modified = copy.deepcopy(base)
            expected = base_rank
            if control == "signal-order":
                modified["profile"].append({"name": development[0]["B"][0]["name"], "type": "urn:entity:artist"})
                canonical = normalize_request(modified)
                expected = _rank(engine, ledger, canonical, phase="invariance", pair_id=control,
                                 label="baseline", repeat=1, progress=progress)
                modified["profile"].reverse()
            elif control == "json-key-order":
                modified = dict(reversed(list(modified.items())))
                modified["profile"] = [dict(reversed(list(row.items()))) for row in modified["profile"]]
            elif control == "equivalent-whitespace":
                modified["profile"][0]["name"] = "  " + modified["profile"][0]["name"].replace(" ", "   ") + "  "
            elif control == "request-id-change":
                modified["request_id"] = "irrelevant-new-request-id"
            elif control == "irrelevant-comment":
                modified["comment"] = "A release reviewer opened this example."
            elif control == "fresh-session":
                # Engine requests are stateless; a new application cache must recompute.
                modified = json.loads(json.dumps(modified))
            normalized = normalize_request(modified)
            ranking = _rank(engine, ledger, normalized, phase="invariance", pair_id=control,
                            label="variant", repeat=1, progress=progress)
            distance = rank_distance(expected, ranking, suite["top_k"])
            report["invariance"].append({"control": control, "distance": distance,
                "normalized_input_sha256": fingerprint(normalized), "ranked_entity_ids": ranking})
        # A repeat after all controls checks drift before freezing anything.
        drift = _rank(engine, ledger, base, phase="invariance", pair_id="calibration-end-repeat", label="A", repeat=1, progress=progress)
        drift_distance = rank_distance(base_rank, drift, suite["top_k"])
        observed_noise = max([row["noise_max"] for row in report["development"]] +
                             [row["distance"] for row in report["invariance"]] + [drift_distance])
        policy = {"schema_version": 1, "created_utc": utc_now(), "contract_version": CONTRACT_VERSION,
            "suite_sha256": fingerprint(suite), "catalog_sha256": fingerprint(template["catalog"]),
            "model_manifest_sha256": fingerprint(engine.manifest), "development_pair_ids": [p["id"] for p in development],
            "development_evidence_sha256": fingerprint(report["development"]), "invariance_evidence_sha256": fingerprint(report["invariance"]),
            "observed_noise_max": observed_noise, "practical_tolerance": suite["practical_tolerance"],
            "observed_noise_barrier": observed_noise + suite["practical_tolerance"], "end_repeat_distance": drift_distance,
            "reserved_cases_seen": 0, "repeat_count": 3, "patch": {"operation": "set-cache-scope", "before": "task", "after": "profile", "clear_old_cache": True},
            "statistical_status": "OBSERVED_DEVELOPMENT_NOISE_ONLY_NO_POPULATION_CERTIFICATION"}
        policy["policy_sha256"] = fingerprint(policy)
        policy_path = ledger.write("frozen-policy.json", policy)
        frozen_bytes = policy_path.read_bytes()
        ledger.record("policy_frozen_before_reserved", {"policy_sha256": policy["policy_sha256"], "reserved_cases_seen": 0})
        report["frozen_policy_sha256"] = policy["policy_sha256"]
        for pair in reserved:
            if policy_path.read_bytes() != frozen_bytes:
                raise SchemaError("Policy file changed after freeze; reserved execution stopped.")
            validate_policy(policy, suite=suite, manifest=engine.manifest, catalog=template["catalog"])
            inputs = requests_for_pair(template, pair)
            faulty, repaired = {"A": [], "B": []}, {"A": [], "B": []}
            collisions = []
            structural_checks = []
            for repeat in range(3):
                order = ("A", "B") if repeat % 2 == 0 else ("B", "A")
                bad = CachedMovieAgent(engine, "task", ledger, "v1-injected-profile-cache-defect")
                fixed = CachedMovieAgent(engine, "profile", ledger, "v2-frozen-profile-cache-policy")
                for label in order:
                    if progress:
                        progress("reserved-candidate", pair["id"], engine.calls + 1)
                    faulty[label].append(bad.rank(inputs[label]))
                for label in order:
                    if progress:
                        progress("reserved-repaired", pair["id"], engine.calls + 1)
                    repaired[label].append(fixed.rank(inputs[label]))
                collisions.append(bad.trace[1]["cache_hit"] and bad.trace[1]["cached_profile_sha256"] != bad.trace[1]["input_profile_sha256"])
                structural_checks.append(all(not event["cache_hit"] and event["input_profile_sha256"] == event["cached_profile_sha256"] for event in fixed.trace))
                # Same profile under a new request ID must hit the repaired cache.
                equivalent = copy.deepcopy(inputs[order[0]])
                equivalent["request_id"] = "same-profile-new-request"
                fixed.rank(equivalent)
                structural_checks.append(fixed.trace[-1]["cache_hit"])
            measured = noise_and_effect(repaired, suite["top_k"])
            barrier = policy["observed_noise_barrier"]
            stable = measured["noise_max"] <= barrier
            sensitive = measured["cross_distance_min"] > barrier
            row = {"pair_id": pair["id"], "split": "reserved", "policy_sha256": policy["policy_sha256"],
                "structural_gate": "PASS" if all(collisions) and all(structural_checks) else "FAIL",
                "behavior_gate": "OBSERVED_SENSITIVITY_RECOVERY" if stable and sensitive else "INCONCLUSIVE",
                "qloo_reference_gate": "NOT_CAPTURED", "ci_gate": "NOT_VALIDATED", "order": ["AB", "BA", "AB"],
                "cache_collisions": sum(collisions), "candidate": faulty, "repaired": repaired,
                "frozen_noise_barrier": barrier, **measured}
            ledger.write("reserved-" + pair["id"] + ".json", row)
            report["reserved"].append(row)
        report["status"] = "COMPLETE_LOCAL_SUITE"
        report["structural_passes"] = sum(r["structural_gate"] == "PASS" for r in report["reserved"])
        report["sensitivity_recoveries"] = sum(r["behavior_gate"] == "OBSERVED_SENSITIVITY_RECOVERY" for r in report["reserved"])
        report["denominator"] = len(reserved)
    except AffinityQAError as exc:
        report["error"] = str(exc)
        ledger.record("stopped", {"reason": str(exc)})
    report["local_inference_attempts"] = engine.calls
    report["model_decisions_recorded"] = len(engine.observations)
    ledger.write("local-inference-observations.json", engine.observations)
    ledger.write("suite-report.json", report)
    return report
