"""One-off read-only probe: what does DMarket's marketplace v2 offers endpoint return for CS2?

Only issues signed GET requests. Never prints keys. No writes to the market.
Run with the project venv: .venv\\Scripts\\python.exe scripts\\probe_market.py [title]
"""
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from nacl.signing import SigningKey

BASE = "https://api.dmarket.com"
CS2 = "a8db"


def load_env(path: Path) -> dict[str, str]:
    env = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


ENV = load_env(Path(__file__).resolve().parent.parent / ".env")
PUBLIC = ENV["DMARKET_PUBLIC_KEY"]
SIGNER = SigningKey(bytes.fromhex(ENV["DMARKET_SECRET_KEY"])[:32])


def get(path: str, **params):
    query = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
    target = f"{path}?{query}" if query else path
    stamp = str(int(time.time()))
    sig = SIGNER.sign(f"GET{target}{stamp}".encode()).signature.hex()
    req = urllib.request.Request(
        BASE + target,
        headers={
            "X-Api-Key": PUBLIC,
            "X-Sign-Date": stamp,
            "X-Request-Sign": f"dmar ed25519 {sig}",
            "User-Agent": "dmarket-watcher-probe/0.1",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, json.load(resp)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")[:800]


def main():
    title = sys.argv[1] if len(sys.argv) > 1 else "AK-47 | Redline (Field-Tested)"
    status, data = get("/marketplace-api/v2/offers", gameId=CS2, title=title, limit=3)
    print("status:", status)
    if isinstance(data, dict):
        print("top-level keys:", list(data))
        for key, val in data.items():
            if isinstance(val, list) and val:
                print(f"{key}: {len(val)} items; first:")
                print(json.dumps(val[0], indent=2, ensure_ascii=False)[:3500])
    else:
        print(data)


if __name__ == "__main__":
    main()
