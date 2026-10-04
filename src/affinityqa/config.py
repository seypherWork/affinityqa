from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from .errors import SchemaError
from .qloo import INSIGHTS_EXTRA


def load_config(path: Path) -> dict[str, Any]:
    try:
        config = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(config, dict) or config.get("schema_version") != 1:
            raise SchemaError("Expected config schema_version=1.")
        for name, lower, upper in (("top_k", 1, 25), ("discovery_take", 1, 25), ("repeats", 2, 5)):
            value = config.get(name)
            if isinstance(value, bool) or not isinstance(value, int) or not lower <= value <= upper:
                raise SchemaError(f"Invalid {name}; expected {lower}..{upper}.")
        if config["top_k"] > config["discovery_take"]:
            raise SchemaError("top_k cannot exceed discovery_take.")
        thresholds = config["thresholds"]
        for name in ("reference_margin", "max_reference_jitter", "insensitivity_ceiling", "max_fidelity_drop"):
            value = thresholds[name]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value < 1:
                raise SchemaError(f"Invalid threshold: {name}.")
        if set(config["personas"]) != {"A", "B"}:
            raise SchemaError("The controlled experiment requires personas A and B.")
        for seeds in config["personas"].values():
            if not isinstance(seeds, list) or not seeds:
                raise SchemaError("Every persona needs a nonempty seed list.")
            for seed in seeds:
                for name in ("name", "query", "search_type"):
                    if not isinstance(seed[name], str) or not seed[name]:
                        raise SchemaError(f"Invalid seed {name}.")
                for name in ("accepted_names", "accepted_types"):
                    if not isinstance(seed[name], list) or not seed[name] or any(not isinstance(v, str) or not v for v in seed[name]):
                        raise SchemaError(f"Invalid seed {name}.")
        scenarios = config["scenarios"]
        if not isinstance(scenarios, list) or not scenarios or not any(s.get("required") for s in scenarios):
            raise SchemaError("At least one required scenario is needed.")
        ids = set()
        for scenario in scenarios:
            if not isinstance(scenario["id"], str) or not scenario["id"] or scenario["id"] in ids:
                raise SchemaError("Scenario IDs must be nonempty and unique.")
            ids.add(scenario["id"])
            if not isinstance(scenario["task"], str) or not scenario["task"]:
                raise SchemaError("Every scenario needs a task.")
            if not isinstance(scenario["required"], bool):
                raise SchemaError("required must be a boolean.")
            entity_type = scenario["filter_type"]
            if entity_type not in INSIGHTS_EXTRA or not isinstance(scenario["filters"], dict):
                raise SchemaError("Unknown scenario entity type or invalid filters.")
            if set(scenario["filters"]) - INSIGHTS_EXTRA[entity_type]:
                raise SchemaError("A scenario contains an unreviewed filter for its entity type.")
            for value in scenario["filters"].values():
                if isinstance(value, bool) or not isinstance(value, int):
                    raise SchemaError("Publication year constraints must be integers.")
        return config
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise SchemaError("Invalid or unreadable config. Review evals/qloo.json.") from None

