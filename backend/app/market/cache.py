"""Market cache: DMarket offers stored locally, refreshed only when stale.

`ensure()` hits DMarket only if the query was not fetched within `max_age`;
`search()` answers criteria queries purely from the local DB.
"""
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import FetchLog, OfferRow
from app.dmarket.client import DMarketClient, build_target
from app.dmarket.schemas import Offer, normalize_enum
from app.rules.matcher import match
from app.rules.schema import Rule

OFFERS_PATH = "/marketplace-api/v2/offers"
CS2 = "a8db"
# Params that leave "all offers of this title" intact (so missing offers really are gone).
_TITLE_ONLY_KEYS = {"gameId", "title", "orderBy", "orderDir", "limit", "cursor"}


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@dataclass
class RefreshResult:
    key: str
    from_cache: bool
    offers: int = 0
    pages: int = 0
    complete: bool = False


def query_key(params: dict[str, Any]) -> str:
    stable = {k: v for k, v in sorted(params.items()) if k not in ("cursor", "limit")}
    return build_target(OFFERS_PATH, stable)


def _row_to_offer(row: OfferRow) -> Offer:
    return Offer(
        **{c: getattr(row, c) for c in Offer.model_fields},
    )


class MarketCache:
    def __init__(
        self,
        client: DMarketClient,
        sessions: sessionmaker[Session],
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self._client = client
        self._sessions = sessions
        self._clock = clock

    async def ensure(
        self, params: dict[str, Any], max_age: timedelta, max_pages: int = 5, page_size: int = 100
    ) -> RefreshResult:
        params = {"gameId": CS2, **params}
        key = query_key(params)
        with self._sessions() as session:
            log = session.get(FetchLog, key)
            if log and self._clock() - log.fetched_at < max_age:
                return RefreshResult(key, True, log.offers_count, 0, log.complete)
        return await self.refresh(params, max_pages, page_size)

    async def ensure_rule(self, rule: Rule, max_age: timedelta, max_pages: int = 5) -> RefreshResult:
        params = {**rule.query_params(), "orderBy": "price", "orderDir": "asc"}
        return await self.ensure(params, max_age, max_pages)

    async def refresh(
        self, params: dict[str, Any], max_pages: int = 5, page_size: int = 100
    ) -> RefreshResult:
        params = {"gameId": CS2, **params}
        key = query_key(params)
        offers: list[Offer] = []
        cursor, pages, complete = None, 0, False
        while pages < max_pages:
            data = await self._client.get(OFFERS_PATH, **{**params, "limit": page_size, "cursor": cursor})
            pages += 1
            offers.extend(Offer.from_api(raw) for raw in data.get("items", []))
            cursor = data.get("cursor")
            if not cursor:
                complete = True
                break
        self._store(key, params, offers, complete)
        return RefreshResult(key, False, len(offers), pages, complete)

    def _store(self, key: str, params: dict[str, Any], offers: list[Offer], complete: bool) -> None:
        now = self._clock()
        with self._sessions.begin() as session:
            seen_ids = set()
            for offer in offers:
                seen_ids.add(offer.offer_id)
                row = session.get(OfferRow, offer.offer_id)
                data = offer.model_dump()
                if data["created_at"] is not None:
                    data["created_at"] = data["created_at"].replace(tzinfo=None)
                if row is None:
                    session.add(OfferRow(**data, active=True, first_seen=now, fetched_at=now))
                else:
                    for column, value in data.items():
                        setattr(row, column, value)
                    row.active, row.fetched_at = True, now
            # A complete title-only fetch is authoritative: anything else cached for it is gone.
            if complete and params.get("title") and set(params) <= _TITLE_ONLY_KEYS | {"gameId"}:
                stale = session.scalars(
                    select(OfferRow).where(
                        OfferRow.title == params["title"],
                        OfferRow.active.is_(True),
                        OfferRow.offer_id.not_in(seen_ids) if seen_ids else True,
                    )
                )
                for row in stale:
                    row.active = False
            log = session.get(FetchLog, key) or FetchLog(key=key)
            log.fetched_at, log.offers_count, log.complete = now, len(offers), complete
            session.add(log)

    def cheapest_by_title(self, titles: list[str], max_price_cents: int | None = None) -> dict[str, Offer]:
        """Cheapest active cached offer per exact title (titles without a match are absent)."""
        best: dict[str, Offer] = {}
        with self._sessions() as session:
            for start in range(0, len(titles), 500):  # stay under SQLite's bound-variable limit
                stmt = (
                    select(OfferRow)
                    .where(OfferRow.active.is_(True), OfferRow.title.in_(titles[start : start + 500]))
                    .order_by(OfferRow.price_cents)
                )
                if max_price_cents is not None:
                    stmt = stmt.where(OfferRow.price_cents <= max_price_cents)
                for row in session.scalars(stmt):
                    best.setdefault(row.title, _row_to_offer(row))
        return best

    def search(self, rule: Rule, limit: int = 50) -> list[Offer]:
        """Cheapest-first cached offers satisfying `rule`. SQL narrows, the matcher decides."""
        s, loc = rule.server, rule.local
        stmt = select(OfferRow).where(OfferRow.active.is_(True))
        if s.title:
            stmt = stmt.where(func.lower(OfferRow.title) == s.title.lower())
        if s.price_from_cents is not None:
            stmt = stmt.where(OfferRow.price_cents >= s.price_from_cents)
        if s.price_to_cents is not None:
            stmt = stmt.where(OfferRow.price_cents <= s.price_to_cents)
        if s.paint_seeds:
            stmt = stmt.where(OfferRow.paint_seed.in_(s.paint_seeds))
        if loc.float_min is not None:
            stmt = stmt.where(OfferRow.float_value >= loc.float_min)
        if loc.float_max is not None:
            stmt = stmt.where(OfferRow.float_value <= loc.float_max)
        if loc.exterior:
            stmt = stmt.where(OfferRow.exterior.in_([normalize_enum(e) for e in loc.exterior]))
        stmt = stmt.order_by(OfferRow.price_cents)

        found: list[Offer] = []
        with self._sessions() as session:
            for row in session.scalars(stmt):
                offer = _row_to_offer(row)
                if match(offer, rule).matched:
                    found.append(offer)
                    if len(found) >= limit:
                        break
        return found
