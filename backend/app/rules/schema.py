"""User-defined watch rule: what the user considers a "good find".

`server` filters can be sent to DMarket in the query; `local` filters are checked on our side.
The matcher checks both, so a rule is always fully evaluated locally.
"""
from pydantic import BaseModel, Field, model_validator


class ServerFilters(BaseModel):
    title: str | None = None
    price_from_cents: int | None = Field(default=None, ge=0)
    price_to_cents: int | None = Field(default=None, ge=0)
    paint_seeds: list[int] = []

    @model_validator(mode="after")
    def _price_order(self) -> "ServerFilters":
        lo, hi = self.price_from_cents, self.price_to_cents
        if lo is not None and hi is not None and lo > hi:
            raise ValueError("price_from_cents must not exceed price_to_cents")
        return self


class LocalFilters(BaseModel):
    float_min: float | None = Field(default=None, ge=0, le=1)
    float_max: float | None = Field(default=None, ge=0, le=1)
    exterior: list[str] = []
    min_discount_percent: float | None = Field(default=None, ge=0, le=100)
    colors: list[str] = []
    sticker_names: list[str] = []
    phase: list[str] = []
    rare_pattern: list[str] = []
    stattrak: bool | None = None

    @model_validator(mode="after")
    def _float_order(self) -> "LocalFilters":
        lo, hi = self.float_min, self.float_max
        if lo is not None and hi is not None and lo > hi:
            raise ValueError("float_min must not exceed float_max")
        return self


class Rule(BaseModel):
    name: str = Field(min_length=1)
    enabled: bool = True
    server: ServerFilters = ServerFilters()
    local: LocalFilters = LocalFilters()

    def query_params(self) -> dict[str, object]:
        """Params for GET /marketplace-api/v2/offers that narrow results on DMarket's side."""
        params: dict[str, object] = {}
        s = self.server
        if s.title:
            params["title"] = s.title
        if s.price_from_cents is not None:
            params["priceFrom"] = s.price_from_cents
        if s.price_to_cents is not None:
            params["priceTo"] = s.price_to_cents
        if s.paint_seeds:
            params["treeFilters"] = ",".join(f"paintSeed[]={seed}" for seed in s.paint_seeds)
        return params
