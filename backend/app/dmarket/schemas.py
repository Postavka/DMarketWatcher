from datetime import datetime
from typing import Any

from pydantic import BaseModel


def normalize_enum(value: str) -> str:
    """'EXTERIOR_FIELD_TESTED' / 'field tested' / 'Field-Tested' -> 'FIELD_TESTED'."""
    text = value.strip().upper().replace("-", "_").replace(" ", "_")
    for prefix in ("EXTERIOR_", "COLOR_", "RARE_PATTERN_"):
        text = text.removeprefix(prefix)
    # DMarket enums use '<PREFIX>_UNSPECIFIED' for "not applicable"; treat as empty.
    return "" if text == "UNSPECIFIED" else text


class Offer(BaseModel):
    """One marketplace offer, flattened from the v2 offers response."""

    offer_id: str
    title: str
    price_cents: int
    discount_percent: float = 0
    created_at: datetime | None = None
    item_type: str = ""
    exterior: str = ""
    float_value: float | None = None
    paint_seed: int | None = None
    phase: str = ""
    rare_pattern: str = ""
    collection: str = ""
    colors: list[str] = []
    sticker_names: list[str] = []
    is_stattrak: bool = False

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> "Offer":
        attrs = raw.get("attributes", {})
        cs2 = attrs.get("cs2", {})
        title = attrs.get("title", "")
        exterior = normalize_enum(cs2.get("exterior", ""))
        float_raw = cs2.get("float")
        # Stickers, cases etc. report float "0" with no exterior: that is "no float", not 0.0.
        has_float = bool(float_raw) and bool(exterior)
        return cls(
            offer_id=raw["offerId"],
            title=title,
            price_cents=int(raw["priceCents"]),
            discount_percent=raw.get("discountPercent") or 0,
            created_at=raw.get("createdAt"),
            item_type=cs2.get("itemType", ""),
            exterior=exterior,
            float_value=float(float_raw) if has_float else None,
            paint_seed=cs2.get("paintSeed") if has_float else None,
            phase=cs2.get("phase", ""),
            rare_pattern=normalize_enum(cs2.get("rarePattern", "")),
            collection=cs2.get("collection", ""),
            colors=[normalize_enum(c) for c in cs2.get("colors", [])],
            sticker_names=[s["name"] for s in cs2.get("stickers", []) if s.get("name")],
            is_stattrak="StatTrak" in title,
        )
