"""AI shortlist: Claude narrows a candidate list to the skins that best fit the player's request.

Safety by construction: the model only sees candidates we pass (short ids, facts, a picture) and can only
answer with those ids; anything else it returns is dropped. It has no tools, so it cannot act on the market.
"""
import json
import ssl
from dataclasses import dataclass, field
from typing import Any

import truststore
from anthropic import AsyncAnthropic, DefaultAsyncHttpxClient

from app.selection.candidates import Candidate

SYSTEM_PROMPT = """\
You help a Counter-Strike 2 player pick skins for a themed loadout.

You receive numbered candidates. Each has an id, key facts, and a picture of the skin. Choose the skins \
that best fit the player's request and look good together, and give each a short reason.

- Use only ids from the list. Never invent a skin or an id.
- Judge by what the picture shows, not only by the name. Mention price or float only when it is a real \
advantage.
- Prefer covering different weapons over several skins of one weapon, unless the player asks otherwise.
- Order picks from best to worst. Return fewer picks than the limit if few candidates really fit.
- Write the reasons in {language}, one short sentence each."""

RESULT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "picks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"id": {"type": "string"}, "reason": {"type": "string"}},
                "required": ["id", "reason"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["picks"],
    "additionalProperties": False,
}


class ShortlistError(Exception):
    """The model could not produce a usable shortlist."""


class ShortlistRefused(ShortlistError):
    def __init__(self, category: str | None) -> None:
        super().__init__(f"model declined the request (category: {category})")
        self.category = category


@dataclass(frozen=True)
class Pick:
    candidate: Candidate
    reason: str


@dataclass
class ShortlistResult:
    picks: list[Pick] = field(default_factory=list)
    ignored: list[str] = field(default_factory=list)  # ids the model returned that we did not offer
    input_tokens: int = 0
    output_tokens: int = 0


def make_anthropic_client(api_key: str | None = None) -> AsyncAnthropic:
    """Client that trusts the OS certificate store (certifi alone fails on some Windows setups)."""
    context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    return AsyncAnthropic(api_key=api_key, http_client=DefaultAsyncHttpxClient(verify=context))


def candidate_ids(candidates: list[Candidate]) -> dict[str, Candidate]:
    return {f"c{i}": c for i, c in enumerate(candidates, start=1)}


def describe(cid: str, c: Candidate) -> str:
    offer, skin = c.offer, c.skin
    facts = [
        f"[{cid}] {offer.title}",
        f"${offer.price_cents / 100:.2f}",
        f"float {offer.float_value:.3f}" if offer.float_value is not None else "no float",
    ]
    if skin.rarity:
        facts.append(skin.rarity)
    if skin.collections:
        facts.append(skin.collections[0])
    if offer.discount_percent:
        facts.append(f"{offer.discount_percent:g}% below suggested price")
    if offer.sticker_names:
        facts.append("stickers: " + ", ".join(offer.sticker_names[:4]))
    return " | ".join(facts)


class Shortlister:
    def __init__(self, client: AsyncAnthropic, model: str = "claude-opus-5-5", effort: str = "medium",
                 language: str = "Ukrainian") -> None:
        self._client, self._model, self._effort, self._language = client, model, effort, language

    def build_content(self, candidates: list[Candidate], request: str, max_picks: int,
                      owned: list[str] | None = None) -> list[dict[str, Any]]:
        header = [f"Player's request: {request}", f"Return at most {max_picks} picks."]
        if owned:
            header.append("Skins the player already owns (consider how new picks go with them):\n- "
                          + "\n- ".join(owned))
        header.append("Candidates:")
        content: list[dict[str, Any]] = [{"type": "text", "text": "\n".join(header)}]
        for cid, candidate in candidate_ids(candidates).items():
            content.append({"type": "text", "text": describe(cid, candidate)})
            if candidate.skin.image:
                content.append({"type": "image", "source": {"type": "url", "url": candidate.skin.image}})
        return content

    async def shortlist(self, candidates: list[Candidate], request: str, max_picks: int = 10,
                        owned: list[str] | None = None) -> ShortlistResult:
        if not candidates:
            return ShortlistResult()
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=16000,
            system=SYSTEM_PROMPT.format(language=self._language),
            messages=[{"role": "user", "content": self.build_content(candidates, request, max_picks, owned)}],
            output_config={"effort": self._effort, "format": {"type": "json_schema", "schema": RESULT_SCHEMA}},
        )
        if response.stop_reason == "refusal":
            details = getattr(response, "stop_details", None)
            raise ShortlistRefused(getattr(details, "category", None))
        if response.stop_reason == "max_tokens":
            raise ShortlistError("the answer was cut off (max_tokens)")
        text = next((b.text for b in response.content if b.type == "text"), None)
        if text is None:
            raise ShortlistError("the model returned no text")
        try:
            raw_picks = json.loads(text)["picks"]
        except (ValueError, KeyError, TypeError) as exc:
            raise ShortlistError(f"unreadable model output: {exc}") from exc

        by_id = candidate_ids(candidates)
        result = ShortlistResult(
            input_tokens=getattr(response.usage, "input_tokens", 0),
            output_tokens=getattr(response.usage, "output_tokens", 0),
        )
        seen: set[str] = set()
        for item in raw_picks:
            cid = item.get("id") if isinstance(item, dict) else None
            if cid not in by_id:
                result.ignored.append(str(cid))
            elif cid not in seen:
                seen.add(cid)
                result.picks.append(Pick(by_id[cid], str(item.get("reason", ""))))
        result.picks = result.picks[:max_picks]
        return result
