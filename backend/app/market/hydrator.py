"""Fill the market cache for a batch of titles (e.g. one loadout slot), only where stale."""
import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta

import httpx

from app.market.cache import MarketCache

log = logging.getLogger(__name__)


@dataclass
class HydrateResult:
    total: int = 0
    fetched: int = 0  # titles requested from DMarket this run
    from_cache: int = 0  # titles still fresh in the cache
    no_offers: int = 0  # titles with nothing listed (also cached, so not re-queried until stale)
    failed: list[str] = field(default_factory=list)


def exact_title_params(title: str) -> dict[str, str]:
    """Query params returning only offers of exactly `title`.

    DMarket's `title` is a substring search, so 'AK-47 | Redline (Field-Tested)' also returns its
    StatTrak and Souvenir versions. `category[]=normal` removes them; it is only valid (and needed)
    for plain weapon titles: knives/gloves start with '★' and are already unambiguous, and
    StatTrak/Souvenir titles carry their prefix.
    """
    params = {"title": title, "orderBy": "price", "orderDir": "asc"}
    if not title.startswith(("★", "StatTrak™", "Souvenir")):
        params["treeFilters"] = "category[]=normal"
    return params


class Hydrator:
    def __init__(self, cache: MarketCache, concurrency: int = 8) -> None:
        self._cache = cache
        self._concurrency = concurrency

    async def hydrate(
        self,
        titles: list[str],
        max_age: timedelta,
        per_title: int = 5,
        on_progress: Callable[[int, int], None] | None = None,
    ) -> HydrateResult:
        """Cache the `per_title` cheapest offers of every title. One bad title never aborts the batch."""
        unique = list(dict.fromkeys(titles))
        result = HydrateResult(total=len(unique))
        gate = asyncio.Semaphore(self._concurrency)
        done = 0

        async def one(title: str) -> None:
            nonlocal done
            async with gate:
                try:
                    r = await self._cache.ensure(
                        exact_title_params(title),
                        max_age,
                        max_pages=1,
                        page_size=per_title,
                    )
                except httpx.HTTPError as exc:
                    log.warning("hydrate failed for %r: %s", title, exc)
                    result.failed.append(title)
                else:
                    if r.from_cache:
                        result.from_cache += 1
                    else:
                        result.fetched += 1
                    if r.offers == 0:
                        result.no_offers += 1
            done += 1
            if on_progress:
                on_progress(done, result.total)

        await asyncio.gather(*(one(t) for t in unique))
        return result
