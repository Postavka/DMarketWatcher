import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.dmarket.schemas import Offer
from app.rules.matcher import match
from app.rules.schema import LocalFilters, Rule, ServerFilters

RAW = json.loads((Path(__file__).parent / "fixtures" / "offers.json").read_text(encoding="utf-8"))
OFFERS = [Offer.from_api(r) for r in RAW]


def by_title(fragment: str) -> list[Offer]:
    return [o for o in OFFERS if fragment in o.title]


def test_all_fixture_offers_parse():
    assert len(OFFERS) == len(RAW) >= 10


def test_sticker_has_no_float_or_seed():
    sticker = by_title("Sticker | 9z Team")[0]
    assert sticker.float_value is None and sticker.paint_seed is None


def test_skin_fields_are_parsed():
    redline = next(o for o in by_title("AK-47 | Redline") if not o.is_stattrak)
    assert redline.exterior == "FIELD_TESTED"
    assert isinstance(redline.float_value, float) and isinstance(redline.paint_seed, int)
    assert redline.price_cents > 0 and redline.sticker_names


def test_phase_is_parsed():
    assert {"sapphire", "phase-1"} <= {o.phase for o in by_title("Karambit | Doppler")}


def test_empty_rule_matches_everything():
    rule = Rule(name="any")
    assert all(match(o, rule).matched for o in OFFERS)


def test_title_and_price_ceiling():
    cheap = Rule(name="r", server=ServerFilters(title="AK-47 | Redline (Field-Tested)", price_to_cents=3000))
    hits = [o for o in OFFERS if match(o, cheap).matched]
    assert hits and all(o.title == "AK-47 | Redline (Field-Tested)" and o.price_cents <= 3000 for o in hits)


def test_paint_seed_filter():
    seed = by_title("Driver Gloves")[0].paint_seed
    rule = Rule(name="seed", server=ServerFilters(paint_seeds=[seed]))
    hits = [o for o in OFFERS if match(o, rule).matched]
    assert hits and all(o.paint_seed == seed for o in hits)


def test_float_range_excludes_items_without_float():
    rule = Rule(name="low float", local=LocalFilters(float_max=0.05))
    hits = [o for o in OFFERS if match(o, rule).matched]
    assert hits and all(o.float_value is not None and o.float_value <= 0.05 for o in hits)
    sticker = by_title("Sticker | 9z Team")[0]
    assert not match(sticker, rule).matched


def test_phase_filter_case_insensitive():
    rule = Rule(name="sapphire", local=LocalFilters(phase=["Sapphire"]))
    hits = [o for o in OFFERS if match(o, rule).matched]
    assert len(hits) == 1 and hits[0].phase == "sapphire"


def test_exterior_accepts_friendly_names():
    rule = Rule(name="fn", local=LocalFilters(exterior=["factory new"]))
    hits = [o for o in OFFERS if match(o, rule).matched]
    assert hits and all(o.exterior == "FACTORY_NEW" for o in hits)


def test_sticker_name_substring_match_reports_reason():
    rule = Rule(name="stk", local=LocalFilters(sticker_names=["flipsid3"]))
    hits = [(o, match(o, rule)) for o in OFFERS if match(o, rule).matched]
    for _, result in hits:
        assert any("stickers" in reason for reason in result.reasons)


def test_stattrak_flag():
    only_st = Rule(name="st", local=LocalFilters(stattrak=True))
    assert all(o.is_stattrak for o in OFFERS if match(o, only_st).matched)
    no_st = Rule(name="nost", local=LocalFilters(stattrak=False))
    assert not any(o.is_stattrak for o in OFFERS if match(o, no_st).matched)


def test_colors_filter_uses_any_of():
    rule = Rule(name="red", local=LocalFilters(colors=["red", "blue"]))
    assert all({"RED", "BLUE"} & set(o.colors) for o in OFFERS if match(o, rule).matched)


def test_query_params_for_server_filters():
    rule = Rule(
        name="q",
        server=ServerFilters(title="X", price_from_cents=100, price_to_cents=500, paint_seeds=[234, 5]),
    )
    assert rule.query_params() == {
        "title": "X", "priceFrom": 100, "priceTo": 500, "treeFilters": "paintSeed[]=234,paintSeed[]=5",
    }
    assert Rule(name="empty").query_params() == {}


@pytest.mark.parametrize(
    "build",
    [
        lambda: LocalFilters(float_min=0.5, float_max=0.1),
        lambda: ServerFilters(price_from_cents=500, price_to_cents=100),
        lambda: Rule(name=""),
    ],
)
def test_invalid_rules_are_rejected(build):
    with pytest.raises(ValidationError):
        build()
