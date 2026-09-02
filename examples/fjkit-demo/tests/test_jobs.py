"""Tests for the background jobs routes and polling contract."""

from __future__ import annotations

import pytest
from app.features.jobs.schemas import KIND_OPTIONS, JobKind, JobState


@pytest.fixture
def jobs(client):
    """The app's job service with the per-step sleep set to zero."""
    service = client.app.state.jobs
    service.step_seconds = 0
    return service


def test_the_reply_comes_back_before_the_work_starts(htmx, jobs):
    """The POST reply shows the job as Queued; the service has it Done once the background task ran."""
    response = htmx.post("/jobs", json={"kind": "export"})

    assert response.status_code == 200
    assert "Queued" in response.text
    assert "0 of 12 steps" in response.text

    assert jobs.get(1).state is JobState.DONE


def test_render_does_not_swallow_the_background_task(htmx, jobs):
    """The background task attached to a `@render` handler's response runs."""
    htmx.post("/jobs", json={"kind": "export"})
    assert jobs.get(1).processed == 12


def test_a_running_job_asks_to_be_polled(htmx, jobs):
    """The card for an unfinished job carries a load-delay trigger, an outerHTML swap and a spinner."""
    job = jobs.create(JobKind.EXPORT)

    response = htmx.get(f"/jobs/{job.id}")

    assert response.status_code == 200
    assert f'id="job-{job.id}"' in response.text
    assert 'hx-trigger="load delay:1s"' in response.text
    assert 'hx-swap="outerHTML"' in response.text
    assert f"/jobs/{job.id}" in response.text
    assert "animate-spin" in response.text


def test_a_finished_job_stops_asking(htmx, jobs):
    """The card for a finished job carries no poll trigger, no self `hx-get` and no spinner."""
    htmx.post("/jobs", json={"kind": "export"})

    response = htmx.get("/jobs/1")

    assert "Done" in response.text
    assert "hx-trigger" not in response.text
    # The Details button's `hx-get` points at `/jobs/1/detail`, not `/jobs/1`.
    assert 'hx-get="/jobs/1"' not in response.text
    assert "12 of 12 steps" in response.text
    assert "animate-spin" not in response.text


def test_a_failing_job_stops_asking_too(htmx, jobs):
    """The card for a failed job shows the error and carries no poll trigger."""
    htmx.post("/jobs", json={"kind": "sync"})

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
    """The start form's `hx-indicator` id is rendered on the page."""
    html = client.get("/jobs").text
    assert 'hx-indicator="#job-busy"' in html
    assert 'id="job-busy"' in html
    assert "htmx-indicator" in html


def test_starting_a_job_answers_with_the_container_the_form_targets(htmx, jobs):
    """POST /jobs answers with a `#job-list` element."""
    response = htmx.post("/jobs", json={"kind": "export"})
    assert 'id="job-list"' in response.text
    assert "No jobs yet" not in response.text


def test_starting_a_second_job_still_works(htmx, jobs):
    """The second POST /jobs lists both jobs, newest first."""
    htmx.post("/jobs", json={"kind": "export"})
    response = htmx.post("/jobs", json={"kind": "reindex"})

    assert 'id="job-1"' in response.text
    assert 'id="job-2"' in response.text
    assert response.text.index('id="job-2"') < response.text.index('id="job-1"'), "newest first"


def test_clearing_keeps_the_jobs_that_are_still_moving(htmx, jobs):
    htmx.post("/jobs", json={"kind": "export"})  # finishes
    running = jobs.create(JobKind.REINDEX)  # never runs

    response = htmx.delete("/jobs/finished")

    assert response.status_code == 200
    assert jobs.get(1) is None
    assert jobs.get(running.id) is not None
    assert response.text.lstrip().startswith("<div")
    assert 'id="job-list"' in response.text


def test_clearing_nothing_is_harmless(htmx, jobs):
    assert htmx.delete("/jobs/finished").status_code == 200


