from datetime import timedelta

import httpx
import pytest
from fakes import RAW, Clock, FakeDMarket
from sqlalchemy import create_engine, select
from sqlalchemy.pool import StaticPool

from app.db.models import OfferRow
from app.db.session import init_db
from app.dmarket.client import DMarketClient
from app.market.cache import MarketCache
from app.rules.schema import LocalFilters, Rule, ServerFilters

REDLINE = "AK-47 | Redline (Field-Tested)"
PAGE = 2  # tiny pages so pagination is exercised; the real cache asks for 100


@pytest.fixture
def env():
    fake, clock = FakeDMarket(), Clock()
    client = DMarketClient("ab" * 32, "cd" * 64, transport=httpx.MockTransport(fake))
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    sessions = init_db(engine)
    return fake, clock, MarketCache(client, sessions, clock), sessions


async def test_refresh_paginates_and_stores(env):
    _, _, cache, sessions = env
    result = await cache.refresh({"title": REDLINE})
    expected = sum(1 for r in RAW if r["attributes"]["title"] == REDLINE)
    assert result.offers == expected and result.complete and result.pages == -(-expected // PAGE)
    with sessions() as s:
        assert len(s.scalars(select(OfferRow)).all()) == expected


async def test_ensure_uses_cache_until_stale(env):
    fake, clock, cache, _ = env
    first = await cache.ensure({"title": REDLINE}, timedelta(hours=1))
    calls = fake.requests
    assert not first.from_cache and calls > 0

    second = await cache.ensure({"title": REDLINE}, timedelta(hours=1))
    assert second.from_cache and fake.requests == calls

    clock.now += timedelta(hours=2)
    third = await cache.ensure({"title": REDLINE}, timedelta(hours=1))
    assert not third.from_cache and fake.requests > calls


async def test_different_params_are_cached_separately(env):
    fake, _, cache, _ = env
    await cache.ensure({"title": REDLINE}, timedelta(hours=1))
    calls = fake.requests
    other = await cache.ensure({"title": REDLINE, "priceTo": 3000}, timedelta(hours=1))
    assert not other.from_cache and fake.requests > calls


async def test_max_pages_marks_result_incomplete(env):
    _, _, cache, _ = env
    result = await cache.refresh({"title": REDLINE}, max_pages=1)
    assert result.pages == 1 and not result.complete


async def test_complete_title_refresh_deactivates_vanished_offers(env):
    fake, clock, cache, sessions = env
    await cache.refresh({"title": REDLINE})
    sold = next(r for r in RAW if r["attributes"]["title"] == REDLINE)
    fake.items = [r for r in fake.items if r["offerId"] != sold["offerId"]]
    clock.now += timedelta(hours=1)
    await cache.refresh({"title": REDLINE})
    with sessions() as s:
        assert s.get(OfferRow, sold["offerId"]).active is False
        others = s.scalars(select(OfferRow).where(OfferRow.title == REDLINE, OfferRow.offer_id != sold["offerId"])).all()
        assert others and all(o.active for o in others)


async def test_filtered_refresh_does_not_deactivate_anything(env):
    _, _, cache, sessions = env
    await cache.refresh({"title": REDLINE})
    await cache.refresh({"title": REDLINE, "priceTo": 1})  # nothing that cheap: must not wipe the rest
    with sessions() as s:
        assert all(o.active for o in s.scalars(select(OfferRow).where(OfferRow.title == REDLINE)))


async def test_search_answers_from_db_without_requests(env):
    fake, _, cache, _ = env
    await cache.refresh({"title": REDLINE})
    calls = fake.requests
    rule = Rule(name="cheap", server=ServerFilters(title=REDLINE, price_to_cents=3000))
    hits = cache.search(rule)
    assert fake.requests == calls
    assert hits and all(o.price_cents <= 3000 for o in hits)
    assert [o.price_cents for o in hits] == sorted(o.price_cents for o in hits)


async def test_search_applies_local_filters(env):
    _, _, cache, _ = env
    await cache.refresh({"title": REDLINE})
    rule = Rule(name="stk", server=ServerFilters(title=REDLINE), local=LocalFilters(sticker_names=["flipsid3"]))
    hits = cache.search(rule)
    assert all(any("flipsid3" in n.lower() for n in o.sticker_names) for o in hits)


async def test_ensure_rule_builds_server_params(env):
    _, _, cache, _ = env
    rule = Rule(name="r", server=ServerFilters(title=REDLINE, price_to_cents=3000))
    result = await cache.ensure_rule(rule, timedelta(hours=1))
    assert result.offers > 0 and cache.search(rule)
