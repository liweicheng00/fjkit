"""Background job routes: start, list, clear, detail, and the status endpoint the cards poll."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, UploadFile
from fjkit import render

from app.features.jobs.schemas import (
    KIND_OPTIONS,
    JobDetailResponse,
    JobResponse,
    JobsResponse,
    JobStart,
    UploadResponse,
)
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
    """Render the jobs page, or just the job list for an htmx request."""
    return _jobs(service)


@router.post("/jobs", name="jobs_start")
@render("jobs/_jobs.html")
def start_job(
    service: ServiceDep,
    background: BackgroundTasks,
    payload: JobStart,
) -> JobsResponse:
    """Create a job, schedule it to run after the response, and return the job list."""
    job = service.create(payload.kind)
    background.add_task(service.run, job.id)
    return _jobs(service)


@router.post("/jobs/upload", name="jobs_upload")
@render("jobs/_upload.html")
async def upload_file(file: UploadFile) -> UploadResponse:
    """Accept the uploaded file and report what arrived.

    `async def`, unlike every rendering handler in this demo: reading an
    `UploadFile` is awaited, and the threadpool rule in CLAUDE.md is about
    handlers whose work is rendering. This one's work is the read.

    Nothing is stored. The demo exists to show that the bytes arrived, which is
    exactly what a form missing `encoding="multipart"` gets wrong — that form
    posts the file's name as a string and this route would report 0 bytes.

    Declared before `/jobs/{job_id}`, like `jobs_clear`: a literal path segment
    loses to a path parameter declared ahead of it.
    """
    return UploadResponse(
        filename=file.filename or "unnamed",
        size=len(await file.read()),
        content_type=file.content_type or "unknown",
    )


@router.delete("/jobs/finished", name="jobs_clear")
@render("jobs/_jobs.html")
def clear_finished(service: ServiceDep) -> JobsResponse:
    """Remove finished jobs and return the job list. Declared before `/jobs/{job_id}`."""
    service.clear_finished()
    return _jobs(service)


@router.get("/jobs/{job_id}/detail", name="jobs_detail")
@render("jobs/_detail.html")
def job_detail(service: ServiceDep, job_id: int) -> JobDetailResponse:
    """Render the detail dialog's body for one job."""
    job = service.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return JobDetailResponse(job=job)


@router.get("/jobs/{job_id}", name="jobs_status")
@render("jobs/_job.html")
def job_status(service: ServiceDep, job_id: int) -> JobResponse:
    """Render one job's card. Polled by the card while the job is running."""
    job = service.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return JobResponse(job=job)
