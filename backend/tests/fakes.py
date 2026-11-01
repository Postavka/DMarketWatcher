"""Test doubles shared by cache and hydrator tests."""
import json
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx

RAW = json.loads((Path(__file__).parent / "fixtures" / "offers.json").read_text(encoding="utf-8"))


def raw_offer(title: str, price_cents: int, float_value: float = 0.1, seed: int = 1) -> dict:
    """A minimal v2-shaped offer for `title`, derived fields (exterior) taken from the title."""
    wears = {"Factory New": "FACTORY_NEW", "Minimal Wear": "MINIMAL_WEAR", "Field-Tested": "FIELD_TESTED",
             "Well-Worn": "WELL_WORN", "Battle-Scarred": "BATTLE_SCARRED"}
    exterior = next((f"EXTERIOR_{v}" for k, v in wears.items() if f"({k})" in title), "EXTERIOR_UNSPECIFIED")
    return {
        "offerId": f"{title}|{price_cents}",
        "priceCents": str(price_cents),
        "discountPercent": 0,
        "createdAt": "2026-11-01T10:00:00Z",
        "attributes": {
            "title": title,
            "cs2": {"exterior": exterior, "float": str(float_value), "paintSeed": seed, "colors": [], "stickers": []},
        },
    }


class FakeDMarket:
    """Serves fixture offers filtered by title/price, paginated by cursor; counts requests.

    `page_size` forces a page size; None honours the request's `limit`.
    Titles in `fail_titles` answer 500.
    """

    def __init__(self, items=RAW, page_size: int | None = 2, fail_titles=(), contains=False):
        self.items, self.page_size, self.fail_titles = list(items), page_size, set(fail_titles)
        self.contains = contains  # real DMarket: `title` is a substring search
        self.requests = 0
        self.queried_titles: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests += 1
        q = {k: v[0] for k, v in parse_qs(urlparse(str(request.url)).query).items()}
        self.queried_titles.append(q.get("title", ""))
        if q.get("title") in self.fail_titles:
            return httpx.Response(500, json={"Code": "Internal"})
        def title_ok(item_title: str) -> bool:
            if "title" not in q:
                return True
            return q["title"] in item_title if self.contains else item_title == q["title"]

        rows = [r for r in self.items if title_ok(r["attributes"]["title"])]
        if q.get("treeFilters") == "category[]=normal":
            rows = [r for r in rows if not r["attributes"]["title"].startswith(("StatTrak", "Souvenir"))]
        if "priceTo" in q:
            rows = [r for r in rows if int(r["priceCents"]) <= int(q["priceTo"])]
        if q.get("orderBy") == "price":
            rows.sort(key=lambda r: int(r["priceCents"]), reverse=q.get("orderDir") == "desc")
        size = self.page_size or int(q.get("limit", 100))
        start = int(q.get("cursor") or 0)
        more = start + size < len(rows)
        return httpx.Response(
            200,
            json={"items": rows[start : start + size], "total": len(rows),
                  "cursor": str(start + size) if more else ""},
        )


class Clock:
    def __init__(self):
        self.now = datetime(2026, 11, 1, 12, 0)

    def __call__(self):
        return self.now
