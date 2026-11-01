import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app.catalog.schemas import Skin
from app.catalog.store import CatalogStore, parse_catalog
from app.db.session import init_db

SAMPLE = Path(__file__).parent / "fixtures" / "skins_sample.json"


@pytest.fixture
def store() -> CatalogStore:
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    s = CatalogStore(init_db(engine))
    s.load(parse_catalog(SAMPLE))
    return s


def weapons(slots):
    return {s.weapon for s in slots}


def test_parse_sample_catalog():
    skins = parse_catalog(SAMPLE)
    assert len(skins) == len(json.loads(SAMPLE.read_text(encoding="utf-8")))
    cyrex = next(s for s in skins if s.name == "M4A1-S | Cyrex")
    assert cyrex.team == "counter-terrorists" and cyrex.category == "Rifles"
    assert cyrex.weapon == "M4A1-S" and cyrex.image.startswith("http") and cyrex.stattrak


def test_slots_by_side(store):
    ct, t = weapons(store.slots("ct")), weapons(store.slots("t"))
    assert {"M4A1-S", "M4A4", "USP-S", "FAMAS", "MP9", "Five-SeveN"} <= ct
    assert not ct & {"AK-47", "Glock-18", "Galil AR", "Tec-9"}
    assert {"AK-47", "Glock-18", "Galil AR", "Tec-9"} <= t
    assert not t & {"M4A1-S", "USP-S", "FAMAS"}
    both = {"AWP", "Desert Eagle", "Karambit", "Driver Gloves", "Hand Wraps"}
    assert both <= ct and both <= t


def test_slots_group_by_category(store):
    categories = {s.category for s in store.slots("ct")}
    assert {"Rifles", "Pistols", "SMGs", "Knives", "Gloves"} <= categories


def test_skins_filter_by_category_and_weapon(store):
    assert {s.weapon for s in store.skins("ct", category="Pistols")} == {"USP-S", "Five-SeveN", "Desert Eagle"}
    assert {s.weapon for s in store.skins("t", category="Pistols")} == {"Glock-18", "Tec-9", "Desert Eagle"}
    assert [s.name for s in store.skins("ct", weapon="M4A1-S")] == ["M4A1-S | Cyrex"]


def test_market_titles_per_wear(store):
    titles = store.market_titles("ct", weapon="M4A1-S")
    assert titles[0] == "M4A1-S | Cyrex (Factory New)" and len(titles) == 5
    assert "M4A1-S | Cyrex (Battle-Scarred)" in titles


def test_vanilla_knife_has_no_wear_and_doppler_phases_collapse(store):
    titles = store.market_titles("t", weapon="Karambit")
    assert "★ Karambit" in titles
    assert titles.count("★ Karambit | Doppler (Factory New)") == 1
    assert len(titles) == len(set(titles))


def test_stattrak_titles_keep_star_prefix(store):
    titles = store.market_titles("t", weapon="Karambit", stattrak=True)
    assert "★ StatTrak™ Karambit | Doppler (Factory New)" in titles
    assert "★ StatTrak™ Karambit" in titles
    gloves = store.market_titles("t", weapon="Driver Gloves", stattrak=True)
    assert gloves == []  # gloves have no StatTrak


def test_stattrak_for_regular_weapon():
    cyrex = next(s for s in parse_catalog(SAMPLE) if s.name == "M4A1-S | Cyrex")
    assert cyrex.market_titles(stattrak=True)[0] == "StatTrak™ M4A1-S | Cyrex (Factory New)"


def test_load_is_idempotent(store):
    before = len(store.skins("ct")) + len(store.skins("t"))
    store.load(parse_catalog(SAMPLE))
    assert len(store.skins("ct")) + len(store.skins("t")) == before


def test_skin_model_defaults():
    skin = Skin(skin_id="x", name="N", weapon="W", category="C", team="both")
    assert skin.market_titles() == ["N"]
