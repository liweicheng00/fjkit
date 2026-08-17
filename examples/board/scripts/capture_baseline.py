"""Snapshot what the app does, so a rewrite can be checked against it.

    uv run python scripts/capture_baseline.py

Run this BEFORE replacing an implementation, never after: a baseline captured
from the new code just asserts that the new code equals itself.

What it records is *semantic*, not byte-level. The markup is expected to change
— that is the point of the rewrite. What must not change is the route set, the
status codes, the links, the form fields, the htmx wiring, and the domain data
on the page.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "tests" / "baseline" / "routes.json"

#: Sent on the probes that only htmx ever calls. Every request htmx makes
#: carries it, so a bare request to a swap endpoint models a client that does
#: not exist — and under `render_mode="auto"` it is answered with the model
#: rather than the fragment.
#:
#: This does not weaken the comparison. The pre-fjkit app read no htmx headers
#: at all, so it would have returned exactly the same markup with or without
#: this one: the baseline the probes are checked against is unchanged, and
#: every field in `EXACT` is still compared exactly.
HTMX = {"HX-Request": "true"}

#: Each entry is a fresh client, so a mutating call cannot contaminate the next
#: snapshot. `TaskService` seeds deterministically, so repeated runs agree.
PROBES: list[tuple[str, str, dict | None, dict | None]] = [
    ("GET", "/", None, None),
    ("GET", "/tasks", None, None),
    ("GET", "/tasks/board", None, HTMX),
    ("GET", "/tasks/board?status=todo", None, HTMX),
    ("GET", "/tasks/board?status=done", None, HTMX),
    ("GET", "/tasks/board?owner=kai", None, HTMX),
    ("GET", "/tasks/report?rows=5", None, None),
    ("GET", "/health", None, None),
    ("POST", "/tasks", {"title": "Parity probe", "priority": "high", "owner": "ana"}, HTMX),
    ("POST", "/tasks/5/advance", None, HTMX),
    ("DELETE", "/tasks/1", None, HTMX),
    ("DELETE", "/tasks/999", None, HTMX),
]

TAG = re.compile(r"<[^>]+>")
SCRIPT = re.compile(r"<(script|style)\b.*?</\1>", re.DOTALL | re.IGNORECASE)


def signature(html: str) -> dict:
    """The parts of a response a rewrite must preserve."""
    body = SCRIPT.sub(" ", html)
    words = TAG.sub(" ", body).split()

    return {
        "hrefs": sorted(set(re.findall(r'href="([^"]*)"', html))),
        "fields": sorted(set(re.findall(r'<(?:input|select|textarea)[^>]*name="([^"]*)"', html))),
        "hx_attrs": sorted(set(re.findall(r"\b(hx-[a-z:-]+)=", html))),
        "hx_targets": sorted(set(re.findall(r'hx-target="([^"]*)"', html))),
        "hx_urls": sorted(set(re.findall(r'hx-(?:get|post|delete|put|patch)="([^"]*)"', html))),
        "form_actions": sorted(set(re.findall(r'<form[^>]*hx-post="([^"]*)"', html))),
        "ids": sorted(set(re.findall(r'\bid="([^"]*)"', html))),
        # Every word on the page, as a set. Used to assert nothing was lost;
        # additions (a changed footer, new copy) are allowed.
        "words": sorted(set(words)),
        "row_count": html.count("<tr>"),
    }


def capture(create_app) -> dict:
    snapshot: dict = {}
    for method, url, data, headers in PROBES:
        with TestClient(create_app()) as client:
            response = client.request(method, url, data=data, headers=headers)
            entry: dict = {"status": response.status_code}
            if response.headers.get("content-type", "").startswith("text/html"):
                entry |= signature(response.text)
            snapshot[f"{method} {url}"] = entry
    return snapshot


def main() -> int:
    from app.main import create_app

    snapshot = capture(create_app)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"{OUT.relative_to(ROOT)}")
    for key, entry in snapshot.items():
        print(f"  {entry['status']}  {key:<34} {len(entry.get('words', [])):>4} words")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
