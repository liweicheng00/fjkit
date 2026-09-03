"""Compares the live app against the baseline in `tests/baseline/routes.json`.

The demo is rewritten as the kit grows, and its behaviour is meant to survive
that: a failure here says a status code, an htmx attribute, a form field, a link
or a piece of visible text changed. Record an intended change in the allow lists
below, or re-run `scripts/capture_baseline.py` to move the baseline itself.
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

#: Signature fields compared exactly against the baseline.
EXACT = ("fields", "hx_attrs", "hx_targets", "hx_urls", "form_actions", "ids", "row_count")

#: Words allowed to be missing from any probe's visible text.
ALLOWED_LOST_WORDS = {
    "fastapi-jinja2",
    "board",
    "Server-Timing",
    "server",
    "render",
    "is",
    "response",
    "header",
    "—",
}

#: Words allowed to be missing from one probe's visible text.
ALLOWED_LOST_WORDS_BY_PROBE = {
    "GET /": {"Advance", "components;"},
}

#: Hrefs allowed to be missing from any probe.
ALLOWED_LOST_HREFS = {"/static/dist/app.css"}

#: The `ids` every board response carries.
BOARD_IDS = ["board", "f-owner", "f-priority", "f-title", "new-task"]

#: The `hx_attrs` every board response carries.
BOARD_HX_ATTRS = [
    "hx-confirm",
    "hx-delete",
    "hx-disabled-elt",
    "hx-disinherit",
    "hx-ext",
    "hx-get",
    "hx-on::after-request",
    "hx-post",
    "hx-swap",
    "hx-target",
]

#: Per-probe expected values that replace the baseline's for the named fields.
ALLOWED_CONTRACT_DRIFT = {
    "GET /": {
        "hx_attrs": [],
        "hx_targets": [],
        "hx_urls": [],
        "ids": ["sidebar", "toaster"],
    },
    "GET /tasks": {
        "hx_attrs": BOARD_HX_ATTRS,
        "ids": [*BOARD_IDS, "sidebar", "toaster"],
    },
    "GET /tasks/board": {"hx_attrs": BOARD_HX_ATTRS, "ids": BOARD_IDS},
    "GET /tasks/board?status=todo": {"hx_attrs": BOARD_HX_ATTRS, "ids": BOARD_IDS},
    "GET /tasks/board?status=done": {"hx_attrs": BOARD_HX_ATTRS, "ids": BOARD_IDS},
    "GET /tasks/board?owner=kai": {"hx_attrs": BOARD_HX_ATTRS, "ids": BOARD_IDS},
    "POST /tasks": {"hx_attrs": BOARD_HX_ATTRS, "ids": BOARD_IDS},
    "POST /tasks/5/advance": {"hx_attrs": BOARD_HX_ATTRS, "ids": BOARD_IDS},
    "DELETE /tasks/1": {"hx_attrs": BOARD_HX_ATTRS, "ids": BOARD_IDS},
    "GET /tasks/report?rows=5": {
        "ids": ["sidebar", "toaster"],
    },
}


@pytest.fixture(scope="module")
def snapshot() -> dict:
    """Run every probe against a fresh app and return each response's signature."""
    from app.main import create_app

    out: dict = {}
    for method, url, body, headers in PROBES:
        with TestClient(create_app()) as client:
            response = client.request(method, url, json=body, headers=headers)
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
    """The fields a browser acts on: a lost `hx-target` or form field fails in the page, not in a test."""
    expected = ALLOWED_CONTRACT_DRIFT.get(probe, {}).get(field, BASELINE[probe].get(field))
    actual = snapshot[probe].get(field)
    assert actual == expected, f"{probe}: {field} changed"


@pytest.mark.parametrize("probe", PROBE_IDS)
def test_no_visible_text_was_lost(snapshot, probe):
    """A refactor may add copy; dropping copy is a regression unless it is on an allow list."""
    lost = set(BASELINE[probe].get("words", [])) - set(snapshot[probe].get("words", []))
    allowed = ALLOWED_LOST_WORDS | ALLOWED_LOST_WORDS_BY_PROBE.get(probe, set())
    assert not (lost - allowed), f"{probe}: text disappeared: {sorted(lost)}"


@pytest.mark.parametrize("probe", PROBE_IDS)
def test_no_link_was_lost(snapshot, probe):
    """A link that disappears leaves part of the app unreachable, and every other test still passes."""
    lost = set(BASELINE[probe].get("hrefs", [])) - set(snapshot[probe].get("hrefs", []))
    assert not (lost - ALLOWED_LOST_HREFS), f"{probe}: links disappeared: {sorted(lost)}"
