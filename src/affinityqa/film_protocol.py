"""A bounded movie pilot, separate from the legacy provisional spike.

Qloo is a relative ranking reference, not human preference ground truth.
All ranking and calibration inputs are frozen before agent evaluation.
"""
from __future__ import annotations

from itertools import combinations, product
import json
import math
from pathlib import Path
from statistics import median
from typing import Any

from .errors import AffinityQAError, SchemaError
from .evidence import fingerprint, utc_now
from .metrics import ndcg_at_k, rank_distance
from .models import context_issues, parse_entities, resolve_seed
from .qloo import BASE_URL, QlooClient, validate_params

METRIC_VERSION = "qloo-reference-agreement-v2-pilot"


def import_lookup_samples(client: QlooClient, directory: Path) -> int:
    """Reuse verified entity lookups only; reference repeats always stay uncached."""
    if directory.is_symlink() or directory.resolve().parent != client.ledger.directory.parent.resolve():
        raise SchemaError("Lookup reuse is restricted to another local run in this evidence store.")
    try:
        for name, limit in (("report.json", 20_000), ("ledger.jsonl", 1_000_000)):
            path = directory / name
            if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
                raise SchemaError("Unsafe lookup provenance file.")
        report = json.loads((directory / "report.json").read_text(encoding="utf-8"))
        if report.get("source") != "qloo-live" or report.get("run_id") != directory.name:
            raise SchemaError("Lookup provenance does not identify a live Qloo run.")
        records = [json.loads(line) for line in (directory / "ledger.jsonl").read_text(encoding="utf-8").splitlines()]
        recorded = {e["data"]["sample"]: e["data"] for e in records if e.get("kind") == "tool_call" and e.get("source") == "qloo-live"}
        imported = 0
        for path in sorted(directory.glob("http-*.json")):
            if path.is_symlink() or path.stat().st_size > 5_100_000:
                raise SchemaError("Unsafe lookup sample.")
            sample = json.loads(path.read_text(encoding="utf-8"))
            request = sample.get("request", {})
            if request.get("path") not in ("/search", "/entities"):
                continue
            if (sample.get("source") != "qloo-live" or sample.get("status") != 200
                    or sample.get("live_network_request") is not True or request.get("host") != BASE_URL
                    or request.get("method") != "GET" or sample.get("response_sha256") != fingerprint(sample.get("response"))
                    or recorded.get(path.name, {}).get("response_sha256") != sample.get("response_sha256")
                    or recorded.get(path.name, {}).get("request") != request):
                raise SchemaError("Lookup sample integrity/provenance failed.")
            validate_params(request["path"], request["params"], synthetic=False)
            parse_entities(sample["response"], insights=False)
            client.cache[fingerprint(request)] = sample["response"]
            client.ledger.record("imported_lookup", {"source_run": directory.name, "sample": path.name,
                "response_sha256": sample["response_sha256"], "new_network_requests": 0})
            imported += 1
        return imported
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        raise SchemaError("Unreadable lookup reuse evidence; no new requests were sent.") from None


def load_suite(path: Path) -> dict[str, Any]:
    try:
        suite = json.loads(path.read_text(encoding="utf-8-sig"))
        validate_suite(suite)
        return suite
    except (OSError, ValueError, KeyError, TypeError):
        raise SchemaError("Invalid movie suite; no reference or quality gate passed.") from None


