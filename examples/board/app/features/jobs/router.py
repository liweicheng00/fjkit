"""HTTP surface for background jobs — the polling half of the demo.

Three ideas, one page:

1. **The work happens after the response.** `BackgroundTasks.add_task` hands
   `JobService.run` to Starlette, which calls it once the reply is on the wire.
   The POST therefore answers in microseconds with a job that has not started,
   which is the honest thing to show the user.
2. **The page finds out by asking.** No websocket, no SSE, no client state: the
   job partial carries its own `hx-get` and re-requests itself.
3. **The polling stops because the last response stopped asking.** A finished
   job renders without the trigger. Nothing has to remember to cancel anything,
   and a browser that reloads mid-job simply resumes from whatever the server
   says now.

`hx-trigger="every 2s"` is the other spelling and it never stops on its own —
the server has to answer 286, or something has to remove the element. Both cost
one request per interval per open tab, so the status handler stays a dict
lookup.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Request
from fjkit import render

from app.features.jobs.schemas import KIND_OPTIONS, JobDetailResponse, JobKind, JobResponse, JobsResponse
from app.features.jobs.service import JobService

router = APIRouter(tags=["jobs"])


def get_service(request: Request) -> JobService:
    return request.app.state.jobs


ServiceDep = Annotated[JobService, Depends(get_service)]


def _jobs(service: JobService) -> JobsResponse:
    return JobsResponse(jobs=service.list(), kind_options=KIND_OPTIONS)


@router.get("/jobs", name="jobs_page")
@render("jobs/page.html", partial="jobs/_jobs.html")
def jobs_page(service: ServiceDep) -> JobsResponse:
    """The full page — and, for an htmx swap, just the list inside it."""
    return _jobs(service)


@router.post("/jobs", name="jobs_start")
@render("jobs/_jobs.html")
def start_job(
    service: ServiceDep,
    background: BackgroundTasks,
    kind: Annotated[JobKind, Form()] = JobKind.EXPORT,
) -> JobsResponse:
    """Queue a job and answer immediately with the list it joined.

    `@render` builds the response itself, and FastAPI attaches the background
    tasks to a response a handler returned — so the ordering still holds:
    reply first, work afterwards. The new card comes back already carrying the
    `hx-get` that will fetch its own next state, so nothing else on the page had
    to be told a job now exists.

    The whole list rather than the one new card, because the form targets
    `#job-list` and that id belongs to the container. Answering with a bare
    card would replace the container with a card, and the *second* start would
    then have no target left to swap into — the kind of bug that looks like it
    works exactly once.
    """
    job = service.create(kind)
    background.add_task(service.run, job.id)
    return _jobs(service)


@router.delete("/jobs/finished", name="jobs_clear")
@render("jobs/_jobs.html")
def clear_finished(service: ServiceDep) -> JobsResponse:
    """Declared above the `{job_id}` route so the literal path wins the match.

    Returns the whole list rather than removing rows one at a time — the same
    reason the task board re-renders wholesale after a mutation: there is then
    no client-side state question to answer.
    """
    service.clear_finished()
    return _jobs(service)


@router.get("/jobs/{job_id}/detail", name="jobs_detail")
@render("jobs/_detail.html")
def job_detail(service: ServiceDep, job_id: int) -> JobDetailResponse:
    """The dialog's body, fetched when the dialog opens.

    A second representation of the same job, and the reason it is a route at
    all: the list renders one empty dialog shell per card, and the contents —
    which nobody may ever look at — cost a request only when one is opened.
    """
    job = service.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return JobDetailResponse(job=job)


@router.get("/jobs/{job_id}", name="jobs_status")
@render("jobs/_job.html")
def job_status(service: ServiceDep, job_id: int) -> JobResponse:
    """What the poll hits. One dict lookup and one small partial.

    A 404 here is not a failure case to design around: htmx leaves the element
    alone on an error response, so a job cleared mid-poll stops updating rather
    than blanking out.
    """
    job = service.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return JobResponse(job=job)
