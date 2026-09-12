"""What a handler asks for with `Depends`, declared once.

The three stores are read off `app.state`, where `lifespan` put them. The stack
guide says a service instance is built by its caller and passed as an argument,
and this is the exception the shape of a web app forces: the rows are the demo's
data, so a store has to outlive the request that reads it, and `app.state` is
where FastAPI keeps a process-lifetime object. The isolation the rule protects is
still there — `create_app()` builds fresh stores, and the test suite calls it per
test.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from fjkit.auth import Session

from app.services.jobs import JobService
from app.services.records import RecordService
from app.services.tasks import TaskService


def get_tasks(request: Request) -> TaskService:
    return request.app.state.tasks


def get_jobs(request: Request) -> JobService:
    return request.app.state.jobs


def get_records(request: Request) -> RecordService:
    return request.app.state.records


async def require_session(request: Request) -> Session:
    """Require a session via the app's auth plugin. Answers 401 when there is none."""
    return await request.app.state.auth.required(request)


TaskServiceDep = Annotated[TaskService, Depends(get_tasks)]
JobServiceDep = Annotated[JobService, Depends(get_jobs)]
RecordServiceDep = Annotated[RecordService, Depends(get_records)]
SessionDep = Annotated[Session, Depends(require_session)]
