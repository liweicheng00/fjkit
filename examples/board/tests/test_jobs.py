"""Background work and the polling contract.

The demo sleeps between steps so a browser has something to watch. The state
machine does not care, so these tests set the step to zero and drive the same
code path — which means `TestClient` finishes the background task before the
POST call returns, and that turns out to be exactly the right microscope:
the response body is what the browser gets *before* the work starts, and the
service is what the next poll will see.
"""

from __future__ import annotations

import pytest
from app.features.jobs.schemas import JobKind, JobState


@pytest.fixture
def jobs(client):
    service = client.app.state.jobs
    service.step_seconds = 0
    return service


def test_the_reply_comes_back_before_the_work_starts(htmx, jobs):
    """The ordering the whole page is built on.

    `BackgroundTasks` runs after the response is sent, so the card in the reply
    shows a job that has not moved. That it is `Queued` here and `Done` a line
    later is the observable proof that the work did not happen inside the
    request — which is also what the polling is for.
    """
    response = htmx.post("/jobs", data={"kind": "export"})

    assert response.status_code == 200
    assert "Queued" in response.text
    assert "0 of 12 steps" in response.text

    # The same job, once TestClient has let the background task finish.
    assert jobs.get(1).state is JobState.DONE


def test_render_does_not_swallow_the_background_task(htmx, jobs):
    """`@render` builds the response itself rather than letting FastAPI build
    one, and FastAPI only attaches background tasks to a reply it constructs —
    or to a `Response` a handler returned. This asserts the second case still
    holds, because if it ever stopped, the POST would look completely healthy
    and no job would ever run."""
    htmx.post("/jobs", data={"kind": "export"})
    assert jobs.get(1).processed == 12


def test_a_running_job_asks_to_be_polled(htmx, jobs):
    """A job the service has not run yet stands in for one mid-flight."""
    job = jobs.create(JobKind.EXPORT)

    response = htmx.get(f"/jobs/{job.id}")

    assert response.status_code == 200
    assert f'id="job-{job.id}"' in response.text
    assert 'hx-trigger="load delay:1s"' in response.text
    assert 'hx-swap="outerHTML"' in response.text
    assert f"/jobs/{job.id}" in response.text
    # The spinner is the visible half of the same flag the trigger hangs off.
    assert "animate-spin" in response.text


def test_a_finished_job_stops_asking(htmx, jobs):
    """The whole stop condition: the last response carries no trigger, so there
    is no next request. Nothing cancels anything."""
    htmx.post("/jobs", data={"kind": "export"})

    response = htmx.get("/jobs/1")

    assert "Done" in response.text
    assert "hx-trigger" not in response.text
    # Named exactly: the card no longer asks for its own status. It still
    # carries the Details button's `hx-get`, which fires on a click and
    # therefore never asks again on its own.
    assert 'hx-get="/jobs/1"' not in response.text
    assert "12 of 12 steps" in response.text
    assert "animate-spin" not in response.text


def test_a_failing_job_stops_asking_too(htmx, jobs):
    """A job that dies has to end the polling as firmly as one that succeeds —
    otherwise the page hammers a handler whose answer will never change."""
    htmx.post("/jobs", data={"kind": "sync"})

    response = htmx.get("/jobs/1")

    assert jobs.get(1).state is JobState.FAILED
    assert "Failed" in response.text
    assert "upstream refused the connection" in response.text
    assert "hx-trigger" not in response.text


def test_the_partial_is_a_fragment_not_a_page(htmx, jobs):
    job = jobs.create(JobKind.REINDEX)
    response = htmx.get(f"/jobs/{job.id}")
    assert "<!doctype html>" not in response.text.lower()
    assert response.text.lstrip().startswith("<div")


def test_the_page_embeds_the_same_list_the_swaps_return(client, htmx, jobs):
    jobs.create(JobKind.EXPORT)

    page = client.get("/jobs").text
    swap = htmx.get("/jobs").text

    assert page.count('id="job-list"') == 1
    assert swap.count('id="job-list"') == 1
    assert "<!doctype html>" not in swap.lower()


def test_the_empty_list_says_so(client, jobs):
    assert "No jobs yet" in client.get("/jobs").text


def test_the_start_form_names_an_indicator_that_exists(client, jobs):
    """`hx-indicator` pointing at nothing fails silently — the request just has
    no loading state — so the id and the element are asserted together."""
    html = client.get("/jobs").text
    assert 'hx-indicator="#job-busy"' in html
    assert 'id="job-busy"' in html
    assert "htmx-indicator" in html


def test_starting_a_job_answers_with_the_container_the_form_targets(htmx, jobs):
    """The form swaps `#job-list` with `outerHTML`, so the reply has to *be* a
    `#job-list`. Answering with a bare card would replace the container with a
    card and leave the next start no target to swap into — a bug that looks
    like it works exactly once."""
    response = htmx.post("/jobs", data={"kind": "export"})
    assert 'id="job-list"' in response.text
    assert "No jobs yet" not in response.text


def test_starting_a_second_job_still_works(htmx, jobs):
    """The regression the assertion above exists to prevent, end to end."""
    htmx.post("/jobs", data={"kind": "export"})
    response = htmx.post("/jobs", data={"kind": "reindex"})

    assert 'id="job-1"' in response.text
    assert 'id="job-2"' in response.text
    assert response.text.index('id="job-2"') < response.text.index('id="job-1"'), "newest first"