def test_a_job_cleared_mid_flight_does_not_crash_its_own_background_task(client, jobs):
    """`run()` on a job id no longer in the store returns without raising."""
    job = jobs.create(JobKind.EXPORT)
    jobs._jobs.pop(job.id)
    jobs.run(job.id)


def test_unknown_job_is_a_404(htmx, jobs):
    assert htmx.get("/jobs/999").status_code == 404


def test_every_details_button_points_at_a_dialog_that_exists(client, jobs):
    """Each Details button's `popovertarget` id is rendered on the page."""
    jobs.create(JobKind.EXPORT)
    html = client.get("/jobs").text

    assert 'popovertarget="job-detail-1"' in html
    assert 'id="job-detail-1"' in html
    assert "popover" in html


def test_the_details_button_targets_the_body_the_dialog_published(client, jobs):
    """The Details button's `hx-target` id matches the dialog body's id."""
    jobs.create(JobKind.EXPORT)
    html = client.get("/jobs").text

    assert 'hx-get="/jobs/1/detail"' in html
    assert 'hx-target="#job-detail-1-body"' in html
    assert 'id="job-detail-1-body"' in html


def test_the_details_button_names_its_own_swap(htmx, jobs):
    """The card polls with `outerHTML`; the Details button inside it declares `innerHTML`."""
    job = jobs.create(JobKind.EXPORT)

    card = htmx.get(f"/jobs/{job.id}").text

    assert 'hx-swap="outerHTML"' in card, "the card still polls itself that way"
    assert 'hx-swap="innerHTML"' in card, "and the trigger inside it must say otherwise"


def test_the_dialog_is_not_inside_the_card_that_replaces_itself(htmx, jobs):
    """The polled card carries the Details trigger but not the dialog."""
    job = jobs.create(JobKind.EXPORT)

    poll = htmx.get(f"/jobs/{job.id}").text

    assert 'popovertarget="job-detail-1"' in poll
    assert 'class="dialog"' not in poll
    assert 'id="job-detail-1"' not in poll


def test_the_detail_is_fetched_only_when_the_dialog_opens(client, jobs):
    """The listing renders the dialog's loading text, not its detail body."""
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
    htmx.post("/jobs", json={"kind": "sync"})

    detail = htmx.get("/jobs/1/detail").text

    assert "Failed" in detail
    assert "Stopped at step 4: upstream refused the connection" in detail


def test_the_detail_of_a_job_that_is_gone_is_a_404(htmx, jobs):
    """GET /jobs/{id}/detail for an unknown id returns 404."""
    assert htmx.get("/jobs/999/detail").status_code == 404


def test_the_job_kinds_drawer_is_modal_where_the_detail_dialog_is_not(client, jobs):
    """The page carries both overlays: a native <dialog> drawer and a popover dialog."""
    jobs.create(JobKind.EXPORT)
    html = client.get("/jobs").text

    assert '<dialog id="job-kinds" class="drawer"' in html
    assert "document.getElementById('job-kinds').showModal()" in html
    assert 'class="dialog" popover id="job-detail-1"' in html


def test_the_drawer_describes_every_kind_the_select_offers(client, jobs):
    """One row per option in the start form's select, each with its step count."""
    html = client.get("/jobs").text

    for _, label in KIND_OPTIONS:
        assert label in html
    assert "12 steps" in html and "8 steps" in html and "6 steps" in html
    assert "wired to fail" in html


def test_the_drawer_is_not_inside_the_list_that_swaps(htmx, jobs):
    """DELETE /jobs/finished returns the list alone, so an open drawer survives it."""
    jobs.create(JobKind.EXPORT)

    swap = htmx.delete("/jobs/finished").text

    assert 'id="job-kinds"' not in swap
    assert "Job kinds" not in swap


def test_the_literal_path_wins_over_the_id_route(htmx, jobs):
    """DELETE /jobs/finished resolves to the clear route, not the `{job_id}` route."""
    assert htmx.delete("/jobs/finished").status_code == 200
