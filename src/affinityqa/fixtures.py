from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .errors import SchemaError
from .qloo import Response


class FixtureTransport:
    """Explicit, artificial contract fixture; no network access and no genuine Qloo data."""

    def __init__(self, fixture: Path) -> None:
        self.data = json.loads(fixture.read_text(encoding="utf-8"))
        if self.data.get("source") != "synthetic":
            raise SchemaError("The fixture must declare source=synthetic.")
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.catalog: dict[str, dict[str, Any]] = {}
        for kind in ("movie", "brand", "book"):
            for index in range(1, self.data["candidate_count"] + 1):
                entity_id = f"fixture:{kind}:{index:02d}"
                self.catalog[entity_id] = {"entity_id": entity_id, "name": f"Synthetic {kind} {index:02d}",
                                          "subtype": f"urn:entity:{kind}", "type": "urn:entity",
                                          "properties": {"publication_year": 1950 + index if kind == "book" else None}}
        for name, entity_id in self.data["seed_ids"].items():
            self.catalog[entity_id] = {"entity_id": entity_id, "name": name,
                                      "types": self.data["seed_types"][name], "properties": {}}

    def send(self, path: str, params: dict[str, Any]) -> Response:
        self.calls.append((path, dict(params)))
        envelope = {"success": True, "_affinityqa_fixture": {"source": "synthetic", "notice": self.data["notice"]}}
        if path == "/search":
            entity_id = self.data["seed_ids"].get(params["query"])
            envelope["results"] = [self.catalog[entity_id]] if entity_id else []
        elif path == "/entities":
            envelope["results"] = [self.catalog[item] for item in params["entity_ids"].split(",") if item in self.catalog]
        elif path == "/v2/insights":
            kind = params["filter.type"].split(":")[-1]
            ids = [f"fixture:{kind}:{index:02d}" for index in range(1, self.data["candidate_count"] + 1)]
            a_profile = set(params["signal.interests.entities"].split(",")) == set(self.data["persona_a_ids"])
            if not a_profile:
                ids.reverse()
            if "filter.results.entities" in params:
                fixed = set(params["filter.results.entities"].split(","))
                ids = [item for item in ids if item in fixed]
            rows = [{**self.catalog[item], "query": {"affinity": round(0.99 - index * 0.02, 4)}}
                    for index, item in enumerate(ids[:params["take"]])]
            envelope["results"] = {"entities": rows, "duration": 0, "query": {"fixture_only": True}}
        else:
            raise SchemaError("The fixture has no such endpoint.")
        return Response(200, envelope, {})

