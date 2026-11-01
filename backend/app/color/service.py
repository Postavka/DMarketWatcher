"""Compute and store image colour profiles for catalog skins."""
import asyncio
import logging
import ssl
from collections.abc import Callable
from datetime import datetime

import httpx
import truststore
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.catalog.schemas import Skin
from app.color.analyzer import ColorProfile, analyze_image
from app.db.models import SkinColorRow
from app.market.cache import utcnow

log = logging.getLogger(__name__)


class ColorService:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        transport: httpx.AsyncBaseTransport | None = None,
        concurrency: int = 8,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self._sessions = sessions
        self._http = httpx.AsyncClient(
            transport=transport,
            timeout=30.0,
            follow_redirects=True,
            verify=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT),
        )
        self._gate = asyncio.Semaphore(concurrency)
        self._clock = clock

    def profiles(self, skin_ids: list[str]) -> dict[str, ColorProfile]:
        """Stored profiles for the skins that have one."""
        with self._sessions() as session:
            rows = session.scalars(select(SkinColorRow).where(SkinColorRow.skin_id.in_(skin_ids)))
            return {r.skin_id: ColorProfile(r.coverage, r.chromatic) for r in rows}

    async def ensure(
        self, skins: list[Skin], on_progress: Callable[[int, int], None] | None = None
    ) -> dict[str, ColorProfile]:
        """Profiles for all `skins`, computing only the missing ones. Skins whose image fails are omitted."""
        result = self.profiles([s.skin_id for s in skins])
        missing = [s for s in skins if s.skin_id not in result and s.image]
        done = 0

        async def one(skin: Skin) -> None:
            nonlocal done
            async with self._gate:
                try:
                    response = await self._http.get(skin.image)
                    response.raise_for_status()
                    profile = await asyncio.to_thread(analyze_image, response.content)
                except (httpx.HTTPError, OSError) as exc:
                    log.warning("colour analysis failed for %s: %s", skin.name, exc)
                else:
                    self._save(skin.skin_id, profile)
                    result[skin.skin_id] = profile
            done += 1
            if on_progress:
                on_progress(done, len(missing))

        await asyncio.gather(*(one(s) for s in missing))
        return result

    def _save(self, skin_id: str, profile: ColorProfile) -> None:
        with self._sessions.begin() as session:
            session.merge(
                SkinColorRow(
                    skin_id=skin_id,
                    coverage=profile.coverage,
                    chromatic=profile.chromatic,
                    computed_at=self._clock(),
                )
            )

    async def aclose(self) -> None:
        await self._http.aclose()
