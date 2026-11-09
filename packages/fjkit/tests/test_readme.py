"""The two READMEs are the funnel, and these tests hold them to the package.

There are two, with different readers and no mechanism keeping them in step.
`README.md` at the repository root is what GitHub shows. `packages/fjkit/README.md`
is `readme` in that package's `pyproject.toml`, so it is the long description
baked into the wheel and rendered on the PyPI project page.

Both got the same two things wrong, and both failed silently. A version that
stopped being true at the last release: the root file claimed 0.1.0 against a
0.4.0 wheel, and the packaged file claimed 0.1.0 on the live PyPI page for
0.4.0. And a quickstart nobody runs — the first thing a reader executes, in
three hand-written copies, counting the site's Introduction page.

So the quickstarts are executed here rather than proof-read, both Status lines
are compared against `pyproject.toml`, and the last test holds the site's copy
of the root quickstart to the root README.

A version bump therefore has to touch both files, which is step 1 of
`RELEASE.md` and is stated there.
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
PYPROJECT = PACKAGE / "pyproject.toml"

#: `(label, path, quickstart heading)`. The heading is load-bearing: renaming it
#: fails these tests rather than quietly leaving the samples untested.
READMES = [
    ("README.md", REPO / "README.md", "## A page in two files"),
    ("packages/fjkit/README.md", PACKAGE / "README.md", "## A working page"),
]

#: The root file writes `## Status` and then the version on the next line; the
#: packaged file writes `Status: 0.4.0.` inline. One pattern reads both, because
#: the claim is the word followed by a version, not a particular heading level.
_STATUS_VERSION = re.compile(r"Status[:\s]+(\d+\.\d+\.\d+)")

_FENCE = re.compile(r"```(\w+)\n(.*?)```", re.S)


def _ids(case) -> str:
    return case[0]


def _packaged_version() -> str:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]["version"]


def _section(path: Path, heading: str) -> str:
    """The body of one `##` section of a README."""
    text = path.read_text(encoding="utf-8")
    assert heading in text, f"{path.name} no longer has a `{heading}` section"
    return text.split(heading, 1)[1].split("\n## ", 1)[0]


def _one_block(section: str, lang: str, label: str) -> str:
    """The single fenced block of `lang` in `section`.

    One, not the first: a second Python sample in a quickstart would be shipped
    untested, and that is the failure this file exists to stop.
    """
    blocks = [body for tag, body in _FENCE.findall(section) if tag == lang]
    assert len(blocks) == 1, f"{label}'s quickstart has {len(blocks)} {lang} blocks; this executes exactly one"
    return blocks[0]


@pytest.mark.parametrize("case", READMES, ids=_ids)
def test_the_readme_states_the_packaged_version(case):
    """Each README's Status line carries the version in `pyproject.toml`.

    A release bumps the version in one place. Nothing used to read either of the
    other two, so both went three minor versions stale without a red build —
    including the one PyPI was serving.
    """
    label, path, _ = case
    found = _STATUS_VERSION.search(path.read_text(encoding="utf-8"))

    assert found, f"{label} should state `Status` followed by the version"
    assert found.group(1) == _packaged_version(), (
        f"{label} says {found.group(1)}, pyproject.toml says {_packaged_version()}"
    )


@pytest.mark.parametrize("case", READMES, ids=_ids)
def test_the_readme_quickstart_runs(case, tmp_path):
    """Each README's quickstart is written to disk and served.

    This is the highest-risk content on the funnel: it is the first thing a
    reader runs, and a broken sample costs the reader before it costs anyone
    here. Reading it cannot establish that `@render` still spreads the model,
    that the shell still resolves, or that `stat` still takes `tone=`.
    """
    label, path, heading = case
    section = _section(path, heading)

    main = tmp_path / "main.py"
    main.write_text(_one_block(section, "python", label), encoding="utf-8")
    templates = tmp_path / "templates"
    templates.mkdir()
    (templates / "overview.html").write_text(_one_block(section, "jinja", label), encoding="utf-8")

    # `__file__` is what the sample's `Path(__file__).parent / "templates"`
    # resolves against, so the module is executed as if it were that file.
    namespace: dict[str, object] = {"__file__": str(main), "__name__": "readme_quickstart"}
    exec(compile(main.read_text(encoding="utf-8"), str(main), "exec"), namespace)  # noqa: S102

    response = TestClient(namespace["app"]).get("/")

    assert response.status_code == 200, response.text
    assert response.text.startswith("<!doctype html>"), f"{label}'s template should extend the kit's shell"
    assert "Overview" in response.text, "`page_header` did not render the title"
    assert "18" in response.text, "`@render` did not pass the model's fields to the template"


def test_the_landing_page_shows_the_same_quickstart():
    """The site's Introduction page repeats both samples, as Jinja string
    literals in `docs/workbench/templates/introduction.html`.

    Three copies of the thing a reader runs first is two too many, and the
    site's copy is the one no test executes. Until there is a single source,
    this is what stops it diverging from the root README.
    """
    built = REPO / "docs" / "index.html"
    if not built.exists():
        pytest.skip("the site has not been built in this checkout")

    label, path, heading = READMES[0]
    page = html.unescape(built.read_text(encoding="utf-8"))
    section = _section(path, heading)

    for lang in ("python", "jinja"):
        sample = _one_block(section, lang, label).strip()
        assert sample in page, (
            f"the landing page's {lang} sample is not {label}'s. "
            "Both are written by hand; edit the other one to match."
        )
