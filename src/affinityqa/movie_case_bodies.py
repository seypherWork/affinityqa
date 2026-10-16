"""Additive HTTP bodies for confirmed movie inputs on repeatable cases only."""
from typing import Annotated

from pydantic import Field, StrictBool

from .individual_api import StrictBody, PlanBody as LegacyPlanBody, ConfirmBody as LegacyConfirmBody


MovieQuery = Annotated[str, Field(min_length=1, max_length=200)]
MovieId = Annotated[str, Field(pattern=r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$')]


class MovieQueries(StrictBody):
    A: Annotated[list[MovieQuery], Field(max_length=2)]
    B: Annotated[list[MovieQuery], Field(max_length=2)]


class MovieSelections(StrictBody):
    A: Annotated[list[MovieId], Field(max_length=2)]
    B: Annotated[list[MovieId], Field(max_length=2)]


class PlanBody(LegacyPlanBody):
    movie_queries: MovieQueries | None = None
    fast_pair_review: StrictBool = False


class ConfirmBody(LegacyConfirmBody):
    selected_movie_entity_ids: MovieSelections | None = None
