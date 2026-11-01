"""Application wiring: builds every service once and owns their lifecycle."""
import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path

from app.ai.shortlist import Shortlister, make_anthropic_client
from app.catalog.store import CatalogStore, download_catalog, parse_catalog
from app.color.service import ColorService
from app.config import Settings
from app.db.session import init_db, make_engine
from app.dmarket.client import DMarketClient
from app.jobs import JobRegistry
from app.market.cache import MarketCache
from app.market.hydrator import Hydrator
from app.selection.candidates import CandidateFinder

log = logging.getLogger(__name__)
CATALOG_FILE = Path("data/catalog/skins.json")


@dataclass
class AppState:
    catalog: CatalogStore
    finder: CandidateFinder
    shortlister: Shortlister | None  # None until ANTHROPIC_API_KEY is configured
    jobs: JobRegistry = field(default_factory=JobRegistry)
    closers: list[Callable[[], Awaitable[None]]] = field(default_factory=list)

    async def aclose(self) -> None:
        for close in self.closers:
            await close()


def build_state(settings: Settings) -> AppState:
    sessions = init_db(make_engine())
    dmarket = DMarketClient(
        settings.dmarket_public_key,
        settings.dmarket_secret_key.get_secret_value(),
        settings.dmarket_base_url,
        settings.dmarket_max_rps,
    )
    cache = MarketCache(dmarket, sessions)
    colors = ColorService(sessions)
    catalog = CatalogStore(sessions)
    state = AppState(
        catalog=catalog,
        finder=CandidateFinder(catalog, colors, cache, Hydrator(cache)),
        shortlister=None,
        closers=[dmarket.aclose, colors.aclose],
    )
    if settings.anthropic_api_key:
        client = make_anthropic_client(settings.anthropic_api_key.get_secret_value())
        state.shortlister = Shortlister(client, settings.ai_model, settings.ai_effort)
        state.closers.append(client.close)
    return state


async def ensure_catalog(state: AppState) -> None:
    """Load the skin catalog on first run (downloads it once). Failure is logged, not fatal."""
    if state.catalog.count():
        return
    try:
        if not CATALOG_FILE.exists():
            await asyncio.to_thread(download_catalog, CATALOG_FILE)
        total = state.catalog.load(parse_catalog(CATALOG_FILE))
        log.info("catalog loaded: %d skins", total)
    except Exception:
        log.exception("could not load the skin catalog; run scripts/load_catalog.py")
