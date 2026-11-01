from datetime import timedelta

import httpx
import pytest
from fakes import RAW, Clock, FakeDMarket
from sqlalchemy import create_engine, func, select
from sqlalchemy.pool import StaticPool

from app.db.models import OfferRow
from app.db.session import init_db
from app.dmarket.client import DMarketClient
from app.market.cache import MarketCache
from app.market.hydrator import Hydrator, exact_title_params

REDLINE = "AK-47 | Redline (Field-Tested)"
DOPPLER = "★ StatTrak™ Karambit | Doppler (Factory New)"
GLOVES = "★ Driver Gloves | King Snake (Field-Tested)"
NOTHING = "M4A1-S | Cyrex (Factory New)"  # not in the fixtures: nothing listed
HOUR = timedelta(hours=1)


@pytest.fixture
def env():
    fake, clock = FakeDMarket(page_size=None, contains=True), Clock()
    client = DMarketClient("ab" * 32, "cd" * 64, max_rps=10_000, transport=httpx.MockTransport(fake))
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    sessions = init_db(engine)
    return fake, clock, Hydrator(MarketCache(client, sessions, clock)), sessions


def count(sessions, title):
    with sessions() as s:
        return s.scalar(select(func.count()).select_from(OfferRow).where(OfferRow.title == title))


async def test_hydrates_every_title_with_cheapest_offers(env):
    _, _, hydrator, sessions = env
    result = await hydrator.hydrate([REDLINE, DOPPLER, GLOVES], HOUR, per_title=2)
    assert (result.total, result.fetched, result.from_cache, result.failed) == (3, 3, 0, [])
    assert count(sessions, REDLINE) == 2 and count(sessions, DOPPLER) == 2
    cheapest = sorted(int(r["priceCents"]) for r in RAW if r["attributes"]["title"] == REDLINE)[:2]
    with sessions() as s:
        stored = sorted(s.scalars(select(OfferRow.price_cents).where(OfferRow.title == REDLINE)))
    assert stored == cheapest


async def test_plain_title_gets_only_exact_offers_not_statrak_variants(env):
    _, _, hydrator, sessions = env
    await hydrator.hydrate([REDLINE], HOUR, per_title=50)
    with sessions() as s:
        titles = set(s.scalars(select(OfferRow.title)))
    assert titles == {REDLINE}  # fixtures also hold StatTrak™ Redline offers; they must not leak in


async def test_statrak_title_gets_only_statrak_offers(env):
    _, _, hydrator, sessions = env
    st_redline = "StatTrak™ AK-47 | Redline (Field-Tested)"
    await hydrator.hydrate([st_redline], HOUR, per_title=50)
    with sessions() as s:
        assert set(s.scalars(select(OfferRow.title))) == {st_redline}


def test_exact_title_params_only_filter_plain_weapons():
    assert exact_title_params(REDLINE)["treeFilters"] == "category[]=normal"
    for title in (DOPPLER, GLOVES, "★ Karambit", "StatTrak™ AK-47 | Redline (Field-Tested)",
                  "Souvenir AWP | Dragon Lore (Factory New)"):
        assert "treeFilters" not in exact_title_params(title)


async def test_second_run_is_served_from_cache(env):
    fake, clock, hydrator, _ = env
    await hydrator.hydrate([REDLINE, GLOVES], HOUR)
    calls = fake.requests
    again = await hydrator.hydrate([REDLINE, GLOVES], HOUR)
    assert (again.fetched, again.from_cache) == (0, 2) and fake.requests == calls

    clock.now += timedelta(hours=2)
    stale = await hydrator.hydrate([REDLINE, GLOVES], HOUR)
    assert stale.fetched == 2 and fake.requests == calls + 2


async def test_empty_title_is_recorded_and_not_requeried(env):
    fake, _, hydrator, _ = env
    first = await hydrator.hydrate([NOTHING], HOUR)
    assert first.no_offers == 1 and first.fetched == 1
    calls = fake.requests
    second = await hydrator.hydrate([NOTHING], HOUR)
    assert second.from_cache == 1 and fake.requests == calls


async def test_one_failing_title_does_not_abort_the_batch(env):
    fake, _, hydrator, sessions = env
    fake.fail_titles = {DOPPLER}
    result = await hydrator.hydrate([REDLINE, DOPPLER, GLOVES], HOUR)
    assert result.failed == [DOPPLER] and result.fetched == 2
    assert count(sessions, REDLINE) > 0 and count(sessions, GLOVES) > 0 and count(sessions, DOPPLER) == 0


async def test_failed_title_is_retried_next_run(env):
    fake, _, hydrator, sessions = env
    fake.fail_titles = {REDLINE}
    await hydrator.hydrate([REDLINE], HOUR)
    fake.fail_titles = set()
    retry = await hydrator.hydrate([REDLINE], HOUR)
    assert retry.fetched == 1 and count(sessions, REDLINE) > 0


async def test_duplicates_collapse_and_progress_reaches_total(env):
    fake, _, hydrator, _ = env
    progress = []
    result = await hydrator.hydrate([REDLINE, REDLINE, GLOVES], HOUR, on_progress=lambda d, t: progress.append((d, t)))
    assert result.total == 2 and fake.requests == 2
    assert progress[-1] == (2, 2) and len(progress) == 2
