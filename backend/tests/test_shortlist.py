import json
from types import SimpleNamespace

import pytest
from fakes import raw_offer

from app.ai.shortlist import (
    RESULT_SCHEMA,
    Shortlister,
    ShortlistError,
    ShortlistRefused,
    candidate_ids,
    describe,
    make_anthropic_client,
)
from app.catalog.schemas import Skin
from app.dmarket.schemas import Offer
from app.selection.candidates import Candidate


def make_candidate(name: str, price: int = 1000, image: str = "https://img/x.png", weapon: str = "AWP") -> Candidate:
    skin = Skin(skin_id=name, name=name, weapon=weapon, category="Rifles", team="both", image=image,
                rarity="Classified", collections=["The Test Collection"])
    offer = Offer.from_api(raw_offer(f"{name} (Field-Tested)", price, float_value=0.21))
    return Candidate(skin, offer, coverage=0.5, dominance=0.9)


CANDIDATES = [make_candidate("AWP | Atheris", 624), make_candidate("USP-S | Blueprint", 417, weapon="USP-S"),
              make_candidate("MP9 | Hydra", 15, image="")]


class FakeClient:
    """Records the request and replies with a scripted response."""

    def __init__(self, text=None, stop_reason="end_turn", stop_details=None):
        self.calls: list[dict] = []
        self._reply = SimpleNamespace(
            content=[SimpleNamespace(type="text", text=text)] if text is not None else [],
            stop_reason=stop_reason, stop_details=stop_details,
            usage=SimpleNamespace(input_tokens=1200, output_tokens=80),
        )
        self.messages = SimpleNamespace(create=self._create)

    async def _create(self, **kwargs):
        self.calls.append(kwargs)
        return self._reply


def answer(*picks):
    return json.dumps({"picks": [{"id": i, "reason": r} for i, r in picks]})


async def run(client, **kwargs):
    return await Shortlister(client).shortlist(CANDIDATES, "blue loadout", **kwargs)


# ---- request construction ---------------------------------------------------------------------

async def test_request_has_ids_facts_images_and_schema():
    client = FakeClient(answer(("c1", "good")))
    await run(client, max_picks=5, owned=["AK-47 | Redline (Field-Tested)"])
    call = client.calls[0]
    assert call["model"] == "claude-opus-5-5" and call["max_tokens"] == 16000
    assert call["output_config"]["format"] == {"type": "json_schema", "schema": RESULT_SCHEMA}
    assert call["output_config"]["effort"] == "medium"
    assert "Ukrainian" in call["system"]
    content = call["messages"][0]["content"]
    header = content[0]["text"]
    assert "blue loadout" in header and "at most 5" in header and "AK-47 | Redline" in header
    texts = [b["text"] for b in content if b["type"] == "text"]
    assert any(t.startswith("[c1] AWP | Atheris (Field-Tested)") and "$6.24" in t for t in texts)
    images = [b["source"]["url"] for b in content if b["type"] == "image"]
    assert images == ["https://img/x.png", "https://img/x.png"]  # c3 has no image: no image block


async def test_image_follows_its_candidate_text():
    client = FakeClient(answer())
    await run(client)
    content = client.calls[0]["messages"][0]["content"]
    assert content[1]["text"].startswith("[c1]") and content[2]["type"] == "image"
    assert content[3]["text"].startswith("[c2]")


def test_describe_includes_float_collection_and_discount():
    candidate = make_candidate("AWP | Atheris")
    text = describe("c7", candidate)
    assert text.startswith("[c7] AWP | Atheris (Field-Tested)") and "float 0.210" in text
    assert "The Test Collection" in text and "Classified" in text


def test_ids_are_short_and_stable():
    assert list(candidate_ids(CANDIDATES)) == ["c1", "c2", "c3"]


# ---- result handling ---------------------------------------------------------------------------

async def test_picks_map_back_to_candidates_in_model_order():
    result = await run(FakeClient(answer(("c2", "бо синій"), ("c1", "дешево"))))
    assert [p.candidate.skin.name for p in result.picks] == ["USP-S | Blueprint", "AWP | Atheris"]
    assert result.picks[0].reason == "бо синій"
    assert (result.input_tokens, result.output_tokens) == (1200, 80)


async def test_unknown_and_duplicate_ids_are_dropped():
    result = await run(FakeClient(answer(("c9", "invented"), ("c1", "ok"), ("c1", "again"), ("zzz", "x"))))
    assert [p.candidate.skin.name for p in result.picks] == ["AWP | Atheris"]
    assert result.ignored == ["c9", "zzz"]


async def test_max_picks_is_enforced_even_if_model_ignores_it():
    result = await run(FakeClient(answer(("c1", "a"), ("c2", "b"), ("c3", "c"))), max_picks=2)
    assert [p.candidate.skin.name for p in result.picks] == ["AWP | Atheris", "USP-S | Blueprint"]


async def test_no_candidates_means_no_call():
    client = FakeClient(answer())
    result = await Shortlister(client).shortlist([], "anything")
    assert result.picks == [] and client.calls == []


# ---- failures ----------------------------------------------------------------------------------

async def test_refusal_is_raised_with_category():
    client = FakeClient(None, stop_reason="refusal", stop_details=SimpleNamespace(category="cyber"))
    with pytest.raises(ShortlistRefused) as info:
        await run(client)
    assert info.value.category == "cyber"


@pytest.mark.parametrize(
    "client",
    [FakeClient(answer(("c1", "x")), stop_reason="max_tokens"), FakeClient(None), FakeClient("not json"),
     FakeClient(json.dumps({"other": []}))],
)
async def test_unusable_answers_raise_shortlist_error(client):
    with pytest.raises(ShortlistError):
        await run(client)


async def test_malformed_pick_entries_do_not_crash():
    result = await run(FakeClient(json.dumps({"picks": ["c1", {"reason": "no id"}, {"id": "c2", "reason": "ok"}]})))
    assert [p.candidate.skin.name for p in result.picks] == ["USP-S | Blueprint"]


def test_client_factory_builds_without_network():
    client = make_anthropic_client("sk-ant-dummy")
    assert hasattr(client.messages, "create")
