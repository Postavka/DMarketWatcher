"""Candidate selection for criteria-based modes (e.g. colour build).

Pipeline: catalog skins of a side -> colour filter (image profiles, cheap) -> market prices only for the
skins that passed (DMarket requests, cached) -> ONE representative offer per skin -> ranked list.
"""
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta

from app.catalog.schemas import Side, Skin
from app.catalog.store import CatalogStore
from app.color.analyzer import ColorProfile
from app.color.service import ColorService
from app.dmarket.schemas import Offer
from app.market.cache import MarketCache
from app.market.hydrator import Hydrator


@dataclass(frozen=True)
class CandidateQuery:
    side: Side
    colors: tuple[str, ...]  # a hue group, e.g. ("blue",) or ("blue", "cyan")
    budget_cents: int | None = None  # max price of one item
    categories: tuple[str, ...] = ()  # e.g. ("Rifles",); empty = all
    weapons: tuple[str, ...] = ()  # e.g. ("M4A1-S",); empty = all
    wears: tuple[str, ...] = ()  # e.g. ("Factory New", "Minimal Wear"); empty = any
    stattrak: bool = False
    min_coverage: float = 0.03
    min_dominance: float = 0.25
    per_weapon: int | None = None  # keep at most this many candidates per weapon
    limit: int = 100  # total cap (the size of the AI input)


@dataclass(frozen=True)
class Candidate:
    skin: Skin
    offer: Offer
    coverage: float  # how much of the skin image is the requested colour
    dominance: float  # share of its painted parts that is the requested colour

    @property
    def wear(self) -> str:
        start = self.offer.title.rfind("(")
        return self.offer.title[start + 1 : -1] if start != -1 else ""


@dataclass
class SelectionStats:
    skins_in_scope: int = 0
    without_color_profile: int = 0  # image missing/failed: cannot be judged
    color_matched: int = 0
    titles_requested: int = 0
    hydrate_failed: int = 0
    with_offers_in_budget: int = 0


@dataclass
class CandidateResult:
    candidates: list[Candidate] = field(default_factory=list)
    stats: SelectionStats = field(default_factory=SelectionStats)


def _wear_ok(title: str, wears: tuple[str, ...]) -> bool:
    if not wears or "(" not in title:  # vanilla knives have no wear: never excluded by the wear filter
        return True
    return any(title.endswith(f"({wear})") for wear in wears)


class CandidateFinder:
    def __init__(self, catalog: CatalogStore, colors: ColorService, cache: MarketCache,
                 hydrator: Hydrator) -> None:
        self._catalog, self._colors, self._cache, self._hydrator = catalog, colors, cache, hydrator

    def _skins_in_scope(self, q: CandidateQuery) -> list[Skin]:
        skins = self._catalog.skins(q.side)
        if q.categories:
            skins = [s for s in skins if s.category in q.categories]
        if q.weapons:
            skins = [s for s in skins if s.weapon in q.weapons]
        return skins

    async def find(
        self,
        q: CandidateQuery,
        max_age: timedelta = timedelta(hours=6),
        on_progress: Callable[[str, int, int], None] | None = None,
    ) -> CandidateResult:
        """`on_progress(stage, done, total)` is called during the slow stages: "colors", then "prices"."""

        def stage(name: str) -> Callable[[int, int], None] | None:
            return (lambda done, total: on_progress(name, done, total)) if on_progress else None

        result = CandidateResult()
        stats = result.stats
        skins = self._skins_in_scope(q)
        stats.skins_in_scope = len(skins)

        profiles = await self._colors.ensure(skins, on_progress=stage("colors"))
        stats.without_color_profile = sum(1 for s in skins if s.skin_id not in profiles)
        matched: list[tuple[Skin, ColorProfile]] = [
            (s, profiles[s.skin_id])
            for s in skins
            if s.skin_id in profiles
            and profiles[s.skin_id].matches(q.colors, q.min_coverage, q.min_dominance)
        ]
        stats.color_matched = len({s.name for s, _ in matched})

        titles_by_skin = {
            s.skin_id: [t for t in s.market_titles(q.stattrak) if _wear_ok(t, q.wears)] for s, _ in matched
        }
        all_titles = list(dict.fromkeys(t for titles in titles_by_skin.values() for t in titles))
        stats.titles_requested = len(all_titles)
        hydrated = await self._hydrator.hydrate(all_titles, max_age, on_progress=stage("prices"))
        stats.hydrate_failed = len(hydrated.failed)

        offers = self._cache.cheapest_by_title(all_titles, q.budget_cents)
        chosen: dict[str, Candidate] = {}  # by skin name: Doppler phases etc. collapse to one
        for skin, profile in sorted(matched, key=lambda m: -m[1].coverage_of(q.colors)):
            if skin.name in chosen:
                continue
            options = [offers[t] for t in titles_by_skin[skin.skin_id] if t in offers]
            if options:
                best = min(options, key=lambda o: o.price_cents)
                chosen[skin.name] = Candidate(
                    skin, best, profile.coverage_of(q.colors), profile.dominance(q.colors)
                )
        stats.with_offers_in_budget = len(chosen)

        ranked = sorted(chosen.values(), key=lambda c: (-c.coverage, c.offer.price_cents))
        per_weapon: dict[str, int] = {}
        for candidate in ranked:
            count = per_weapon.get(candidate.skin.weapon, 0)
            if q.per_weapon is not None and count >= q.per_weapon:
                continue
            per_weapon[candidate.skin.weapon] = count + 1
            result.candidates.append(candidate)
            if len(result.candidates) >= q.limit:
                break
        return result
