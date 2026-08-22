"""The documentation site is a fjkit app, and these are the tests that say so.

`examples/board` proves the kit can build a back office. This site proves it can
build the other thing every project needs — a documentation site with prose,
source listings, tab strips and a navigation rail — and it is the harder case,
because a docs page keeps reaching for shapes an admin never needs.

The value is the failures. When one of these needs a new utility class to pass,
that is the kit missing a component, and the missing component is named in
`assets/brand.css` under PART 2 before it is worked around anywhere.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fjkit.cli.check import check_templates

DOCS = Path(__file__).resolve().parents[1] / "docs" / "workbench"
TEMPLATES = DOCS / "templates"

#: Every page template, both languages. The Chinese pages are the same four
#: pages translated — same `sections`, same shell — so they answer to the same
#: assertions rather than a relaxed set.
PAGES = [
    "introduction.html",
    "learn.html",
    "plugins.html",
    "components.html",
    "zh/introduction.html",
    "zh/learn.html",
    "zh/plugins.html",
    "zh/components.html",
]


def test_the_site_stays_inside_the_vocabulary():
    """The same gate `examples/board` passes, on the docs site's own templates.

    This is the whole claim. If it fails, the site has started writing markup
    the kit cannot express — and the fix is a component, not an exemption.
    """
    violations = check_templates(TEMPLATES)
    assert not violations, "\n".join(v.render(TEMPLATES) for v in violations)


def test_the_shell_is_the_kit_s():
    """An app that stops extending the shell has quietly taken on the <head>,
    the theme flash-guard and the asset links. Then the site is no longer
    evidence of anything."""
    assert '{% extends "ui/shell.html" %}' in (TEMPLATES / "base.html").read_text()


@pytest.mark.parametrize("name", PAGES, ids=lambda n: n.removesuffix(".html"))
def test_pages_extend_the_site_shell(name):
    assert '{% extends "base.html" %}' in (TEMPLATES / name).read_text()


@pytest.mark.parametrize("name", PAGES, ids=lambda n: n.removesuffix(".html"))
def test_every_page_declares_its_rail(name):
    """`base.html` builds the "On this page" group from a top-level `sections`
    set in each page, so a page without one renders a navigation with nothing
    in it rather than failing."""
    assert "{% set sections = [" in (TEMPLATES / name).read_text()


#: A listener that goes looking for a tab element. Reading which tab is selected
#: is fine; binding an input event and resolving a tab from it is the site
#: taking over a component it ships.
_LISTENER_FINDS_A_TAB = re.compile(
    r"""addEventListener\(\s*["'](?:click|keydown|keyup)["'][\s\S]{0,400}?\[role=["']tab["']\]"""
)


def test_no_page_drives_tab_selection():
    """Basecoat's `.tabs` owns which tab is selected, the roving tabindex and
    the arrow keys, and the shell already loads it.

    *Reading* that selection is allowed, and `components.js` does: the preview,
    the two code panes and the caption sit outside the tab group and still have
    to follow it, and `aria-selected` is the one place every input path — click,
    arrow key, a script calling `select()` — has to write. What this forbids is
    a listener that resolves a tab itself, because that is how a keyboard user
    ends up with one tab underlined and a different one's content on screen.

    The earlier version of this test looked for `role="tab"]` and `closest` in
    the same file. It failed the day a caption mentioned `hx-target="closest
    tr"`, which is the shape of an assertion matching prose rather than code.
    """
    for path in sorted((DOCS / "assets").glob("*.js")):
        assert not _LISTENER_FINDS_A_TAB.search(path.read_text()), (
            f"{path.name} looks like it is selecting tabs itself — Basecoat does that"
        )


def test_the_quoted_routes_are_the_demo_s():
    """Lesson 06 quotes two of the demo's routes to show one handler answering
    with HTML and with JSON. The snippet is a literal in `build.py` because a
    live capture would rewrite `docs/` on every build — so nothing but this
    stops it describing routes the demo no longer has.

    Only the decorator lines are compared. The bodies in the snippet are
    trimmed and re-commented for the page, which is the point of quoting rather
    than dumping the file.
    """
    import sys

    sys.path.insert(0, str(DOCS))
    try:
        import build  # type: ignore[import-not-found]
    finally:
        sys.path.pop(0)

    router = (
        Path(__file__).resolve().parents[3] / "examples" / "board" / "app" / "features" / "tasks" / "router.py"
    ).read_text()

    quoted = [line for line in build.NEGOTIATION["route"].splitlines() if line.startswith("@")]
    assert quoted, "the snippet quotes no routes at all"
    missing = [line for line in quoted if line not in router]
    assert not missing, "Lesson 06 quotes decorators the demo no longer declares:\n" + "\n".join(missing)


def test_the_site_builds():
    """End to end: all eight pages — four, twice — render through the real
    Environment.

    Also the only test that proves `url_for`/`is_active` still satisfy the
    signatures `sidebar_link` and `brand` call them with — a static site swaps
    those globals out, and the shell has no idea.
    """
    import sys

    sys.path.insert(0, str(DOCS))
    try:
        import build  # type: ignore[import-not-found]
    finally:
        sys.path.pop(0)

    from types import SimpleNamespace

    from fjkit import FjkitConfig, build_environment

    for lang in build.LANGS:
        env = build_environment(
            FjkitConfig(
                template_dir=TEMPLATES,
                static_url=lang["static"],
                auto_reload=False,
                globals={"url_for": build.url_for, "is_active": build.is_active},
            )
        )
        pages = [{k: v for k, v in p.items() if k not in build.LANG_BY_CODE} | p[lang["code"]] for p in build.PAGES]
        for page in pages:
            html = env.get_template(f"{lang['templates']}{page['route']}.html").render(
                request=SimpleNamespace(route=page["route"], lang=lang["code"]),
                pages=pages,
                page=page,
                lang=lang,
                t=build.STRINGS[lang["code"]],
                wire=build.NEGOTIATION,
            )
            assert html.startswith("<!doctype html>")
            assert 'class="sidebar"' in html, "the shell's sidebar block went unfilled"
            assert page["title"] in html
            assert f'<html lang="{lang["html_lang"]}"' in html


def test_every_asset_link_is_relative_to_its_page():
    """GitHub Pages serves this site from a project subpath — `/fjkit/`, not
    `/` — and the Chinese pages sit one directory deeper than the English ones.

    An absolute `/assets/...` would 404 on Pages while working perfectly from a
    local server rooted at `docs/`, which is the failure that only shows up
    after publishing. So the rule is checked on the built files: every link a
    page makes is relative, and resolves to a file that exists next to it.
    """
    out = Path(__file__).resolve().parents[3] / "docs"
    if not (out / "index.html").exists():
        pytest.skip("the site has not been built in this checkout")

    names = ("index.html", "learn.html", "plugins.html", "components.html")
    pages = [out / name for name in names]
    pages += [out / "zh" / name for name in names]

    for page in pages:
        html = page.read_text(encoding="utf-8")
        for ref in re.findall(r'(?:href|src)="([^"]+)"', html):
            if ref.startswith(("http://", "https://", "#", "mailto:", "data:")):
                continue
            assert not ref.startswith("/"), f"{page.name} links to {ref}, which breaks under /fjkit/"
            # The fragment and the query are not part of the path. `fjkit_static`
            # stamps every asset with `?v=<mtime>` so a browser cannot serve a
            # stale stylesheet against current markup; a static host ignores the
            # query and serves the file, and so must this check.
            target = (page.parent / ref.split("#")[0].split("?")[0]).resolve()
            assert target.exists(), f"{page.relative_to(out)} links to {ref}, which is not there"
