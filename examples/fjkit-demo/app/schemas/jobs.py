"""Wire contracts for background jobs."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, computed_field


class JobState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class JobKind(StrEnum):
    EXPORT = "export"
    REINDEX = "reindex"
    SYNC = "sync"


class JobStart(BaseModel):
    """JSON body of the start form."""

    kind: JobKind = JobKind.EXPORT


class UploadResponse(BaseModel):
    """What arrived. The demo stores nothing — the point is proving the bytes
    reached the route, which a urlencoded form would not have managed."""

    filename: str
    size: int
    content_type: str

    @computed_field  # type: ignore[prop-decorator]
    @property
    def size_label(self) -> str:
        """Bytes as KB once there are enough of them to read."""
        return f"{self.size / 1024:,.1f} KB" if self.size >= 1024 else f"{self.size} bytes"


#: Job state -> badge variant.
STATE_VARIANT: dict[JobState, str] = {
    JobState.QUEUED: "outline",
    JobState.RUNNING: "info",
    JobState.DONE: "success",
    JobState.FAILED: "destructive",
}

#: Job kind -> (label, step count, fails on purpose).
KINDS: dict[JobKind, tuple[str, int, bool]] = {
    JobKind.EXPORT: ("Export the board to CSV", 12, False),
    JobKind.REINDEX: ("Rebuild the search index", 8, False),
    JobKind.SYNC: ("Sync with the upstream tracker", 6, True),
}

#: Options for the kind select.
KIND_OPTIONS: list[tuple[JobKind, str]] = [
    (JobKind.EXPORT, "Export CSV"),
    (JobKind.REINDEX, "Rebuild index"),
    (JobKind.SYNC, "Sync upstream (fails on purpose)"),
]

#: Job kind -> the sentence the "Job kinds" drawer shows. The select has room for
#: a label and nothing else, which is what the drawer is for.
KIND_NOTES: dict[JobKind, str] = {
    JobKind.EXPORT: "Walks the board once and writes a row per task. The longest of the three.",
    JobKind.REINDEX: "Re-reads every title and rebuilds the search index in place.",
    JobKind.SYNC: "Calls the upstream tracker, which refuses. It is wired to fail so the failed state is reachable.",
}


class Job(BaseModel):
    id: int
    kind: JobKind
    label: str
    state: JobState = JobState.QUEUED
    processed: int = 0
    total: int
    error: str | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def state_variant(self) -> str:
        return STATE_VARIANT[self.state]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def percent(self) -> int:
        return round(self.processed / self.total * 100) if self.total else 0

    @computed_field  # type: ignore[prop-decorator]
    @property
    def running(self) -> bool:
        """True while the job is queued or running. The card polls only while it is."""
        return self.state in (JobState.QUEUED, JobState.RUNNING)


class JobResponse(BaseModel):
    job: Job


class JobDetailResponse(BaseModel):
    """Context for the job detail dialog."""

    job: Job

    @computed_field  # type: ignore[prop-decorator]
    @property
    def facts(self) -> list[tuple[str, str]]:
        """Label/value pairs for `metric_group`."""
        return [
            ("Steps", f"{self.job.processed} / {self.job.total}"),
            ("Progress", f"{self.job.percent}%"),
            ("Job", f"#{self.job.id}"),
        ]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def timeline(self) -> list[str]:
        """Lines describing the job's progress so far."""
        lines = [
            "Queued after the response to the POST had been sent, never inside the request.",
            f"{self.job.processed} of {self.job.total} steps finished.",
        ]
        if self.job.error:
            lines.append(f"Stopped at step {self.job.processed + 1}: {self.job.error}.")
        elif self.job.state is JobState.DONE:
            lines.append("Finished. The card stopped polling on the response that said so.")
        else:
            lines.append("Still running — this is the state when you opened the dialog. Reopen it for a fresh one.")
        return lines


class KindGuide(BaseModel):
    """One row of the "Job kinds" drawer."""

    name: str
    note: str
    steps: int
    fails: bool


class JobsResponse(BaseModel):
    jobs: list[Job]
    kind_options: list[tuple[JobKind, str]]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def kind_guide(self) -> list[KindGuide]:
        """The drawer's rows, in the order the select offers them."""
        return [
            KindGuide(name=label, note=KIND_NOTES[kind], steps=KINDS[kind][1], fails=KINDS[kind][2])
            for kind, label in self.kind_options
        ]
