"""In-memory store and runner for background jobs. `run()` is sync so Starlette runs it in the threadpool."""

from __future__ import annotations

from itertools import count
from threading import Lock
from time import sleep

from app.features.jobs.schemas import KINDS, Job, JobKind, JobState


class JobService:
    def __init__(self, step_seconds: float = 0.4) -> None:
        # Seconds per step; tests pass 0.
        self.step_seconds = step_seconds
        self._lock = Lock()
        self._ids = count(1)
        self._jobs: dict[int, Job] = {}

    def list(self) -> list[Job]:
        """All jobs, newest first."""
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
        """Advance the job one step at a time until done, failed, or removed."""
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
        """Remove every job that is not running. Returns how many were removed."""
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
        """Whether a failing kind fails at this step (past the halfway point)."""
        _, total, fails = KINDS[job.kind]
        return fails and step > total // 2
