from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Any
import unicodedata
from uuid import UUID

from .errors import ResolutionError, SchemaError


def canonical_id(value: Any, *, synthetic: bool = False) -> str:
    if not isinstance(value, str) or not value:
        raise SchemaError("Missing or invalid entity_id.")
    if synthetic and value.startswith("fixture:"):
        return value
    try:
        return str(UUID(value))
    except ValueError as exc:
        raise SchemaError("Live Qloo entity IDs must be UUIDs; fixture IDs cannot be sent live.") from exc


def normalized_name(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.casefold())
    value = "".join(char for char in value if not unicodedata.combining(char))
    return " ".join(re.sub(r"[^\w\s]", " ", value).split())


@dataclass(frozen=True)
class Entity:
    entity_id: str
    name: str
    types: tuple[str, ...]
    affinity: float | None
    metadata: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {"entity_id": self.entity_id, "name": self.name, "types": list(self.types),
                "affinity": self.affinity, "metadata": self.metadata}


def validate_response_envelope(body: Any, *, insights: bool) -> None:
    if not isinstance(body, dict) or "error" in body or "errors" in body:
        raise SchemaError("Qloo returned an invalid or error response envelope.")
    # The authenticated 2026 /search response has results but no success field.
    # A present success field must still be the boolean True; never coerce it.
    if "success" in body and body["success"] is not True:
        raise SchemaError("Qloo did not return success=true. Check the recorded response.")
    if insights:
        if body.get("success") is not True or not isinstance(body.get("results"), dict):
            raise SchemaError("Expected a successful Insights results object.")
    elif not isinstance(body.get("results"), list):
        raise SchemaError("Expected a lookup results array.")


def parse_entities(body: Any, *, insights: bool, synthetic: bool = False) -> list[Entity]:
    validate_response_envelope(body, insights=insights)
    results = body.get("results")
    if insights:
        if not isinstance(results, dict):
            raise SchemaError("Expected results.entities in the Insights response.")
        results = results.get("entities")
    if not isinstance(results, list):
        raise SchemaError("Expected an entity array; documentation examples are not live evidence.")
    entities: list[Entity] = []
    seen: set[str] = set()
    for row in results:
        if not isinstance(row, dict):
            raise SchemaError("An entity response entry is not an object.")
        entity_id = canonical_id(row.get("entity_id"), synthetic=synthetic)
        if entity_id in seen:
            raise SchemaError("Duplicate entity IDs in one ranking.")
        seen.add(entity_id)
        name = row.get("name")
        if not isinstance(name, str) or not name.strip():
            raise SchemaError("An entity has no usable name.")
        raw_types = row.get("types", [])
        if not isinstance(raw_types, list) or any(not isinstance(t, str) for t in raw_types):
            raise SchemaError("Entity types must be strings in an array.")
        types = set(raw_types)
        for key in ("type", "subtype"):
            if isinstance(row.get(key), str):
                types.add(row[key])
        types.discard("urn:entity")
        if not types:
            raise SchemaError("Entity category metadata is missing; context cannot be verified.")
        query = row.get("query", {})
        if not isinstance(query, dict):
            raise SchemaError("Entity query metadata is not an object.")
        affinity = query.get("affinity", row.get("affinity"))
        if affinity is not None:
            if isinstance(affinity, bool) or not isinstance(affinity, (int, float)) or not math.isfinite(affinity):
                raise SchemaError("An affinity value is not finite numeric data.")
            if not 0 <= affinity <= 1:
                raise SchemaError("Affinity is outside the documented 0–1 range.")
        properties = row.get("properties", {})
        if not isinstance(properties, dict):
            raise SchemaError("Entity properties must be an object.")
        metadata = dict(properties)
        for key in ("publication_year", "release_year", "disambiguation", "tags", "location", "popularity"):
            if key in row:
                metadata[key] = row[key]
        entities.append(Entity(entity_id, name.strip(), tuple(sorted(types)), affinity, metadata))
    return entities


def resolve_seed(seed: dict[str, Any], entities: list[Entity], *, synthetic: bool) -> Entity:
    names = {normalized_name(name) for name in seed["accepted_names"]}
    accepted_types = set(seed["accepted_types"])
    candidates = [entity for entity in entities if accepted_types.intersection(entity.types)]
    if seed.get("entity_id"):
        pinned = canonical_id(seed["entity_id"], synthetic=synthetic)
        matches = [entity for entity in candidates if entity.entity_id == pinned]
    else:
        matches = [entity for entity in candidates if normalized_name(entity.name) in names]
    if "expected_release_year" in seed:
        matches = [entity for entity in matches if entity.metadata.get("release_year") == seed["expected_release_year"]]
    if len(matches) != 1:
        detail = "; ".join(f"{e.name} [{e.entity_id}]" for e in candidates[:8]) or "no typed matches"
        raise ResolutionError(f"Cannot resolve {seed['name']} unambiguously: {detail}. Pin a reviewed entity_id in the config.")
    return matches[0]


def context_issues(entities: list[Entity], scenario: dict[str, Any], excluded: set[str]) -> list[str]:
    issues: list[str] = []
    for entity in entities:
        if scenario["filter_type"] not in entity.types:
            issues.append(f"Wrong entity category: {entity.entity_id}")
        if entity.entity_id in excluded:
            issues.append(f"An excluded interest was returned: {entity.entity_id}")
        for param in ("filter.publication_year.min", "filter.publication_year.max"):
            if param in scenario["filters"]:
                year = entity.metadata.get("publication_year")
                limit = scenario["filters"][param]
                if isinstance(year, bool) or not isinstance(year, int):
                    issues.append(f"Publication year is unknown: {entity.entity_id}")
                elif (param.endswith(".min") and year < limit) or (param.endswith(".max") and year > limit):
                    issues.append(f"Publication year violates the constraint: {entity.entity_id}")
    return issues

