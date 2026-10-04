"""Ordinal ranking metrics; API affinity is evidence, never a calibrated probability."""
from __future__ import annotations

from itertools import combinations
from math import log2
from typing import Sequence

from .errors import SchemaError


def validate_ranking(ranking: Sequence[str], *, minimum: int = 1) -> None:
    if len(ranking) < minimum or any(not isinstance(item, str) or not item for item in ranking):
        raise SchemaError("Ranking is too short or contains invalid IDs.")
    if len(set(ranking)) != len(ranking):
        raise SchemaError("A ranking cannot contain duplicate IDs.")


def ndcg_at_k(actual: Sequence[str], reference: Sequence[str], k: int) -> float:
    """Linear ordinal gains M-r+1; absent reference IDs get zero gain."""
    if isinstance(k, bool) or not isinstance(k, int) or k < 1:
        raise SchemaError("k must be a positive integer.")
    validate_ranking(actual, minimum=k)
    validate_ranking(reference, minimum=k)
    gains = {entity_id: len(reference) - rank for rank, entity_id in enumerate(reference)}
    ideal = sum(gains[item] / log2(rank + 2) for rank, item in enumerate(reference[:k]))
    actual_dcg = sum(gains.get(item, 0) / log2(rank + 2) for rank, item in enumerate(actual[:k]))
    return actual_dcg / ideal


def rank_distance(left: Sequence[str], right: Sequence[str], k: int) -> float:
    validate_ranking(left, minimum=k)
    validate_ranking(right, minimum=k)
    if set(left) != set(right) or len(left) != len(right):
        raise SchemaError("Rank distance requires complete rankings over the same fixed candidate set.")
    return max(0.0, 1 - (ndcg_at_k(left, right, k) + ndcg_at_k(right, left, k)) / 2)


def top_k_overlap(left: Sequence[str], right: Sequence[str], k: int) -> float:
    validate_ranking(left, minimum=k)
    validate_ranking(right, minimum=k)
    return len(set(left[:k]).intersection(right[:k])) / k


def directional_alignment(agent_a: Sequence[str], agent_b: Sequence[str], reference_a: Sequence[str],
                          reference_b: Sequence[str], k: int) -> float:
    """Signed own-persona advantage; an invariant agent scores exactly zero."""
    return ((ndcg_at_k(agent_a, reference_a, k) - ndcg_at_k(agent_a, reference_b, k))
            + (ndcg_at_k(agent_b, reference_b, k) - ndcg_at_k(agent_b, reference_a, k))) / 2


def max_repeat_jitter(rankings: list[list[str]], k: int) -> float:
    if len(rankings) < 2:
        raise SchemaError("At least two uncached repeats are required to estimate jitter.")
    return max(rank_distance(a, b, k) for a, b in combinations(rankings, 2))