def validate_suite(suite: dict[str, Any]) -> None:
    if not isinstance(suite, dict) or suite.get("schema_version") != 2:
        raise SchemaError("Expected movie suite schema_version=2.")
    if not isinstance(suite.get("task"), str) or not suite["task"].strip():
        raise SchemaError("The personalization task must be explicit.")
    for key, low, high in (("top_k", 1, 20), ("repeats", 3, 5)):
        value = suite.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
            raise SchemaError(f"Invalid suite {key}.")
    tolerance = suite.get("practical_tolerance")
    if isinstance(tolerance, bool) or not isinstance(tolerance, (int, float)) or not math.isfinite(tolerance) or not 0 <= tolerance < 1:
        raise SchemaError("Practical tolerance must be predeclared, finite and in [0,1).")
    catalog = suite.get("catalog")
    if not isinstance(catalog, list) or not suite["top_k"] <= len(catalog) <= 20:
        raise SchemaError("The independently selected catalog must contain top_k..20 movies.")
    def validate_seed(seed, entity_type):
        if not isinstance(seed, dict) or seed.get("search_type") != entity_type:
            raise SchemaError("Every seed must have a reviewed entity type.")
        for key in ("name", "query"):
            if not isinstance(seed.get(key), str) or not seed[key].strip():
                raise SchemaError("A seed has no explicit name/query.")
        for key in ("accepted_names", "accepted_types"):
            value = seed.get(key)
            if not isinstance(value, list) or not value or any(not isinstance(x, str) or not x for x in value):
                raise SchemaError("Seed resolution rules must be explicit.")
        if seed["accepted_types"] != [entity_type]:
            raise SchemaError("The pilot does not infer sensitive or alternate entity categories.")
    for seed in catalog:
        validate_seed(seed, "urn:entity:movie")
        if "expected_release_year" in seed and (isinstance(seed["expected_release_year"], bool)
                or not isinstance(seed["expected_release_year"], int) or not 1888 <= seed["expected_release_year"] <= 2100):
            raise SchemaError("Movie disambiguation needs an explicit integer release year.")
    if len({seed["query"].casefold() for seed in catalog}) != len(catalog):
        raise SchemaError("Duplicate movie queries cannot form an independent catalog.")
    pairs = suite.get("pairs")
    if not isinstance(pairs, list) or not pairs:
        raise SchemaError("A suite needs development and reserved mutation pairs.")
    ids, splits = set(), set()
    for pair in pairs:
        if not isinstance(pair, dict) or not isinstance(pair.get("id"), str) or not pair["id"] or pair["id"] in ids:
            raise SchemaError("Mutation IDs must be unique.")
        ids.add(pair["id"])
        if pair.get("split") not in ("development", "reserved"):
            raise SchemaError("Every pair needs a declared development/reserved split.")
        splits.add(pair["split"])
        a, b = pair.get("A"), pair.get("B")
        if not isinstance(a, list) or not isinstance(b, list) or len(a) != len(b) or not a:
            raise SchemaError("Profiles must contain matching nonempty signal slots.")
        for seed in a + b:
            validate_seed(seed, "urn:entity:artist")
        if any(len({x["query"].casefold() for x in profile}) != len(profile) for profile in (a, b)):
            raise SchemaError("A profile cannot contain duplicate signal slots.")
        if sum(left != right for left, right in zip(a, b)) != 1:
            raise SchemaError("Each mutation must replace exactly one signal slot.")
        if {x["query"].casefold() for x in a} == {x["query"].casefold() for x in b}:
            raise SchemaError("Signal reorder is invariance, not a taste mutation.")
    if splits != {"development", "reserved"}:
        raise SchemaError("Freeze reserved pairs before evaluating an agent.")
    if not any(p["id"] == suite.get("pilot_pair_id") and p["split"] == "development" for p in pairs):
        raise SchemaError("The feasibility pilot must use a development pair.")


def calibrate_reference(rankings: dict[str, list[list[str]]], catalog: list[str], k: int,
                        practical_tolerance: float) -> dict[str, Any]:
    """Conservative observed-noise barrier; never an estimated population quantile."""
    if isinstance(k, bool) or not isinstance(k, int) or not 1 <= k <= len(catalog):
        raise SchemaError("Invalid calibration top_k.")
    if len(set(catalog)) != len(catalog) or not catalog:
        raise SchemaError("The calibration catalog must contain unique IDs.")
    if isinstance(practical_tolerance, bool) or not isinstance(practical_tolerance, (int, float)) or not math.isfinite(practical_tolerance) or not 0 <= practical_tolerance < 1:
        raise SchemaError("Calibration tolerance is invalid.")
    if set(rankings) != {"A", "B"}:
        raise SchemaError("Calibration needs both profiles.")
    for rows in rankings.values():
        if not isinstance(rows, list) or len(rows) < 3:
            raise SchemaError("At least three uncached repeats are required for this pilot.")
        for row in rows:
            if len(row) != len(catalog) or set(row) != set(catalog):
                raise SchemaError("Missing or duplicate candidates make the reference inconclusive.")
    within = [rank_distance(a, b, k) for rows in rankings.values() for a, b in combinations(rows, 2)]
    cross = [rank_distance(a, b, k) for a, b in product(rankings["A"], rankings["B"])]
    noise = max(within)
    barrier = noise + practical_tolerance
    policy = {"metric_version": METRIC_VERSION, "catalog_sha256": fingerprint(catalog), "top_k": k,
              "calibration_rankings_sha256": fingerprint(rankings), "method": "maximum-observed-null-distance",
              "reference_noise_max": noise, "practical_tolerance": practical_tolerance,
              "informative_barrier": barrier, "cross_distance_min": min(cross),
              "cross_distance_median": median(cross), "within_comparisons": len(within),
              "cross_comparisons": len(cross), "informative": min(cross) > barrier,
              "statistical_status": "PILOT_ONLY_NO_POPULATION_CERTIFICATION"}
    policy["policy_sha256"] = fingerprint(policy)
    return policy


def reference_agreement(actual: list[str], references: list[list[str]], catalog: list[str], k: int) -> dict[str, Any]:
    if len(actual) != len(catalog) or set(actual) != set(catalog):
        raise SchemaError("Agent output must be a complete catalog permutation; do not fabricate its tail.")
    if len(references) < 3 or any(len(r) != len(catalog) or set(r) != set(catalog) for r in references):
        raise SchemaError("Agreement requires complete repeated references.")
    scores = [ndcg_at_k(actual, reference, k) for reference in references]
    return {"name": "agreement-with-qloo-reference", "median": median(scores),
            "min": min(scores), "max": max(scores), "reference_repeats": len(scores),
            "notice": "Relative ordinal agreement, not human preference fidelity or satisfaction."}