def test_clearing_keeps_the_jobs_that_are_still_moving(htmx, jobs):
    htmx.post("/jobs", data={"kind": "export"})  # runs to completion
    running = jobs.create(JobKind.REINDEX)  # never started

    response = htmx.delete("/jobs/finished")

    assert response.status_code == 200
    assert jobs.get(1) is None
    assert jobs.get(running.id) is not None
    assert response.text.lstrip().startswith("<div")
    assert 'id="job-list"' in response.text


def test_clearing_nothing_is_harmless(htmx, jobs):
    assert htmx.delete("/jobs/finished").status_code == 200


def test_a_job_cleared_mid_flight_does_not_crash_its_own_background_task(client, jobs):
    """A background task always outlives the request that started it, so it can
    never assume its row is still there."""
    job = jobs.create(JobKind.EXPORT)
    jobs._jobs.pop(job.id)
    jobs.run(job.id)  # must simply return


def test_unknown_job_is_a_404(htmx, jobs):
    assert htmx.get("/jobs/999").status_code == 404


def test_every_details_button_points_at_a_dialog_that_exists(client, jobs):
    """`popovertarget` naming nothing fails silently — the click just does
    nothing at all — so the id and the element are asserted together, the same
    way `hx-indicator` is."""
    jobs.create(JobKind.EXPORT)
    html = client.get("/jobs").text

    assert 'popovertarget="job-detail-1"' in html
    assert 'id="job-detail-1"' in html
    assert "popover" in html


def test_the_details_button_targets_the_body_the_dialog_published(client, jobs):
    """The seam between the shell and its contents: the button fetches into the
    id `dialog` puts on its body. If either side renames it, the panel opens on
    a spinner that never resolves."""
    jobs.create(JobKind.EXPORT)
    html = client.get("/jobs").text

    assert 'hx-get="/jobs/1/detail"' in html
    assert 'hx-target="#job-detail-1-body"' in html
    assert 'id="job-detail-1-body"' in html


def test_the_details_button_names_its_own_swap(htmx, jobs):
    """htmx inherits `hx-swap` from ancestors, and this button's ancestor is a
    card that carries `outerHTML` for its own poll. Inherited, the first open of
    a running job's dialog replaces the body element instead of its contents —
    the id goes with it, and every open after that fills nothing. The failure is
    silent in the browser: the panel opens, and simply never updates again."""
    job = jobs.create(JobKind.EXPORT)

    card = htmx.get(f"/jobs/{job.id}").text

    assert 'hx-swap="outerHTML"' in card, "the card still polls itself that way"
    assert 'hx-swap="innerHTML"' in card, "and the trigger inside it must say otherwise"


def test_the_dialog_is_not_inside_the_card_that_replaces_itself(htmx, jobs):
    """The reason the dialogs are a second loop rather than part of `job_card`.
    A poll swaps `#job-{id}` wholesale; a dialog rendered in there would be torn
    out of the DOM about a second after the user opened it."""
    job = jobs.create(JobKind.EXPORT)

    poll = htmx.get(f"/jobs/{job.id}").text

    # The trigger travels with the card; the panel it opens must not.
    assert 'popovertarget="job-detail-1"' in poll
    assert 'class="dialog"' not in poll
    assert 'id="job-detail-1"' not in poll


def test_the_detail_is_fetched_only_when_the_dialog_opens(client, jobs):
    """The shell renders with the list; the contents cost a request per open.
    A list that already carried every detail would make the dialog free and the
    list expensive, which is the wrong way round for a panel most rows never
    show."""
    jobs.create(JobKind.EXPORT)
    listing = client.get("/jobs").text

    assert "Loading the job detail" in listing
    assert "0 of 12 steps finished" not in listing


def test_the_detail_partial_is_a_fragment(htmx, jobs):
    job = jobs.create(JobKind.REINDEX)

    response = htmx.get(f"/jobs/{job.id}/detail")

    assert response.status_code == 200
    assert "<!doctype html>" not in response.text.lower()
    assert "Rebuild the search index" not in response.text, "the title belongs to the shell, not the body"
    assert "0 / 8" in response.text
    assert "0 of 8 steps finished" in response.text


def test_a_failed_job_says_where_it_stopped(htmx, jobs):
    htmx.post("/jobs", data={"kind": "sync"})

    detail = htmx.get("/jobs/1/detail").text

    assert "Failed" in detail
    assert "Stopped at step 4: upstream refused the connection" in detail


def test_the_detail_of_a_job_that_is_gone_is_a_404(htmx, jobs):
    """A dialog opened for a row that was cleared in the meantime. htmx leaves
    the panel alone on an error response, so the user keeps the last body they
    saw instead of an empty box."""
    assert htmx.get("/jobs/999/detail").status_code == 404


def test_the_literal_path_wins_over_the_id_route(htmx, jobs):
    """`/jobs/finished` is declared above `/jobs/{job_id}`; if that ever flips,
    the clear button starts asking for a job called "finished"."""
    assert htmx.delete("/jobs/finished").status_code == 200
