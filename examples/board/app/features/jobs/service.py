"""Business logic for background jobs.

No HTTP here either — `run()` is an ordinary function that happens to take a
while, which is the point: FastAPI's `BackgroundTasks` needs nothing from it
but a callable, and the router is what decides it should run after the
response rather than during it.

`run()` is deliberately a plain `def`. Starlette sends a sync background task
to the threadpool, so its sleeping never touches the event loop; written as
`async def` with a blocking `sleep` it would stall every other request in the
worker, and nothing would report the mistake.
"""

from __future__ import annotations

from itertools import count
from threading import Lock
from time import sleep

from app.features.jobs.schemas import KINDS, Job, JobKind, JobState


class JobService:
    def __init__(self, step_seconds: float = 0.4) -> None:
        # How long one step of the pretend work takes. A constructor argument
        # rather than a module constant so the tests can drive the same code
        # path with the waiting removed — the state machine under test is the
        # same one the demo runs.
        self.step_seconds = step_seconds
        self._lock = Lock()
        self._ids = count(1)
        self._jobs: dict[int, Job] = {}

    def list(self) -> list[Job]:
        """Newest first — a job you just started should not appear last."""
        return sorted(self._jobs.values(), key=lambda j: -j.id)

    def get(self, job_id: int) -> Job | None:
        return self._jobs.get(job_id)

    def create(self, kind: JobKind) -> Job:
        label, total, _ = KINDS[kind]
        with self._lock:
            job = Job(id=next(self._ids), kind=kind, label=label, total=total)
            self._jobs[job.id] = job
            return job

    def run(self, job_id: int) -> None:
        """Work through one job's steps, then mark it finished.

        Called after the response has been sent. Each step re-reads the job
        under the lock instead of holding the one it was handed, because
        `clear_finished` may have removed it in the meantime — a background
        task always outlives the request, so it can never assume its own row is
        still there.
        """
        for step in range(1, self._total(job_id) + 1):
            sleep(self.step_seconds)
            with self._lock:
                job = self._jobs.get(job_id)
                if job is None:
                    return
                if self._fails_at(job, step):
                    self._jobs[job_id] = job.model_copy(
                        update={"state": JobState.FAILED, "error": "upstream refused the connection"}
                    )
                    return
                self._jobs[job_id] = job.model_copy(update={"state": JobState.RUNNING, "processed": step})

        with self._lock:
            job = self._jobs.get(job_id)
            if job is not None:
                self._jobs[job_id] = job.model_copy(update={"state": JobState.DONE})

    def clear_finished(self) -> int:
        """Drop every job that has stopped moving. Running ones stay."""
        with self._lock:
            gone = [job_id for job_id, job in self._jobs.items() if not job.running]
            for job_id in gone:
                del self._jobs[job_id]
            return len(gone)

    def _total(self, job_id: int) -> int:
        job = self._jobs.get(job_id)
        return job.total if job else 0

    @staticmethod
    def _fails_at(job: Job, step: int) -> bool:
        """The one kind that fails does so partway through, not at step one —
        a job that dies before it moves never exercises the partial that has to
        show how far it got."""
        _, total, fails = KINDS[job.kind]
        return fails and step > total // 2
