import io
from pathlib import Path

import httpx
import pytest
from fakes import Clock
from PIL import Image
from sqlalchemy import create_engine, select
from sqlalchemy.pool import StaticPool

from app.catalog.schemas import Skin
from app.color.analyzer import analyze_image
from app.color.service import ColorService
from app.db.models import SkinColorRow
from app.db.session import init_db

IMAGES = Path(__file__).parent / "fixtures" / "images"
BLUE_GROUP = ("blue",)


def real(name: str):
    return analyze_image((IMAGES / f"{name}.png").read_bytes())


def solid(rgb, size=(40, 30), alpha=255) -> Image.Image:
    return Image.new("RGBA", size, (*rgb, alpha))


# ---- synthetic images -------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("rgb", "expected"),
    [((220, 30, 30), "red"), ((240, 140, 20), "orange"), ((230, 220, 30), "yellow"), ((40, 200, 60), "green"),
     ((30, 220, 220), "cyan"), ((30, 70, 230), "blue"), ((140, 40, 220), "purple"), ((230, 60, 160), "pink")],
)
def test_solid_colours_are_named_correctly(rgb, expected):
    profile = analyze_image(solid(rgb))
    assert profile.coverage[expected] == pytest.approx(1.0)
    assert profile.dominance(expected) == pytest.approx(1.0)


@pytest.mark.parametrize(("rgb", "expected"), [((10, 10, 10), "black"), ((250, 250, 250), "white"), ((128, 128, 128), "gray")])
def test_achromatic_pixels_are_not_coloured(rgb, expected):
    profile = analyze_image(solid(rgb))
    assert profile.coverage[expected] == pytest.approx(1.0)
    assert profile.chromatic == 0 and profile.dominance("blue") == 0 and not profile.matches("blue")


def test_transparent_pixels_are_ignored():
    image = solid((30, 70, 230), size=(40, 30))
    image.paste((0, 0, 0, 0), (0, 0, 40, 20))  # two thirds of the image fully transparent
    profile = analyze_image(image)
    assert profile.coverage["blue"] == pytest.approx(1.0)  # share of OPAQUE pixels


def test_fully_transparent_image_has_empty_profile():
    profile = analyze_image(solid((30, 70, 230), alpha=0))
    assert profile.coverage == {} and profile.chromatic == 0 and not profile.matches("blue")


def test_unpainted_gun_with_small_blue_accent():
    image = solid((90, 90, 95), size=(100, 100))  # gunmetal
    image.paste((30, 70, 230, 255), (0, 0, 10, 100))  # 10% blue
    profile = analyze_image(image)
    assert profile.coverage["blue"] == pytest.approx(0.10, abs=0.02)
    assert profile.dominance("blue") == pytest.approx(1.0)
    assert profile.matches("blue")
    assert not profile.matches("blue", min_coverage=0.2)  # visible area requirement is adjustable


def test_tiny_accent_does_not_count_as_blue():
    image = solid((90, 90, 95), size=(100, 100))
    image.paste((30, 70, 230, 255), (0, 0, 1, 100))  # 1%
    assert not analyze_image(image).matches("blue")


def test_blue_must_dominate_among_coloured_parts():
    image = solid((90, 90, 95), size=(100, 100))
    image.paste((220, 30, 30, 255), (0, 0, 40, 100))  # 40% red
    image.paste((30, 70, 230, 255), (40, 0, 50, 100))  # 10% blue -> 20% of coloured pixels
    profile = analyze_image(image)
    assert profile.coverage["blue"] >= 0.03 and not profile.matches("blue")


def test_group_of_neighbouring_hues():
    image = solid((90, 90, 95), size=(100, 100))
    image.paste((30, 70, 230, 255), (0, 0, 10, 100))
    image.paste((30, 220, 220, 255), (10, 0, 20, 100))
    profile = analyze_image(image)
    assert profile.coverage_of(("blue", "cyan")) == pytest.approx(0.20, abs=0.03)
    assert profile.matches(("blue", "cyan"), min_coverage=0.15)
    assert not profile.matches("blue", min_coverage=0.15)


def test_analyzer_accepts_png_bytes():
    buffer = io.BytesIO()
    solid((30, 70, 230)).save(buffer, format="PNG")
    assert analyze_image(buffer.getvalue()).matches("blue")


# ---- real skin renders (regression for the thresholds) ----------------------------------------

@pytest.mark.parametrize("name", ["AK47__Blue_Laminate", "USPS__Blueprint", "AWP__Atheris", "M4A4__Desolate_Space"])
def test_known_blue_skins_match_blue(name):
    assert real(name).matches("blue")


@pytest.mark.parametrize("name", ["AK47__Redline", "M4A1S__Cyrex", "AK47__Slate", "SSG_08__Blue_Spruce"])
def test_known_non_blue_skins_do_not_match_blue(name):
    assert not real(name).matches("blue")


def test_teal_blue_spruce_is_cyan_not_blue():
    # Its name says blue but the render is mint/teal: the group ("blue", "cyan") is how a user would opt in.
    assert real("SSG_08__Blue_Spruce").coverage.get("blue", 0) < 0.01
    assert real("AK47__Redline").matches("red")
    assert real("M4A1S__Cyrex").matches("red")


def test_blue_laminate_ranks_below_blueprint_by_coverage():
    assert real("USPS__Blueprint").coverage_of("blue") > real("AK47__Blue_Laminate").coverage_of("blue")


# ---- ColorService ----------------------------------------------------------------------------

def make_skin(skin_id: str, image: str = "") -> Skin:
    return Skin(skin_id=skin_id, name=skin_id, weapon="W", category="Rifles", team="both", image=image)


@pytest.fixture
def service_env():
    pngs = {"https://img/blue.png": solid((30, 70, 230)), "https://img/red.png": solid((220, 30, 30))}
    hits: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        hits.append(url)
        if url not in pngs:
            return httpx.Response(404)
        buffer = io.BytesIO()
        pngs[url].save(buffer, format="PNG")
        return httpx.Response(200, content=buffer.getvalue())

    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    sessions = init_db(engine)
    return ColorService(sessions, transport=httpx.MockTransport(handler), clock=Clock()), sessions, hits


async def test_service_computes_stores_and_reuses(service_env):
    service, sessions, hits = service_env
    skins = [make_skin("a", "https://img/blue.png"), make_skin("b", "https://img/red.png")]
    first = await service.ensure(skins)
    assert first["a"].matches("blue") and first["b"].matches("red") and len(hits) == 2
    with sessions() as s:
        assert {r.skin_id for r in s.scalars(select(SkinColorRow))} == {"a", "b"}

    second = await service.ensure(skins)
    assert len(hits) == 2 and second["a"].matches("blue")  # nothing downloaded again
    assert service.profiles(["a"])["a"].matches("blue")
    await service.aclose()


async def test_service_skips_failed_and_imageless_skins(service_env):
    service, _, hits = service_env
    skins = [make_skin("ok", "https://img/blue.png"), make_skin("gone", "https://img/missing.png"), make_skin("noimg")]
    progress = []
    result = await service.ensure(skins, on_progress=lambda d, t: progress.append((d, t)))
    assert set(result) == {"ok"} and progress[-1] == (2, 2)
    assert "https://img/missing.png" in hits
    retry = await service.ensure(skins)  # failed ones are retried, imageless are never fetched
    assert set(retry) == {"ok"} and hits.count("https://img/missing.png") == 2
    await service.aclose()
