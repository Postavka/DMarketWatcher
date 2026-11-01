import asyncio

from app.jobs import JobRegistry


async def finish(registry: JobRegistry, job_id: str) -> None:
    for _ in range(200):
        if registry.get(job_id).status != "running":
            return
        await asyncio.sleep(0.005)
    raise AssertionError("job did not finish")


async def test_job_completes_with_result_and_progress():
    registry = JobRegistry()

    async def work(progress):
        progress("colors", 1, 3)
        await asyncio.sleep(0)
        progress("prices", 3, 3)
        return {"ok": True}

    job = registry.start(work)
    assert job.status == "running"
    await finish(registry, job.id)
    assert (job.status, job.result, job.stage, job.done, job.total) == ("done", {"ok": True}, "prices", 3, 3)


async def test_job_failure_is_captured_not_raised():
    registry = JobRegistry()

    async def work(_progress):
        raise ValueError("bad input")

    job = registry.start(work)
    await finish(registry, job.id)
    assert job.status == "failed" and job.error == "ValueError: bad input" and job.result is None


async def test_old_jobs_are_evicted():
    registry = JobRegistry(keep=2)

    async def work(_progress):
        return 1

    first = registry.start(work)
    second, third = registry.start(work), registry.start(work)
    assert registry.get(first.id) is None
    assert registry.get(second.id) is second and registry.get(third.id) is third
    await finish(registry, third.id)


async def test_unknown_job_is_none():
    assert JobRegistry().get("nope") is None
