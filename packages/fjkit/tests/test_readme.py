"""The README is the funnel, and these tests hold it to the package.

Someone arriving from PyPI or GitHub reads this file before anything else, and
the two things it is most likely to get wrong both fail silently: a version that
stopped being true at the last release, and a code sample that no longer runs.
Neither shows up in a test suite that only exercises the package, which is how
`README.md` came to claim 0.1.0 against a 0.4.0 wheel.

So the quickstart is executed here rather than proof-read. The landing page
carries the same two samples — written a second time, in a Jinja string — and
the last test compares the built page against the README so the copies cannot
drift apart.
"""

from __future__ import annotations

import html
import re
import tomllib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

PACKAGE = Path(__file__).resolve().parents[1]
REPO = PACKAGE.parents[1]
README = REPO / "README.md"
PYPROJECT = PACKAGE / "pyproject.toml"

#: The quickstart heading. Both samples under it are executed below, so the
#: heading is load-bearing: renaming it fails these tests rather than quietly
#: leaving the samples untested.
QUICKSTART = "## A page in two files"

#: `## Status` holds one sentence, and it opens with the version.
STATUS = "## Status"

_FENCE = re.compile(r"```(\w+)\n(.*?)```", re.S)
_OPENING_VERSION = re.compile(r"^(\d+\.\d+\.\d+)")


def _packaged_version() -> str:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]["version"]


def _section(heading: str) -> str:
    """The body of one `##` section of the README."""
    text = README.read_text(encoding="utf-8")
    assert heading in text, f"the README no longer has a `{heading}` section"
    return text.split(heading, 1)[1].split("\n## ", 1)[0]


def _one_block(section: str, lang: str) -> str:
    """The single fenced block of `lang` in `section`.

    One, not the first: a second Python sample in the quickstart would be
    shipped untested, and that is the failure this file exists to stop.
    """
    blocks = [body for tag, body in _FENCE.findall(section) if tag == lang]
    assert len(blocks) == 1, f"the quickstart has {len(blocks)} {lang} blocks; this test executes exactly one"
    return blocks[0]


def test_the_readme_states_the_packaged_version():
    """`## Status` opens with the version in `packages/fjkit/pyproject.toml`.

    A release bumps the version in one place. Nothing used to read the other,
    so the README went three minor versions stale without a red build.
    """
    status = _section(STATUS).strip()
    found = _OPENING_VERSION.match(status)

    assert found, f"`{STATUS}` should open with the version; it opens with {status[:40]!r}"
    assert found.group(1) == _packaged_version(), (
        f"the README says {found.group(1)}, pyproject.toml says {_packaged_version()}"
    )


def test_the_readme_quickstart_runs(tmp_path):
    """The two files of "a page in two files" are written to disk and served.

    This is the highest-risk content on the funnel: it is the first thing a
    reader runs, and a broken sample costs the reader before it costs anyone
    here. Reading it cannot establish that `@render` still spreads the model,
    that the shell still resolves, or that `stat` still takes `tone=`.
    """
    section = _section(QUICKSTART)

    main = tmp_path / "main.py"
    main.write_text(_one_block(section, "python"), encoding="utf-8")
    templates = tmp_path / "templates"
    templates.mkdir()
    (templates / "overview.html").write_text(_one_block(section, "jinja"), encoding="utf-8")

    # `__file__` is what the sample's `Path(__file__).parent / "templates"`
    # resolves against, so the module is executed as if it were that file.
    namespace: dict[str, object] = {"__file__": str(main), "__name__": "readme_quickstart"}
    exec(compile(main.read_text(encoding="utf-8"), str(main), "exec"), namespace)  # noqa: S102

    response = TestClient(namespace["app"]).get("/")

    assert response.status_code == 200, response.text
    assert response.text.startswith("<!doctype html>"), "the sample's template should extend the kit's shell"
    assert "Overview" in response.text, "`page_header` did not render the title"
    assert "18" in response.text, "`@render` did not pass the model's fields to the template"


def test_the_landing_page_shows_the_same_quickstart():
    """The site's Introduction page repeats both samples, as Jinja string
    literals in `docs/workbench/templates/introduction.html`.

    Two copies of the thing a reader runs first is one copy too many, and the
    site's copy is the one no test executes. Until there is a single source,
    this is what stops them diverging.
    """
    built = REPO / "docs" / "index.html"
    if not built.exists():
        pytest.skip("the site has not been built in this checkout")

    page = html.unescape(built.read_text(encoding="utf-8"))
    section = _section(QUICKSTART)

    for lang in ("python", "jinja"):
        sample = _one_block(section, lang).strip()
        assert sample in page, (
            f"the landing page's {lang} sample is not the README's. "
            "Both are written by hand; edit the other one to match."
        )
