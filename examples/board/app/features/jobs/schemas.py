"""Wire contracts for background jobs.

A job is the one thing on the board that outlives the request that started it,
so its model has to answer a question no task model needs: *is this still
moving?* `running` is a field on the model rather than a test the template
performs, because the polling contract hangs off it — the partial carries its
own `hx-trigger` only while `running` is true, and that decision belongs in the
same place as the state machine that flips it.
"""

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


#: Domain value -> Basecoat badge variant, in Python for the same reason
#: `STATUS_VARIANT` is: a template prints the variant it was handed, and never
#: grows an if/elif chain over domain values.
STATE_VARIANT: dict[JobState, str] = {
    JobState.QUEUED: "outline",
    JobState.RUNNING: "info",
    JobState.DONE: "success",
    JobState.FAILED: "destructive",
}

#: What each kind is called, how many steps it takes, and whether it is the one
#: that fails on purpose. The demo needs a failing job: a background task that
#: can only succeed teaches the wrong lesson about background tasks.
KINDS: dict[JobKind, tuple[str, int, bool]] = {
    JobKind.EXPORT: ("Export the board to CSV", 12, False),
    JobKind.REINDEX: ("Rebuild the search index", 8, False),
    JobKind.SYNC: ("Sync with the upstream tracker", 6, True),
}

#: The select's options, built here rather than comprehended in Jinja. The
#: failing kind says so in its label — a demo that looks broken is a bug.
KIND_OPTIONS: list[tuple[JobKind, str]] = [
    (JobKind.EXPORT, "Export CSV"),
    (JobKind.REINDEX, "Rebuild index"),
    (JobKind.SYNC, "Sync upstream (fails on purpose)"),
]


class Job(BaseModel):
    id: int
    kind: JobKind
    label: str
    state: JobState = JobState.QUEUED
    processed: int = 0
    total: int
    error: str | None = None

    # Computed, not a plain property, so the mapping and the arithmetic reach
    # the JSON representation too instead of existing only in Jinja.
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
        """Whether the browser should ask again.

        The whole polling contract is this one boolean: while it is true the
        partial renders its own `hx-trigger`, and the render that returns false
        simply does not — so the polling stops because the last response
        stopped asking for another.
        """
        return self.state in (JobState.QUEUED, JobState.RUNNING)


class JobResponse(BaseModel):
    job: Job


class JobDetailResponse(BaseModel):
    """What the detail dialog is handed.

    The two display lists are computed here rather than assembled in Jinja, for
    the reason every option list in this app is: a template prints what it is
    given. They live on the detail response instead of on `Job` because they
    are the detail view's answer — putting them on the model would ship three
    sentences of prose with every row of every list that mentions a job.
    """

    job: Job

    @computed_field  # type: ignore[prop-decorator]
    @property
    def facts(self) -> list[tuple[str, str]]:
        """The label/value pairs `metric_group` renders."""
        return [
            ("Steps", f"{self.job.processed} / {self.job.total}"),
            ("Progress", f"{self.job.percent}%"),
            ("Job", f"#{self.job.id}"),
        ]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def timeline(self) -> list[str]:
        """What happened, in the order it happened."""
        lines = [
            "Queued after the response to the POST had been sent, never inside the request.",
            f"{self.job.processed} of {self.job.total} steps finished.",
        ]
        if self.job.error:
            lines.append(f"Stopped at step {self.job.processed + 1}: {self.job.error}.")
        elif self.job.state is JobState.DONE:
            lines.append("Finished. The card stopped polling on the response that said so.")
        else:
            # The dialog is filled when it opens, so a running job's numbers are
            # a snapshot. Saying so beats a panel that silently goes stale next
            # to a card that is still moving.
            lines.append("Still running — this is the state when you opened the dialog. Reopen it for a fresh one.")
        return lines


class JobsResponse(BaseModel):
    jobs: list[Job]
    kind_options: list[tuple[JobKind, str]]
