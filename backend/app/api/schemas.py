from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.catalog.schemas import Side
from app.color.analyzer import HUES
from app.selection.candidates import Candidate, CandidateQuery, SelectionStats


class ColorBuildRequest(BaseModel):
    side: Side
    colors: list[str] = Field(min_length=1)
    budget_cents: int | None = Field(default=None, ge=1)
    categories: list[str] = []
    weapons: list[str] = []
    wears: list[str] = []
    stattrak: bool = False
    per_weapon: int | None = Field(default=None, ge=1)
    limit: int = Field(default=100, ge=1, le=300)

    @field_validator("colors")
    @classmethod
    def _known_colors(cls, colors: list[str]) -> list[str]:
        cleaned = [c.strip().lower() for c in colors]
        unknown = [c for c in cleaned if c not in HUES]
        if unknown:
            raise ValueError(f"unknown colours {unknown}; choose from {sorted(HUES)}")
        return cleaned

    def to_query(self) -> CandidateQuery:
        return CandidateQuery(
            side=self.side,
            colors=tuple(self.colors),
            budget_cents=self.budget_cents,
            categories=tuple(self.categories),
            weapons=tuple(self.weapons),
            wears=tuple(self.wears),
            stattrak=self.stattrak,
            per_weapon=self.per_weapon,
            limit=self.limit,
        )


class ShortlistRequest(BaseModel):
    request: str = Field(min_length=1, max_length=1000)
    max_picks: int = Field(default=10, ge=1, le=50)
    owned: list[str] = []


class CandidateOut(BaseModel):
    skin: str
    weapon: str
    category: str
    offer_id: str
    title: str
    wear: str
    price_cents: int
    float_value: float | None
    paint_seed: int | None
    image: str
    collection: str
    rarity: str
    coverage: float
    dominance: float

    @classmethod
    def of(cls, c: Candidate) -> "CandidateOut":
        return cls(
            skin=c.skin.name, weapon=c.skin.weapon, category=c.skin.category, offer_id=c.offer.offer_id,
            title=c.offer.title, wear=c.wear, price_cents=c.offer.price_cents, float_value=c.offer.float_value,
            paint_seed=c.offer.paint_seed, image=c.skin.image,
            collection=c.skin.collections[0] if c.skin.collections else "",
            rarity=c.skin.rarity, coverage=round(c.coverage, 4), dominance=round(c.dominance, 4),
        )


class PickOut(BaseModel):
    candidate: CandidateOut
    reason: str


class JobCreated(BaseModel):
    job_id: str


class SelectionStatsOut(BaseModel):
    skins_in_scope: int
    without_color_profile: int
    color_matched: int
    titles_requested: int
    hydrate_failed: int
    with_offers_in_budget: int

    @classmethod
    def of(cls, s: SelectionStats) -> "SelectionStatsOut":
        return cls(**vars(s))


class JobOut(BaseModel):
    id: str
    status: Literal["running", "done", "failed"]
    stage: str
    done: int
    total: int
    error: str | None = None
    candidates: list[CandidateOut] | None = None
    stats: SelectionStatsOut | None = None


class ShortlistOut(BaseModel):
    picks: list[PickOut]
    ignored: list[str]
    input_tokens: int
    output_tokens: int


class SlotOut(BaseModel):
    category: str
    weapon: str
    skins: int


class HealthOut(BaseModel):
    status: str
    catalog_skins: int
    ai_enabled: bool
