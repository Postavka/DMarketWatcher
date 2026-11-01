from typing import Any, Literal

from pydantic import BaseModel

Side = Literal["ct", "t"]
TEAM_BY_SIDE = {"ct": "counter-terrorists", "t": "terrorists"}


class Skin(BaseModel):
    """One catalog skin, flattened from a ByMykel/CSGO-API `skins.json` entry."""

    skin_id: str
    name: str
    weapon: str
    category: str
    team: str
    pattern: str = ""
    paint_index: str = ""
    rarity: str = ""
    min_float: float | None = None
    max_float: float | None = None
    wears: list[str] = []
    collections: list[str] = []
    image: str = ""
    stattrak: bool = False
    souvenir: bool = False

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> "Skin":
        return cls(
            skin_id=raw["id"],
            name=raw["name"],
            weapon=raw["weapon"]["name"],
            category=raw["category"]["name"],
            team=raw["team"]["id"],
            pattern=(raw.get("pattern") or {}).get("name", ""),
            paint_index=str(raw.get("paint_index") or ""),
            rarity=(raw.get("rarity") or {}).get("name", ""),
            min_float=raw.get("min_float"),
            max_float=raw.get("max_float"),
            wears=[w["name"] for w in raw.get("wears", [])],
            collections=[c["name"] for c in raw.get("collections", [])],
            image=raw.get("image", ""),
            stattrak=bool(raw.get("stattrak")),
            souvenir=bool(raw.get("souvenir")),
        )

    def market_titles(self, stattrak: bool = False) -> list[str]:
        """DMarket/Steam market titles for this skin, one per wear (vanilla knives have none)."""
        name = self.name
        if stattrak:
            if not self.stattrak:
                return []
            name = name.replace("★ ", "★ StatTrak™ ", 1) if name.startswith("★ ") else f"StatTrak™ {name}"
        if not self.wears:
            return [name]
        return [f"{name} ({wear})" for wear in self.wears]


def team_matches(side: Side) -> tuple[str, str]:
    """Catalog `team` values usable on a side: its own and 'both'."""
    return TEAM_BY_SIDE[side], "both"
