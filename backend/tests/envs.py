"""Shared test environment: catalog sample + fake DMarket + fake image host, wired into a CandidateFinder."""
import io
from pathlib import Path
from types import SimpleNamespace

import httpx
from fakes import Clock, FakeDMarket, raw_offer
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app.catalog.store import CatalogStore, parse_catalog
from app.color.service import ColorService
from app.db.session import init_db
from app.dmarket.client import DMarketClient
from app.market.cache import MarketCache
from app.market.hydrator import Hydrator
from app.selection.candidates import CandidateFinder

FIXTURES = Path(__file__).parent / "fixtures"

# Which test image stands in for which catalog skin (names are real; images are fixtures).
IMAGE_BY_NAME = {
    "AWP | Atheris": "AWP__Atheris",  # blue-ish
    "M4A4 | Howl": "M4A4__Desolate_Space",  # stand-in blue skin, CT only
    "★ Karambit | Doppler": "USPS__Blueprint",  # blue; two catalog entries share this name
    "★ Karambit": "USPS__Blueprint",  # blue vanilla knife: has no wear in its title
    "M4A1-S | Cyrex": "M4A1S__Cyrex",  # red
    "AK-47 | Redline": "AK47__Redline",  # red, T only
}

OFFERS = [
    raw_offer("AWP | Atheris (Factory New)", 3000),
    raw_offer("AWP | Atheris (Minimal Wear)", 1200),
    raw_offer("AWP | Atheris (Field-Tested)", 624),
    raw_offer("AWP | Atheris (Battle-Scarred)", 300),
    raw_offer("StatTrak™ AWP | Atheris (Field-Tested)", 2000),
    raw_offer("M4A4 | Howl (Factory New)", 500000),
    raw_offer("M4A4 | Howl (Minimal Wear)", 400000),
    raw_offer("★ Karambit | Doppler (Factory New)", 40000),
    raw_offer("M4A1-S | Cyrex (Field-Tested)", 15000),
    raw_offer("AK-47 | Redline (Field-Tested)", 2400),
]


def png(name: str | None) -> bytes:
    buffer = io.BytesIO()
    if name:
        Image.open(FIXTURES / "images" / f"{name}.png").save(buffer, format="PNG")
    else:
        Image.new("RGBA", (40, 30), (120, 120, 125, 255)).save(buffer, format="PNG")  # gunmetal
    return buffer.getvalue()


def build_env() -> SimpleNamespace:
    skins = parse_catalog(FIXTURES / "skins_sample.json")
    images = {s.image: png(IMAGE_BY_NAME.get(s.name)) for s in skins}
    image_hits: list[str] = []

    def image_handler(request: httpx.Request) -> httpx.Response:
        image_hits.append(str(request.url))
        return httpx.Response(200, content=images[str(request.url)])

    fake = FakeDMarket(OFFERS, page_size=None, contains=True)
    clock = Clock()
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    sessions = init_db(engine)
    catalog = CatalogStore(sessions)
    catalog.load(skins)
    client = DMarketClient("ab" * 32, "cd" * 64, max_rps=10_000, transport=httpx.MockTransport(fake))
    cache = MarketCache(client, sessions, clock)
    colors = ColorService(sessions, transport=httpx.MockTransport(image_handler), clock=clock)
    finder = CandidateFinder(catalog, colors, cache, Hydrator(cache))
    return SimpleNamespace(finder=finder, fake=fake, image_hits=image_hits, catalog=catalog,
                           sessions=sessions, colors=colors, cache=cache)
