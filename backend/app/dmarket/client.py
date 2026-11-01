"""Read-only DMarket client.

Only GET is implemented, and only for allowlisted paths: the app must never buy, list or trade.
"""
import asyncio
import ssl
import time
import urllib.parse
from collections.abc import Mapping
from typing import Any

import httpx
import truststore
from nacl.signing import SigningKey

ALLOWED_GET_PATHS = frozenset({"/marketplace-api/v2/offers"})


class ForbiddenPathError(Exception):
    """Raised when a path outside the read-only allowlist is requested."""


def build_target(path: str, params: Mapping[str, Any]) -> str:
    """Path plus query string, exactly as it is both signed and sent."""
    query = urllib.parse.urlencode(
        {k: v for k, v in params.items() if v is not None},
        quote_via=urllib.parse.quote,
    )
    return f"{path}?{query}" if query else path


class DMarketClient:
    def __init__(
        self,
        public_key: str,
        secret_key_hex: str,
        base_url: str = "https://api.dmarket.com",
        max_rps: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._public_key = public_key
        # DMarket secret is 64 bytes (seed + public key); Ed25519 signing needs the 32-byte seed.
        self._signer = SigningKey(bytes.fromhex(secret_key_hex)[:32])
        # Use the OS trust store (certifi alone fails behind some Windows TLS setups).
        # Verification stays on. `verify` is ignored when a custom transport is given.
        ssl_context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        self._http = httpx.AsyncClient(
            base_url=base_url, transport=transport, timeout=20.0, verify=ssl_context
        )
        self._min_interval = 1.0 / max_rps
        self._lock = asyncio.Lock()
        self._last_request = 0.0

    def sign_headers(self, method: str, target: str, body: str = "", stamp: int | None = None) -> dict[str, str]:
        stamp_str = str(stamp if stamp is not None else int(time.time()))
        signature = self._signer.sign(f"{method}{target}{body}{stamp_str}".encode()).signature.hex()
        return {
            "X-Api-Key": self._public_key,
            "X-Sign-Date": stamp_str,
            "X-Request-Sign": f"dmar ed25519 {signature}",
        }

    async def _throttle(self) -> None:
        async with self._lock:
            wait = self._last_request + self._min_interval - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_request = time.monotonic()

    async def get(self, path: str, **params: Any) -> dict[str, Any]:
        if path not in ALLOWED_GET_PATHS:
            raise ForbiddenPathError(f"GET {path} is not in the read-only allowlist")
        target = build_target(path, params)
        await self._throttle()
        response = await self._http.get(target, headers=self.sign_headers("GET", target))
        response.raise_for_status()
        return response.json()

    async def aclose(self) -> None:
        await self._http.aclose()
