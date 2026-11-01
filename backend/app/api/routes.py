from fastapi import APIRouter, HTTPException, Request

from app.ai.shortlist import ShortlistError, ShortlistRefused
from app.api.schemas import (
    CandidateOut,
    ColorBuildRequest,
    HealthOut,
    JobCreated,
    JobOut,
    PickOut,
    SelectionStatsOut,
    ShortlistOut,
    ShortlistRequest,
    SlotOut,
)
from app.catalog.schemas import Side
from app.jobs import Job
from app.selection.candidates import CandidateResult
from app.state import AppState

router = APIRouter(prefix="/api")


def state_of(request: Request) -> AppState:
    return request.app.state.app_state


def job_out(job: Job) -> JobOut:
    out = JobOut(id=job.id, status=job.status, stage=job.stage, done=job.done, total=job.total, error=job.error)
    if job.status == "done" and isinstance(job.result, CandidateResult):
        out.candidates = [CandidateOut.of(c) for c in job.result.candidates]
        out.stats = SelectionStatsOut.of(job.result.stats)
    return out


@router.get("/health", response_model=HealthOut)
def health(request: Request) -> HealthOut:
    state = state_of(request)
    return HealthOut(status="ok", catalog_skins=state.catalog.count(), ai_enabled=state.shortlister is not None)


@router.get("/catalog/slots", response_model=list[SlotOut])
def slots(request: Request, side: Side) -> list[SlotOut]:
    return [SlotOut(category=s.category, weapon=s.weapon, skins=s.skins) for s in state_of(request).catalog.slots(side)]


@router.post("/modes/color-build/search", response_model=JobCreated, status_code=202)
async def start_color_build(body: ColorBuildRequest, request: Request) -> JobCreated:
    state = state_of(request)
    if not state.catalog.count():
        raise HTTPException(503, "skin catalog is not loaded yet; run scripts/load_catalog.py")
    query = body.to_query()

    async def run(progress):
        return await state.finder.find(query, on_progress=progress)

    return JobCreated(job_id=state.jobs.start(run).id)


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: str, request: Request) -> JobOut:
    job = state_of(request).jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "unknown job")
    return job_out(job)


@router.post("/modes/color-build/jobs/{job_id}/shortlist", response_model=ShortlistOut)
async def shortlist(job_id: str, body: ShortlistRequest, request: Request) -> ShortlistOut:
    state = state_of(request)
    job = state.jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "unknown job")
    if job.status != "done" or not isinstance(job.result, CandidateResult):
        raise HTTPException(409, "the search has not finished successfully")
    if state.shortlister is None:
        raise HTTPException(503, "AI is not configured: set ANTHROPIC_API_KEY in .env")
    try:
        result = await state.shortlister.shortlist(
            job.result.candidates, body.request, body.max_picks, body.owned or None
        )
    except ShortlistRefused as exc:
        raise HTTPException(422, f"the model declined this request ({exc.category})") from exc
    except ShortlistError as exc:
        raise HTTPException(502, str(exc)) from exc
    return ShortlistOut(
        picks=[PickOut(candidate=CandidateOut.of(p.candidate), reason=p.reason) for p in result.picks],
        ignored=result.ignored,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
    )
