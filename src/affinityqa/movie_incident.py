"""A declared cache defect, diagnosis and a single declarative policy repair.

Only the development pilot is consumed. This is not a reserved-suite CI gate.
"""
from __future__ import annotations

import copy
from itertools import combinations, product
from statistics import median

from .agents import AgentError, validate_response
from .errors import AffinityQAError, SchemaError
from .evidence import fingerprint
from .film_protocol import calibrate_reference, reference_agreement, validate_suite
from .metrics import rank_distance


def movie_requests(reference, suite):
    validate_suite(suite)
    if (reference.get("schema_version") != 2 or reference.get("suite_sha256") != fingerprint(suite)
            or reference.get("reference_sha256") != fingerprint({k: v for k, v in reference.items() if k != "reference_sha256"})):
        raise SchemaError("Movie reference integrity or suite binding failed.")
    pair = next((p for p in suite["pairs"] if p["id"] == reference.get("pair_id")), None)
    if not pair or pair["split"] != "development":
        raise SchemaError("The incident/repair runner cannot consume reserved reference answers.")
    policy = calibrate_reference(reference["rankings"], reference["catalog_ids"], reference["top_k"], suite["practical_tolerance"])
    if reference.get("calibration_policy") != policy or not policy["informative"]:
        raise SchemaError("Reference is uninformative or its frozen policy changed.")
    catalog = [{"entity_id": e["entity_id"], "name": e["name"], "types": e["types"],
                "release_year": e.get("metadata", {}).get("release_year")}
               for e in sorted(reference["entities"], key=lambda row: row["entity_id"])]
    if len(catalog) != len(reference["catalog_ids"]) or {e["entity_id"] for e in catalog} != set(reference["catalog_ids"]):
        raise SchemaError("Agent input catalog does not match the reference universe.")
    requests = {}
    for label in ("A", "B"):
        value = {"schema_version": 1, "task": suite["task"], "top_k": suite["top_k"], "catalog": catalog,
                 "profile": [{"name": seed["name"], "type": seed["search_type"]} for seed in pair[label]]}
        value["request_id"] = fingerprint(value)
        requests[label] = value
    return requests


class CachedMovieAgent:
    def __init__(self, engine, scope, ledger, version):
        if scope not in ("task", "profile"):
            raise AgentError("Cache scope must be task or profile.")
        self.engine, self.scope, self.ledger, self.version = engine, scope, ledger, version
        self.cache = {}
        self.trace = []

    def rank(self, request):
        key_input = {"task": request["task"], "top_k": request["top_k"], "catalog": request["catalog"],
                     "model_manifest": self.engine.manifest}
        if self.scope == "profile":
            key_input["profile"] = request["profile"]
        key = fingerprint(key_input)
        profile = fingerprint(request["profile"])
        hit = key in self.cache
        if hit:
            ranking, original_profile = self.cache[key]
        else:
            response = self.engine.rank(request)
            ranking = validate_response(request, response)
            if len(ranking) != len(request["catalog"]):
                raise AgentError("Movie output must rank the complete catalog.")
            original_profile = profile
            self.cache[key] = (ranking, original_profile)
        event = {"agent_version": self.version, "cache_scope": self.scope, "cache_key_sha256": key,
                 "input_profile_sha256": profile, "cached_profile_sha256": original_profile,
                 "cache_hit": hit, "output_sha256": fingerprint(ranking)}
        self.trace.append(event)
        self.ledger.record("agent_cache_decision", event)
        return list(ranking)


