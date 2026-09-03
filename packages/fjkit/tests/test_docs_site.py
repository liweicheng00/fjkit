"""The documentation site is a fjkit app, and these tests hold it to that.

`examples/fjkit-demo` proves the kit can build a back office. This site proves
it can build a documentation site — prose, source listings, tab strips and a
navigation rail — which is the harder case, because a docs page keeps reaching
for shapes an admin never needs.

The failures are the value. When one of these needs a new utility class to
pass, the kit is missing a component, and that component is named in
`assets/brand.css` under PART 2 before it is worked around anywhere.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fjkit.cli.check import check_templates

DOCS = Path(__file__).resolve().parents[1] / "docs" / "workbench"
TEMPLATES = DOCS / "templates"

#: Every page template, both languages. The Chinese pages are the same five
#: pages translated, with the same `sections` and the same shell, so they answer
#: to the same assertions rather than a relaxed set.
PAGES = [
    "introduction.html",
    "learn.html",
    "plugins.html",
    "components.html",
    "cheatsheet.html",
    "zh/introduction.html",
    "zh/learn.html",
    "zh/plugins.html",
    "zh/components.html",
    "zh/cheatsheet.html",
]


def test_the_site_stays_inside_the_vocabulary():
    """The same gate `examples/fjkit-demo` passes, on the docs site's templates.

    A failure means the site has started writing markup the kit cannot express.
    The fix is a component, not an exemption.
    """
    violations = check_templates(TEMPLATES)
    assert not violations, "\n".join(v.render(TEMPLATES) for v in violations)


def test_the_shell_is_the_kit_s():
    """An app that stops extending the shell has taken on the `<head>`, the
    theme flash-guard and the asset links itself, and the site is then no longer
    evidence that the kit can build it."""
    assert '{% extends "ui/shell.html" %}' in (TEMPLATES / "base.html").read_text()


@pytest.mark.parametrize("name", PAGES, ids=lambda n: n.removesuffix(".html"))
def test_pages_extend_the_site_shell(name):
    assert '{% extends "base.html" %}' in (TEMPLATES / name).read_text()


@pytest.mark.parametrize("name", PAGES, ids=lambda n: n.removesuffix(".html"))
def test_every_page_declares_its_rail(name):
    """`base.html` builds the "On this page" group from a top-level `sections`
    set in each page. A page without one renders an empty navigation rather than
    failing."""
    assert "{% set sections = [" in (TEMPLATES / name).read_text()


#: `{% call lesson("wiring", "01", …) %}` — the badge printed beside a heading.
_LESSON_CALL = re.compile(r'\{%\s*call lesson\("([\w-]+)",\s*"(\d+)"')

#: `{"id": "wiring", "num": "01", …}` — the same count, in the navigation rail.
_RAIL_NUMBER = re.compile(r'\{"id":\s*"([\w-]+)",\s*"num":\s*"(\d+)"')


@pytest.mark.parametrize("name", PAGES, ids=lambda n: n.removesuffix(".html"))
def test_the_rail_counts_the_way_the_page_does(name):
    """The number beside a heading and the number in the rail are written twice
    — once in the `lesson()` call, once in `sections` — so this is what stops
    the two from drifting after a lesson is inserted or removed.

    Order matters as well as membership: the rail is the reading order.

    A section with no number is not an error. The Cheatsheet numbers nothing on
    purpose, and a trailing "Read next" band carries no badge, so both sides are
    simply absent for those.
    """
    text = (TEMPLATES / name).read_text()
    assert _LESSON_CALL.findall(text) == _RAIL_NUMBER.findall(text)


#: A listener that goes looking for a tab element. Reading which tab is
#: selected is allowed; binding an input event and resolving a tab from it is
#: the site taking over a component it ships.
_LISTENER_FINDS_A_TAB = re.compile(
    r"""addEventListener\(\s*["'](?:click|keydown|keyup)["'][\s\S]{0,400}?\[role=["']tab["']\]"""
)


def test_no_page_drives_tab_selection():
    """Basecoat's `.tabs` owns tab selection, the roving tabindex and the arrow
    keys, and the shell already loads it.

    Reading that selection is allowed, and `components.js` does: the preview,
    the two code panes and the caption sit outside the tab group and still have
    to follow it, and every input path (click, arrow key, a script calling
    `select()`) writes `aria-selected`. What this forbids is a listener that
    resolves a tab itself, because that leaves a keyboard user with one tab
    underlined and another tab's content on screen.

    The earlier version looked for `role="tab"]` and `closest` in the same file.
    It failed the day a caption mentioned `hx-target="closest tr"` — an
    assertion matching prose rather than code.
    """
    for path in sorted((DOCS / "assets").glob("*.js")):
        assert not _LISTENER_FINDS_A_TAB.search(path.read_text()), (
            f"{path.name} looks like it is selecting tabs itself — Basecoat does that"
        )


#: `{% macro name(` — the definition, not a call. Underscore-prefixed names are
#: the file's own helpers (`_message`, `_ROWS`) and are no more part of the
#: vocabulary than a private function is part of an API.
_MACRO = re.compile(r"\{%-?\s*macro\s+(\w+)\(")

UI = Path(__file__).resolve().parents[1] / "src" / "fjkit" / "templates" / "ui"


def _cheatsheet():
    """Import the Cheatsheet page's data module. It sits beside `build.py` in
    the workbench rather than in the package, so it is imported the same way."""
    import sys

    sys.path.insert(0, str(DOCS))
    try:
        import cheatsheet  # type: ignore[import-not-found]
    finally:
        sys.path.pop(0)
    return cheatsheet


def _rows() -> list[tuple[str, str, bool]]:
    """Every row on the page, as (macro name, the file it is filed under,
    whether the sheet claims it takes a block)."""
    return [
        (macro["call"].split("(")[0], file["name"], bool(macro["block"]))
        for group in _cheatsheet().GROUPS
        for file in group["files"]
        for macro in file["macros"]
    ]


def test_the_cheatsheet_names_every_macro():
    """The Cheatsheet page is the index, and a reader treats it as complete: a
    macro missing from it does not exist as far as this site is concerned.

    The rows are hand-written, because no generator produces the grouping, the
    Block column and the one-line notes that make an index readable. This test
    stops that half falling behind the package; it caught `form_scripts` and
    `multiselect_scripts`, both shipped without a line on the page.

    The file is checked as well as the name. `cheatsheet.py` files each macro
    under the path you import it from, and a row filed under the wrong path is
    worse than a missing row: it sends a reader to write an import that raises.
    """
    listed = {name: filed for name, filed, _ in _rows()}
    wrong = []
    for path in sorted(UI.glob("*.html")):
        for name in _MACRO.findall(path.read_text()):
            if name.startswith("_"):
                continue
            if name not in listed:
                wrong.append(f"{path.name}: {name} — no row")
            elif listed[name] != f"ui/{path.name}":
                wrong.append(f"{path.name}: {name} — filed under {listed[name]}")
    assert not wrong, "the cheatsheet and ui/ disagree:\n" + "\n".join(wrong)


def test_the_cheatsheet_block_column_matches_the_macros():
    """The Block column is the one thing on the page not copied from a
    signature, and it is why the page exists: `·  block` was a notation a reader
    had to guess at, so it became a column that says it in words.

    Hand-written claims about the source can be wrong, and this test says so.
    `caller()` in the macro body is the fact: a macro that calls it takes a
    block, and one that does not, does not.
    """
    listed = {name: takes_block for name, _, takes_block in _rows()}
    wrong = []
    for path in sorted(UI.glob("*.html")):
        source = path.read_text()
        names = _MACRO.findall(source)
        bodies = re.split(r"\{%-?\s*macro\s+\w+\(", source)[1:]
        for name, body in zip(names, bodies, strict=True):
            if name.startswith("_"):
                continue
            takes = "caller(" in body.split("{% endmacro %}")[0]
            if takes != listed[name]:
                claim = "takes a block" if listed[name] else "takes no block"
                wrong.append(f"{path.name}: {name} — the sheet says it {claim}")
    assert not wrong, "the Block column disagrees with the macro bodies:\n" + "\n".join(wrong)


def test_the_cheatsheet_reads_the_same_in_both_languages():
    """`for_lang` keeps one index behind two pages, so both builds come out with
    the same rows in the same order. The notes differ; nothing structural
    does."""
    en = _cheatsheet().for_lang("en")
    zh = _cheatsheet().for_lang("zh")

    assert [g["id"] for g in en["groups"]] == [g["id"] for g in zh["groups"]]
    for group_en, group_zh in zip(en["groups"], zh["groups"], strict=True):
        assert [f["name"] for f in group_en["files"]] == [f["name"] for f in group_zh["files"]]
        for file_en, file_zh in zip(group_en["files"], group_zh["files"], strict=True):
            assert [m["call"] for m in file_en["macros"]] == [m["call"] for m in file_zh["macros"]]
            for macro_en, macro_zh in zip(file_en["macros"], file_zh["macros"], strict=True):
                assert bool(macro_en["block"]) == bool(macro_zh["block"]), (
                    f"{macro_en['call']} carries a block badge in only one language"
                )


def test_the_site_builds():
    """End to end: all ten pages (five, twice) render through the real
    `Environment`.

    Also the only test that proves `url_for` and `is_active` still satisfy the
    signatures `sidebar_link` and `brand` call them with. A static site swaps
    those globals out, and the shell cannot tell.
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
                sheet=build.cheatsheet.for_lang(lang["code"]),
            )
            assert html.startswith("<!doctype html>")
            assert 'class="sidebar"' in html, "the shell's sidebar block went unfilled"
            assert page["title"] in html
            assert f'<html lang="{lang["html_lang"]}"' in html


def test_every_asset_link_is_relative_to_its_page():
    """GitHub Pages serves this site from a project subpath (`/fjkit/`, not
    `/`), and the Chinese pages sit one directory deeper than the English ones.

    An absolute `/assets/...` would 404 on Pages while working from a local
    server rooted at `docs/`, so the failure only shows up after publishing. The
    rule is therefore checked on the built files: every link a page makes is
    relative and resolves to a file next to it.
    """
    out = Path(__file__).resolve().parents[3] / "docs"
    if not (out / "index.html").exists():
        pytest.skip("the site has not been built in this checkout")

    names = ("index.html", "learn.html", "plugins.html", "components.html", "cheatsheet.html")
    pages = [out / name for name in names]
    pages += [out / "zh" / name for name in names]

    for page in pages:
        html = page.read_text(encoding="utf-8")
        for ref in re.findall(r'(?:href|src)="([^"]+)"', html):
            if ref.startswith(("http://", "https://", "#", "mailto:", "data:")):
                continue
            assert not ref.startswith("/"), f"{page.name} links to {ref}, which breaks under /fjkit/"
            # The fragment and the query are not part of the path.
            # `fjkit_static` stamps every asset with `?v=<mtime>` so a browser
            # cannot serve a stale stylesheet against current markup; a static
            # host ignores the query and serves the file, and so must this check.
            target = (page.parent / ref.split("#")[0].split("?")[0]).resolve()
            assert target.exists(), f"{page.relative_to(out)} links to {ref}, which is not there"
