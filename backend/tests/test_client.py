import httpx
import pytest
from nacl.signing import SigningKey

from app.dmarket.client import ALLOWED_GET_PATHS, DMarketClient, ForbiddenPathError, build_target

SEED = bytes(range(32))
SECRET_HEX = (SEED + SigningKey(SEED).verify_key.encode()).hex()
PUBLIC_HEX = SigningKey(SEED).verify_key.encode().hex()


def make_client(handler=None, **kwargs) -> DMarketClient:
    transport = httpx.MockTransport(handler or (lambda request: httpx.Response(200, json={"items": []})))
    return DMarketClient(PUBLIC_HEX, SECRET_HEX, transport=transport, **kwargs)


def test_signature_verifies_with_public_key():
    client = make_client()
    target = "/marketplace-api/v2/offers?gameId=a8db&limit=2"
    headers = client.sign_headers("GET", target, stamp=1700000000)
    signature = bytes.fromhex(headers["X-Request-Sign"].removeprefix("dmar ed25519 "))
    SigningKey(SEED).verify_key.verify(f"GET{target}1700000000".encode(), signature)
    assert headers["X-Api-Key"] == PUBLIC_HEX
    assert headers["X-Sign-Date"] == "1700000000"


def test_build_target_encodes_spaces_and_skips_none():
    target = build_target("/p", {"title": "AK-47 | Redline", "limit": 2, "cursor": None})
    assert target == "/p?title=AK-47%20%7C%20Redline&limit=2"


async def test_get_sends_signed_headers_and_returns_json():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["headers"] = request.headers
        return httpx.Response(200, json={"items": [], "total": 0})

    client = make_client(handler)
    data = await client.get("/marketplace-api/v2/offers", gameId="a8db", limit=1)
    assert data == {"items": [], "total": 0}
    assert seen["url"].endswith("/marketplace-api/v2/offers?gameId=a8db&limit=1")
    assert seen["headers"]["x-request-sign"].startswith("dmar ed25519 ")
    await client.aclose()


async def test_get_rejects_paths_outside_allowlist():
    client = make_client()
    with pytest.raises(ForbiddenPathError):
        await client.get("/exchange/v1/offers-buy")
    await client.aclose()


def test_client_has_no_write_methods():
    forbidden = {"post", "put", "patch", "delete", "buy", "sell", "request"}
    public = {name for name in dir(DMarketClient) if not name.startswith("_")}
    assert not public & forbidden
    assert all(path.startswith("/marketplace-api/v2/offers") for path in ALLOWED_GET_PATHS)
