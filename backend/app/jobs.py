"""Tiny in-process background jobs with progress, for searches that can take a minute on a cold cache."""
import asyncio
import logging
import uuid
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal

log = logging.getLogger(__name__)

Status = Literal["running", "done", "failed"]
ProgressFn = Callable[[str, int, int], None]


@dataclass
class Job:
    id: str
    status: Status = "running"
    stage: str = ""
    done: int = 0
    total: int = 0
    result: Any = None
    error: str | None = None


class JobRegistry:
    def __init__(self, keep: int = 50) -> None:
        self._jobs: OrderedDict[str, Job] = OrderedDict()
        self._tasks: set[asyncio.Task] = set()  # strong refs: the loop only keeps weak ones
        self._keep = keep

    def start(self, runner: Callable[[ProgressFn], Awaitable[Any]]) -> Job:
        job = Job(id=uuid.uuid4().hex[:12])
        self._jobs[job.id] = job
        while len(self._jobs) > self._keep:
            self._jobs.popitem(last=False)

        def progress(stage: str, done: int, total: int) -> None:
            job.stage, job.done, job.total = stage, done, total

        async def run() -> None:
            try:
                job.result = await runner(progress)
                job.status = "done"
            except Exception as exc:
                log.exception("job %s failed", job.id)
                job.error, job.status = f"{type(exc).__name__}: {exc}", "failed"

        task = asyncio.get_running_loop().create_task(run())
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return job

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)
