import json
import time
from types import SimpleNamespace

import pytest
from envs import build_env
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from test_shortlist import FakeClient, answer

from app.ai.shortlist import Shortlister
from app.catalog.store import CatalogStore
from app.db.session import init_db
from app.main import create_app
from app.state import AppState

BLUE_CT = {"side": "ct", "colors": ["blue"]}


def make_state(shortlister=None, catalog=None) -> tuple[AppState, SimpleNamespace]:
    env = build_env()
    return AppState(catalog=catalog or env.catalog, finder=env.finder, shortlister=shortlister), env


def wait_done(client: TestClient, job_id: str, timeout: float = 10.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        body = client.get(f"/api/jobs/{job_id}").json()
        if body["status"] != "running":
            return body
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def start_job(client: TestClient, runner):
    """Start a job on the app's own event loop, as a request handler would."""
    async def start():
        return client.app.state.app_state.jobs.start(runner)

    return client.portal.call(start)


def search(client: TestClient, **body) -> dict:
    created = client.post("/api/modes/color-build/search", json={**BLUE_CT, **body})
    assert created.status_code == 202
    return wait_done(client, created.json()["job_id"])


@pytest.fixture
def client():
    state, _ = make_state()
    with TestClient(create_app(state)) as c:
        yield c


# ---- basics ------------------------------------------------------------------------------------

def test_health_reports_catalog_and_ai_flag(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok" and body["catalog_skins"] > 0 and body["ai_enabled"] is False


def test_health_ai_enabled_when_configured():
    state, _ = make_state(shortlister=Shortlister(FakeClient(answer())))
    with TestClient(create_app(state)) as c:
        assert c.get("/api/health").json()["ai_enabled"] is True


def test_slots_by_side(client):
    ct = {s["weapon"] for s in client.get("/api/catalog/slots", params={"side": "ct"}).json()}
    t = {s["weapon"] for s in client.get("/api/catalog/slots", params={"side": "t"}).json()}
    assert "M4A1-S" in ct and "M4A1-S" not in t and "AK-47" in t
    assert client.get("/api/catalog/slots", params={"side": "x"}).status_code == 422


def test_api_has_no_write_style_methods(client):
    methods = {m for route in client.app.routes for m in getattr(route, "methods", set())}
    assert methods <= {"GET", "POST", "HEAD", "OPTIONS"}


# ---- colour-build search -----------------------------------------------------------------------

def test_search_runs_as_a_job_and_returns_candidates(client):
    job = search(client)
    assert job["status"] == "done" and job["error"] is None
    skins = {c["skin"] for c in job["candidates"]}
    assert skins == {"AWP | Atheris", "M4A4 | Howl", "★ Karambit | Doppler"}
    assert job["stats"]["color_matched"] > 0 and job["stats"]["with_offers_in_budget"] == 3
    assert job["total"] > 0 and job["stage"] == "prices"  # progress of the last slow stage


def test_candidate_fields(client):
    atheris = next(c for c in search(client)["candidates"] if c["skin"] == "AWP | Atheris")
    assert atheris["price_cents"] == 300 and atheris["wear"] == "Battle-Scarred"
    assert atheris["weapon"] == "AWP" and atheris["image"].startswith("http")
    assert 0 < atheris["coverage"] <= 1 and 0 < atheris["dominance"] <= 1


def test_budget_and_wear_filters_reach_the_finder(client):
    job = search(client, budget_cents=10_000, wears=["Minimal Wear", "Factory New"])
    assert [(c["skin"], c["wear"]) for c in job["candidates"]] == [("AWP | Atheris", "Minimal Wear")]


@pytest.mark.parametrize(
    "body",
    [{"side": "ct", "colors": []}, {"side": "ct", "colors": ["magenta"]}, {"side": "bad", "colors": ["blue"]},
     {"side": "ct", "colors": ["blue"], "budget_cents": 0}, {"side": "ct", "colors": ["blue"], "limit": 0},
     {"colors": ["blue"]}],
)
def test_invalid_search_requests_are_rejected(client, body):
    assert client.post("/api/modes/color-build/search", json=body).status_code == 422


def test_colours_are_case_insensitive(client):
    assert search(client, colors=["Blue"])["status"] == "done"


def test_unknown_job_is_404(client):
    assert client.get("/api/jobs/nope").status_code == 404


def test_empty_catalog_gives_503():
    env = build_env()
    empty = CatalogStore(init_db(create_engine("sqlite://", poolclass=StaticPool,
                                               connect_args={"check_same_thread": False})))
    state = AppState(catalog=empty, finder=env.finder, shortlister=None)
    with TestClient(create_app(state)) as c:
        assert c.post("/api/modes/color-build/search", json=BLUE_CT).status_code == 503


def test_failed_job_reports_error(client):
    async def boom(_progress):
        raise RuntimeError("dmarket exploded")

    job = start_job(client, boom)
    body = wait_done(client, job.id)
    assert body["status"] == "failed" and "dmarket exploded" in body["error"] and body["candidates"] is None


# ---- shortlist ---------------------------------------------------------------------------------

def test_shortlist_without_api_key_is_503(client):
    job = search(client)
    response = client.post(f"/api/modes/color-build/jobs/{job['id']}/shortlist", json={"request": "blue"})
    assert response.status_code == 503 and "ANTHROPIC_API_KEY" in response.json()["detail"]


def test_shortlist_returns_ai_picks_from_the_job_candidates():
    ai = FakeClient(None)
    state, _ = make_state(shortlister=Shortlister(ai))
    with TestClient(create_app(state)) as c:
        job = search(c)
        names = [x["skin"] for x in job["candidates"]]
        # the model answers with ids of the 2nd and 1st candidate, plus an invented id
        ai._reply.content = [SimpleNamespace(type="text", text=answer(("c2", "краще"), ("c1", "теж"), ("c99", "x")))]
        response = c.post(f"/api/modes/color-build/jobs/{job['id']}/shortlist",
                          json={"request": "clean look", "max_picks": 5, "owned": ["AK-47 | Redline"]})
        assert response.status_code == 200
        body = response.json()
        assert [p["candidate"]["skin"] for p in body["picks"]] == [names[1], names[0]]
        assert body["picks"][0]["reason"] == "краще" and body["ignored"] == ["c99"]
        sent = json.dumps(ai.calls[0]["messages"], ensure_ascii=False)
        assert "clean look" in sent and "AK-47 | Redline" in sent


@pytest.mark.parametrize(("reply", "status"), [
    (FakeClient(None, stop_reason="refusal", stop_details=SimpleNamespace(category="cyber")), 422),
    (FakeClient("not json"), 502),
])
def test_shortlist_model_failures_map_to_http_errors(reply, status):
    state, _ = make_state(shortlister=Shortlister(reply))
    with TestClient(create_app(state)) as c:
        job = search(c)
        assert c.post(f"/api/modes/color-build/jobs/{job['id']}/shortlist",
                      json={"request": "blue"}).status_code == status


def test_shortlist_needs_a_finished_successful_job():
    state, _ = make_state(shortlister=Shortlister(FakeClient(answer())))
    with TestClient(create_app(state)) as c:
        async def boom(_progress):
            raise RuntimeError("x")

        failed = start_job(c, boom)
        wait_done(c, failed.id)
        assert c.post(f"/api/modes/color-build/jobs/{failed.id}/shortlist", json={"request": "r"}).status_code == 409
        assert c.post("/api/modes/color-build/jobs/missing/shortlist", json={"request": "r"}).status_code == 404
        assert c.post(f"/api/modes/color-build/jobs/{failed.id}/shortlist", json={"request": ""}).status_code == 422
