"""The app must still do what it did before it was rewritten on fjkit.

The baseline in `tests/baseline/routes.json` was captured from the pre-fjkit
implementation (`uv run python scripts/capture_baseline.py`) *before* any of it
was replaced. That ordering is the whole value of the file: a baseline captured
afterwards only asserts that the new code equals itself.

Markup is expected to differ — that is what the rewrite was for. What must not
differ is the contract: routes, status codes, links, form fields, htmx wiring,
element ids, row counts, and the domain text on the page.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from capture_baseline import PROBES, signature  # noqa: E402

BASELINE = json.loads((ROOT / "tests" / "baseline" / "routes.json").read_text())

#: Everything here is compared exactly. These are the parts a user or a browser
#: actually depends on, so a difference is a regression by definition.
EXACT = ("fields", "hx_attrs", "hx_targets", "hx_urls", "form_actions", "ids", "row_count")

#: Copy that changed on purpose, listed one word at a time so every intentional
#: change is visible in review. A word going missing that is NOT on this list
#: is a regression. Keeping this list closed is what stops "parity" from
#: quietly degrading into "roughly similar".
ALLOWED_LOST_WORDS = {
    # The demo was renamed; the shell's <title> suffix changed with it.
    "fastapi-jinja2",
    # The `Server-Timing` middleware was removed, and with it the footer
    # sentence that pointed at the header: "— server render time is in the
    # Server-Timing response header". `bench/render_bench.py` is where those
    # numbers come from, and always was; the header only restated them.
    #
    # These are the words that actually stopped appearing anywhere, not every
    # word in the sentence — "the", "in" and "time" survive elsewhere on the
    # pages that carry them. Listing the observed set rather than a generous
    # superset is what keeps this list from turning into a stop-word exemption
    # that would hide the next real loss.
    "Server-Timing",
    "server",
    "render",
    "is",
    "response",
    "header",
    "—",
}

#: Per-probe exceptions for copy that left one page on purpose. "Advance" still
#: has to appear on /tasks; it only left the overview, which is read-only.
ALLOWED_LOST_WORDS_BY_PROBE = {
    "GET /": {"Advance"},
}

#: Same idea for links. The stylesheet moved into the package — that *is* the
#: rewrite, so the old app-served path is expected to disappear.
ALLOWED_LOST_HREFS = {"/static/dist/app.css"}

#: GET / used to ship the same mutating row as /tasks. The overview is now
#: read-only; those htmx hooks live on the board. Everywhere else is exact.
#:
#: `ids` is the one field where an *addition* still fails, and deliberately so:
#: an id is an htmx target, and a page that quietly grows or renames one is how
#: a swap starts landing in the wrong place. So the shell's sidebar — which is
#: on every full page now — is written out here per probe rather than waved
#: through by a rule, which keeps every new id a line someone had to add.
ALLOWED_CONTRACT_DRIFT = {
    "GET /": {
        "hx_attrs": [],
        "hx_targets": [],
        "hx_urls": [],
        "ids": ["sidebar"],
    },
    "GET /tasks": {
        "ids": ["board", "f-owner", "f-priority", "f-title", "sidebar"],
    },
    "GET /tasks/report?rows=5": {
        "ids": ["sidebar"],
    },
}


@pytest.fixture(scope="module")
def snapshot() -> dict:
    """Probe the live app the same way the baseline was captured.

    A fresh client per probe, because the service is in-memory and mutable: one
    POST leaking into the next probe would make the comparison meaningless.
    """
    from app.main import create_app

    out: dict = {}
    for method, url, data, headers in PROBES:
        with TestClient(create_app()) as client:
            response = client.request(method, url, data=data, headers=headers)
            entry: dict = {"status": response.status_code}
            if response.headers.get("content-type", "").startswith("text/html"):
                entry |= signature(response.text)
            out[f"{method} {url}"] = entry
    return out


PROBE_IDS = list(BASELINE)


@pytest.mark.parametrize("probe", PROBE_IDS)
def test_status_code_is_unchanged(snapshot, probe):
    assert snapshot[probe]["status"] == BASELINE[probe]["status"]


@pytest.mark.parametrize("probe", PROBE_IDS)
@pytest.mark.parametrize("field", EXACT)
def test_contract_is_unchanged(snapshot, probe, field):
    expected = ALLOWED_CONTRACT_DRIFT.get(probe, {}).get(field, BASELINE[probe].get(field))
    actual = snapshot[probe].get(field)
    assert actual == expected, f"{probe}: {field} changed"


@pytest.mark.parametrize("probe", PROBE_IDS)
def test_no_visible_text_was_lost(snapshot, probe):
    """Added words are fine — new copy is allowed. Missing words are not."""
    lost = set(BASELINE[probe].get("words", [])) - set(snapshot[probe].get("words", []))
    allowed = ALLOWED_LOST_WORDS | ALLOWED_LOST_WORDS_BY_PROBE.get(probe, set())
    assert not (lost - allowed), f"{probe}: text disappeared: {sorted(lost)}"


@pytest.mark.parametrize("probe", PROBE_IDS)
def test_no_link_was_lost(snapshot, probe):
    lost = set(BASELINE[probe].get("hrefs", [])) - set(snapshot[probe].get("hrefs", []))
    assert not (lost - ALLOWED_LOST_HREFS), f"{probe}: links disappeared: {sorted(lost)}"
