from datetime import timedelta

import httpx
import pytest
from envs import build_env
from fakes import raw_offer

from app.selection.candidates import CandidateQuery

HOUR = timedelta(hours=1)


@pytest.fixture
def env():
    e = build_env()
    return e.finder, e.fake, e.image_hits

def names(result):
    return [c.skin.name for c in result.candidates]


async def test_ct_blue_returns_one_representative_per_skin(env):
    finder, _, _ = env
    result = await finder.find(CandidateQuery(side="ct", colors=("blue",)))
    assert set(names(result)) == {"AWP | Atheris", "M4A4 | Howl", "★ Karambit | Doppler"}
    assert len(names(result)) == len(set(names(result)))  # Doppler phases collapsed to one
    atheris = next(c for c in result.candidates if c.skin.name == "AWP | Atheris")
    assert atheris.offer.title == "AWP | Atheris (Battle-Scarred)"  # cheapest across all wears
    assert atheris.offer.price_cents == 300 and atheris.wear == "Battle-Scarred"


async def test_non_blue_skins_are_excluded(env):
    finder, _, _ = env
    result = await finder.find(CandidateQuery(side="ct", colors=("blue",)))
    assert "M4A1-S | Cyrex" not in names(result)


async def test_side_filter(env):
    finder, _, _ = env
    t = await finder.find(CandidateQuery(side="t", colors=("blue",)))
    assert "M4A4 | Howl" not in names(t) and "AWP | Atheris" in names(t)  # AWP is for both sides
    red_t = await finder.find(CandidateQuery(side="t", colors=("red",)))
    assert names(red_t) == ["AK-47 | Redline"]


async def test_budget_drops_skins_without_an_affordable_offer(env):
    finder, _, _ = env
    result = await finder.find(CandidateQuery(side="ct", colors=("blue",), budget_cents=10_000))
    assert set(names(result)) == {"AWP | Atheris"}
    assert all(c.offer.price_cents <= 10_000 for c in result.candidates)


async def test_wear_filter_limits_titles_and_choice(env):
    finder, _, _ = env
    result = await finder.find(
        CandidateQuery(side="ct", colors=("blue",), weapons=("AWP",), wears=("Factory New", "Minimal Wear"))
    )
    (atheris,) = result.candidates
    assert atheris.offer.title == "AWP | Atheris (Minimal Wear)" and atheris.offer.price_cents == 1200


async def test_vanilla_style_titles_without_wear_pass_wear_filter(env):
    finder, fake, _ = env
    fake.items.append(raw_offer("★ Karambit", 30000))
    result = await finder.find(
        CandidateQuery(side="ct", colors=("blue",), weapons=("Karambit",), wears=("Factory New",))
    )
    assert set(names(result)) == {"★ Karambit", "★ Karambit | Doppler"}
    vanilla = next(c for c in result.candidates if c.skin.name == "★ Karambit")
    assert vanilla.offer.title == "★ Karambit" and vanilla.wear == ""


async def test_only_colour_matches_hit_the_market(env):
    finder, fake, _ = env
    await finder.find(CandidateQuery(side="ct", colors=("blue",)))
    queried = " ".join(fake.queried_titles)
    assert "Atheris" in queried and "Howl" in queried and "Doppler" in queried
    assert "Cyrex" not in queried and "Redline" not in queried  # saved requests


async def test_stats_are_reported(env):
    finder, _, _ = env
    stats = (await finder.find(CandidateQuery(side="ct", colors=("blue",)))).stats
    assert stats.skins_in_scope > stats.color_matched == 4  # Atheris, Howl, Doppler, vanilla Karambit
    assert stats.with_offers_in_budget == 3  # the vanilla Karambit has no listing and stats.hydrate_failed == 0 and stats.without_color_profile == 0
    assert stats.titles_requested > 0


async def test_stattrak_uses_stattrak_titles(env):
    finder, _, _ = env
    result = await finder.find(CandidateQuery(side="ct", colors=("blue",), stattrak=True, weapons=("AWP",)))
    (atheris,) = result.candidates
    assert atheris.offer.title == "StatTrak™ AWP | Atheris (Field-Tested)" and atheris.offer.is_stattrak


async def test_second_search_uses_caches(env):
    finder, fake, image_hits = env
    q = CandidateQuery(side="ct", colors=("blue",))
    await finder.find(q)
    requests, images = fake.requests, len(image_hits)
    again = await finder.find(q)
    assert fake.requests == requests and len(image_hits) == images and again.candidates


async def test_ranking_and_limits(env):
    finder, _, _ = env
    q = CandidateQuery(side="ct", colors=("blue",))
    ranked = (await finder.find(q)).candidates
    assert [c.coverage for c in ranked] == sorted((c.coverage for c in ranked), reverse=True)
    limited = (await finder.find(CandidateQuery(side="ct", colors=("blue",), limit=2))).candidates
    assert [c.skin.name for c in limited] == [c.skin.name for c in ranked[:2]]


async def test_per_weapon_cap(env):
    finder, fake, _ = env
    fake.items.append(raw_offer("★ Karambit", 30000))
    q = CandidateQuery(side="ct", colors=("blue",), weapons=("Karambit",), per_weapon=1)
    (only,) = (await finder.find(q)).candidates
    assert only.skin.weapon == "Karambit"


async def test_category_filter(env):
    finder, _, _ = env
    result = await finder.find(CandidateQuery(side="ct", colors=("blue",), categories=("Knives",)))
    assert names(result) == ["★ Karambit | Doppler"]


async def test_missing_images_are_counted_not_fatal(env):
    finder, _, _ = env
    finder._colors._http = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    result = await finder.find(CandidateQuery(side="ct", colors=("blue",)))
    assert result.candidates == [] and result.stats.without_color_profile == result.stats.skins_in_scope
