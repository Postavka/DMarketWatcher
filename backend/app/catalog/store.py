"""Static skin catalog: download, load into the DB, answer slot / skin queries."""
import json
import ssl
from dataclasses import dataclass
from pathlib import Path

import httpx
import truststore
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.catalog.schemas import Side, Skin, team_matches
from app.db.models import SkinRow

CATALOG_URL = "https://raw.githubusercontent.com/ByMykel/CSGO-API/main/public/api/en/skins.json"


@dataclass(frozen=True)
class Slot:
    category: str
    weapon: str
    skins: int


def download_catalog(dest: Path, url: str = CATALOG_URL) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    response = httpx.get(url, verify=context, timeout=60.0, follow_redirects=True)
    response.raise_for_status()
    dest.write_bytes(response.content)
    return dest


def parse_catalog(path: Path) -> list[Skin]:
    return [Skin.from_api(raw) for raw in json.loads(path.read_text(encoding="utf-8"))]


class CatalogStore:
    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._sessions = sessions

    def load(self, skins: list[Skin]) -> int:
        """Upsert skins by id. Returns how many are in the catalog afterwards."""
        with self._sessions.begin() as session:
            for skin in skins:
                row = session.get(SkinRow, skin.skin_id)
                if row is None:
                    session.add(SkinRow(**skin.model_dump()))
                else:
                    for column, value in skin.model_dump().items():
                        setattr(row, column, value)
            return session.scalar(select(func.count()).select_from(SkinRow)) or 0

    def count(self) -> int:
        with self._sessions() as session:
            return session.scalar(select(func.count()).select_from(SkinRow)) or 0

    def slots(self, side: Side) -> list[Slot]:
        """Weapons a side can use (own team or both), grouped by category."""
        stmt = (
            select(SkinRow.category, SkinRow.weapon, func.count())
            .where(SkinRow.team.in_(team_matches(side)))
            .group_by(SkinRow.category, SkinRow.weapon)
            .order_by(SkinRow.category, SkinRow.weapon)
        )
        with self._sessions() as session:
            return [Slot(c, w, n) for c, w, n in session.execute(stmt)]

    def skins(self, side: Side, category: str | None = None, weapon: str | None = None) -> list[Skin]:
        stmt = select(SkinRow).where(SkinRow.team.in_(team_matches(side)))
        if category:
            stmt = stmt.where(SkinRow.category == category)
        if weapon:
            stmt = stmt.where(SkinRow.weapon == weapon)
        with self._sessions() as session:
            return [
                Skin.model_validate({c: getattr(row, c) for c in Skin.model_fields})
                for row in session.scalars(stmt.order_by(SkinRow.name))
            ]

    def market_titles(self, side: Side, category: str | None = None, weapon: str | None = None,
                      stattrak: bool = False) -> list[str]:
        """Distinct DMarket titles to query for a slot (Doppler phases etc. collapse to one title)."""
        titles: dict[str, None] = {}
        for skin in self.skins(side, category, weapon):
            titles.update(dict.fromkeys(skin.market_titles(stattrak)))
        return list(titles)