def capture_movie_pilot(client: QlooClient, suite: dict[str, Any]) -> dict[str, Any]:
    validate_suite(suite)
    ledger = client.ledger
    ledger.write("suite.json", suite)
    pair = next(p for p in suite["pairs"] if p["id"] == suite["pilot_pair_id"])
    report = {"schema_version": 2, "run_id": ledger.run_id, "source": ledger.source,
              "suite_sha256": fingerprint(suite), "pair_id": pair["id"], "split": pair["split"],
              "reference_gate": "INCONCLUSIVE", "ci_gate": "NOT_VALIDATED", "error": None,
              "notice": "Feasibility and calibration only; no agent or repair has been validated."}
    reference = None
    try:
        def resolve(seed):
            if seed.get("entity_id"):
                body = client.get("/entities", {"entity_ids": seed["entity_id"]})
            else:
                body = client.get("/search", {"query": seed["query"], "types": seed["search_type"], "take": 5})
            entity = resolve_seed(seed, parse_entities(body, insights=False, synthetic=client.synthetic), synthetic=client.synthetic)
            ledger.record("entity_resolution", {"query": seed["query"], "entity": entity.as_dict()})
            return entity.entity_id
        personas = {label: [resolve(seed) for seed in pair[label]] for label in ("A", "B")}
        if sum(a != b for a, b in zip(personas["A"], personas["B"])) != 1:
            raise SchemaError("Resolved profiles must differ in exactly one signal slot.")
        # Catalog names were chosen in the manifest before any affinity results.
        catalog = [resolve(seed) for seed in suite["catalog"]]
        if len(set(catalog)) != len(catalog):
            raise SchemaError("Two catalog titles resolved to the same entity.")
        entities = parse_entities(client.get("/entities", {"entity_ids": ",".join(catalog)}), insights=False, synthetic=client.synthetic)
        if len(entities) != len(catalog) or {x.entity_id for x in entities} != set(catalog):
            raise SchemaError("Independent catalog metadata is incomplete.")
        scenario = {"filter_type": "urn:entity:movie", "filters": {}}
        excluded = set(personas["A"] + personas["B"])
        if context_issues(entities, scenario, excluded):
            raise SchemaError("Catalog types/exclusions do not satisfy the fixed contract.")
        rankings = {"A": [], "B": []}
        for repeat in range(suite["repeats"]):
            # Alternate order so a persistent first-profile effect is visible.
            for label in (("A", "B") if repeat % 2 == 0 else ("B", "A")):
                params = {"filter.type": "urn:entity:movie", "bias.trends": "off", "take": len(catalog),
                          "filter.results.entities": ",".join(catalog),
                          "signal.interests.entities": ",".join(personas[label])}
                rows = parse_entities(client.get("/v2/insights", params, cache=False), insights=True, synthetic=client.synthetic)
                if len(rows) != len(catalog) or {row.entity_id for row in rows} != set(catalog):
                    raise SchemaError("Ranking coverage is incomplete; stop before more repeats.")
                if context_issues(rows, scenario, excluded):
                    raise SchemaError("Ranking type or exclusions violate the contract.")
                rankings[label].append([row.entity_id for row in rows])
                ledger.record("reference_repeat", {"profile": label, "repeat": repeat + 1})
        policy = calibrate_reference(rankings, catalog, suite["top_k"], suite["practical_tolerance"])
        reference = {"schema_version": 2, "source": ledger.source, "captured_utc": utc_now(),
                     "suite_sha256": fingerprint(suite), "pair_id": pair["id"], "task": suite["task"],
                     "personas": personas, "catalog_ids": catalog, "entities": [e.as_dict() for e in entities],
                     "rankings": rankings, "calibration_policy": policy, "top_k": suite["top_k"]}
        reference["reference_sha256"] = fingerprint(reference)
        ledger.write("movie-reference.json", reference)
        ledger.write("calibration-policy.json", policy)
        report.update({"reference_sha256": reference["reference_sha256"], "policy_sha256": policy["policy_sha256"],
                       "catalog_size": len(catalog), "informative": policy["informative"],
                       "reference_gate": "NOT_VALIDATED" if client.synthetic else ("PASS" if policy["informative"] else "INCONCLUSIVE")})
    except AffinityQAError as exc:
        report["error"] = str(exc)
        ledger.record("stopped", {"reason": str(exc)})
    report.update({"real_qloo_requests": ledger.live_requests, "transport_attempts": client.requests})
    if client.synthetic:
        report["reference_gate"] = "NOT_VALIDATED"
    ledger.write("report.json", report)
    return report