def run_movie_incident(engine, ledger, reference, suite, *, progress=None):
    requests = movie_requests(reference, suite)
    if ledger.source != "qloo-live+local-llm" or reference.get("source") != "qloo-live":
        raise SchemaError("The incident runner requires a real Qloo reference and declared local LLM execution.")
    report = {"schema_version": 2, "run_id": ledger.run_id, "source": ledger.source,
              "reference_sha256": reference["reference_sha256"], "suite_sha256": fingerprint(suite),
              "pair_id": reference["pair_id"], "split": "development", "ci_gate": "NOT_VALIDATED",
              "incident_gate": "INCONCLUSIVE", "repair_gate": "INCONCLUSIVE", "error": None,
              "fault_injection": "Declared cache defect: candidate v1 omits profile from its cache key.",
              "notice": "Development pilot only. No reserved retest, absolute quality threshold or full cultural CI certification."}
    ledger.write("agent-manifest.json", engine.manifest)
    ledger.write("agent-inputs.json", requests)
    ledger.write("reference-binding.json", {"reference_sha256": reference["reference_sha256"],
                "policy_sha256": reference["calibration_policy"]["policy_sha256"], "pair_id": reference["pair_id"]})
    try:
        baseline = {"A": [], "B": []}
        for repeat in range(3):
            for label in (("A", "B") if repeat % 2 == 0 else ("B", "A")):
                if progress:
                    progress("baseline", engine.calls + 1)
                response = engine.rank(requests[label])
                ranking = validate_response(requests[label], response)
                if len(ranking) != len(reference["catalog_ids"]):
                    raise AgentError("Movie baseline must return the complete catalog.")
                baseline[label].append(ranking)
        noise = max(rank_distance(a, b, suite["top_k"]) for rows in baseline.values() for a, b in combinations(rows, 2))
        cross = min(rank_distance(a, b, suite["top_k"]) for a, b in product(baseline["A"], baseline["B"]))
        healthy_sensitive = cross > noise + suite["practical_tolerance"]
        frozen = {"agent_noise_max": noise, "healthy_cross_distance_min": cross,
                  "healthy_sensitive": healthy_sensitive, "reference_policy_sha256": reference["calibration_policy"]["policy_sha256"],
                  "method": "observed-noise-development-pilot", "reserved_cases_seen": 0}
        frozen["policy_sha256"] = fingerprint(frozen)
        ledger.write("agent-calibration.json", frozen)
        if progress:
            progress("candidate-with-declared-cache-defect", engine.calls + 1)
        candidate = CachedMovieAgent(engine, "task", ledger, "v1-injected-profile-cache-defect")
        before = {label: candidate.rank(requests[label]) for label in ("A", "B")}
        collision = (candidate.trace[1]["cache_hit"] is True
                     and candidate.trace[0]["input_profile_sha256"] != candidate.trace[1]["input_profile_sha256"]
                     and candidate.trace[1]["cached_profile_sha256"] != candidate.trace[1]["input_profile_sha256"])
        detected = healthy_sensitive and collision and before["A"] == before["B"]
        report.update({"incident_gate": "FAIL" if detected else "INCONCLUSIVE", "cache_profile_collision": collision,
                       "diagnosis": "CACHE_OMITS_PROFILE" if detected else "INSUFFICIENT_BASELINE_OR_CACHE_EVIDENCE"})
        # The repair is determined by observable cache arguments, not oracle rankings.
        patch = {"schema_version": 1, "operation": "set-cache-scope", "before": "task", "after": "profile",
                 "clear_old_cache": True, "attempt": 1, "max_attempts": 2,
                 "cause_evidence_sha256": fingerprint(candidate.trace), "reserved_answers_used": False}
        ledger.write("proposed-patch.json", patch)
        repaired = CachedMovieAgent(engine, "profile", ledger, "v2-profile-cache-repair")
        after = {}
        for label in ("A", "B"):
            if progress:
                progress("repair-retest", engine.calls + 1)
            after[label] = repaired.rank(requests[label])
        after_distance = rank_distance(after["A"], after["B"], suite["top_k"])
        repair_observed = detected and after_distance > noise + suite["practical_tolerance"] and all(not e["cache_hit"] for e in repaired.trace)
        def score(outputs):
            own = {label: reference_agreement(outputs[label], reference["rankings"][label], reference["catalog_ids"], suite["top_k"])
                   for label in ("A", "B")}
            opposite = {label: reference_agreement(outputs[label], reference["rankings"]["B" if label == "A" else "A"], reference["catalog_ids"], suite["top_k"])
                        for label in ("A", "B")}
            return {"own_reference": own, "own_profile_advantage": median(own[label]["median"] - opposite[label]["median"] for label in ("A", "B"))}
        report.update({"repair_gate": "OBSERVED_DEVELOPMENT_REPAIR" if repair_observed else "INCONCLUSIVE",
                       "agent_calibration": frozen, "before": score(before), "after": score(after),
                       "repaired_profile_distance": after_distance, "reserved_cases_evaluated": 0})
        ledger.write("decisions.json", {"baseline": baseline, "candidate": before, "repaired": after})
        ledger.write("applied-patch.json", patch)
    except AffinityQAError as exc:
        report["error"] = str(exc)
        ledger.record("stopped", {"reason": str(exc)})
    report.update({"local_inference_calls": engine.calls, "new_qloo_requests": 0,
                   "heldout_validation": "NOT_RUN", "live_ci_workflow": "NOT_RUN"})
    ledger.write("local-inference-observations.json", engine.observations)
    ledger.write("incident-report.json", report)
    return report
