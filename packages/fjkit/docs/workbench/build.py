"""Build the documentation site — four pages in two languages, and the site is
a fjkit app.

    uv run python packages/fjkit/docs/workbench/build.py

Output, all under `docs/` at the repo root, which is what GitHub Pages serves:

    index.html       Introduction — what the kit is, who it is for, what it is not
    learn.html       Learn        — the narrative: wiring, htmx, theming, the gate
    plugins.html     Plugins      — the extension seam, and the session plugin
    components.html  Components   — every macro, live, with the code that made it
    zh/              the same four pages in Chinese, from `templates/zh/`
    assets/dist/     fjkit.css, exactly as the wheel ships it
    assets/vendor/   htmx and Basecoat's JS, exactly as the wheel ships them
    assets/brand/    the brand mark, exactly as the wheel ships it
    assets/          the site's own brand.css and page scripts — one copy for
                     both languages, because only the prose is translated

**Every link is relative.** GitHub Pages serves this from a project subpath
(`https://…/fjkit/`), so an absolute `/assets/fjkit.css` would 404 there while
working perfectly from a local server rooted at `docs/`. The English pages name
`assets`, the Chinese pages in `zh/` name `../assets`, and `url_for` returns the
hop between the two builds rather than a path from the root.

**The site is built the way the docs tell you to build one.** `base.html`
extends `ui/shell.html`; the navigation is `sidebar` + `sidebar_link`; the
sections are `page_header`, `section`, `card`, `table`, `grid` and `stack`. No
utility classes, no hand-written chrome — `tests/test_docs_site.py` runs
`fjkit check` over `templates/` and fails the build if any appears. When the
kit cannot say something, that shows up here first, which is the point of
eating your own cooking.

Two adaptations turn a server-rendered app into a static site, and both use
knobs `FjkitConfig` already has rather than a fork of the shell:

* `static_url="assets"` — so `fjkit_static('dist/fjkit-<pack>.css')` resolves to a
  path next to the page instead of to a mounted route. The static tree is
  copied under `assets/` with the same shape `mount_fjkit()` serves.
* `globals={"url_for": …, "is_active": …}` — the kit's versions call
  `request.url_for`, and a build has no request. These take the same
  `(request, name)` signature and read `request.route`, which is a plain object
  the page's context supplies. Route *names* stay the currency, so `nav_links`
  and `sidebar_link` work unmodified.

Everything else is the package: the shell's `<head>`, its theme flash-guard,
Basecoat's JS (which initialises the sidebar, the tab strips and the range
sliders on these pages), and every component preview — all rendered by
`build_environment()`. A broken kit is a broken docs build.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from fjkit import FjkitConfig, build_environment
from fjkit.vendored import DEFAULT_STYLE

HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parents[1] / "src" / "fjkit"
REPO = HERE.parents[3]

TEMPLATES = HERE / "templates"
ASSETS = HERE / "assets"
DATA = HERE / "data.json"

STATIC = PACKAGE / "static"
#: The docs site is one build of one style pack — the default, so what a
#: reader sees is what an app gets before it touches `FjkitConfig.style`.
DOCS_STYLE = DEFAULT_STYLE
CSS = STATIC / "dist" / f"fjkit-{DOCS_STYLE}.css"
HTMX = STATIC / "vendor" / "htmx" / "htmx.min.js"
BASECOAT = STATIC / "vendor" / "basecoat" / "js" / "all.min.js"
MARK = STATIC / "brand" / "torii-bolt.png"

OUT = REPO / "docs"
OUT_ASSETS = OUT / "assets"

DEMO = REPO / "examples" / "board"

#: The three pages, in reading order. Both the sidebar and `url_for` are built
#: from this, so a page added here appears in the navigation of the others and
#: becomes addressable by name without touching a template. The first entry is
#: `index.html`, because that is what GitHub Pages serves to someone arriving
#: with no idea what this is.
#:
#: `en` and `zh` carry only what differs between the two builds — the label in
#: the rail, the <title>, the meta description. Everything structural (route,
#: file name, icon) is shared, so the two languages cannot drift into different
#: navigations.
PAGES = [
    {
        "route": "introduction",
        "file": "index.html",
        "icon": "book-open",
        "en": {
            "label": "Introduction",
            "title": "fjkit — a fast UI for FastAPI",
            "description": (
                "fjkit integrates Jinja, Tailwind CSS and shadcn-style components with FastAPI: pages, "
                "tables, forms, navigation and htmx swaps as Jinja macros, with no build step on your side."
            ),
        },
        "zh": {
            "label": "簡介",
            "title": "fjkit — 給 FastAPI 的快速 UI",
            "description": (
                "fjkit 把 Jinja、Tailwind CSS 與 shadcn 風格元件整合給 FastAPI 用：頁面、表格、表單、"
                "導覽與 htmx 局部更新全部是 Jinja macro，而且你這端零建置。"
            ),
        },
    },
    {
        "route": "learn",
        "file": "learn.html",
        "icon": "sparkle",
        "en": {
            "label": "Learn",
            "title": "Learn fjkit",
            "description": (
                "Build a FastAPI interface without a front-end toolchain: how the kit is wired, what "
                "htmx actually sends, a brand knob that repaints the page, and the vocabulary checker."
            ),
        },
        "zh": {
            "label": "上手",
            "title": "學會 fjkit",
            "description": (
                "不碰前端工具鏈也做得出 FastAPI 介面：kit 怎麼接、htmx 實際送出什麼、"
                "一拉就重新上色的品牌旋鈕，以及那支詞彙表檢查工具。"
            ),
        },
    },
    {
        "route": "plugins",
        "file": "plugins.html",
        "icon": "puzzle",
        "en": {
            "label": "Plugins",
            "title": "fjkit plugins",
            "description": (
                "Add middleware, an exception handler or a value every template gets, in one object "
                "registered in one place — and the session plugin that was the first to need it."
            ),
        },
        "zh": {
            "label": "外掛",
            "title": "fjkit 外掛",
            "description": (
                "用一個物件、一個註冊點，加上 middleware、exception handler，或每個模板都拿得到的值"
                "——以及第一個需要它的 session 外掛。"
            ),
        },
    },
    {
        "route": "components",
        "file": "components.html",
        "icon": "list",
        "en": {
            "label": "Components",
            "title": "fjkit components",
            "description": (
                "Every fjkit macro with a live preview, the Jinja call that produced it and the HTML "
                "it emits — rendered by the kit itself, so a signature here cannot drift from the "
                "package."
            ),
        },
        "zh": {
            "label": "元件",
            "title": "fjkit 元件",
            "description": (
                "每一個 fjkit macro 都有實際渲染的預覽、產生它的那行 Jinja，以及吐出來的 HTML——"
                "全部由 kit 自己渲染，所以這裡的簽名不可能跟套件對不上。"
            ),
        },
    },
]

ROUTES = {page["route"]: page["file"] for page in PAGES}

#: The two builds. `dir` is where the pages land under `docs/` and `static` is
#: what `fjkit_static` prefixes — one level up for the pages in `zh/`, because
#: GitHub Pages serves plain files and every link on this site is relative.
#: `templates` is the directory the page templates are read from, so English
#: and Chinese share `base.html`, `_parts.html` and every `ui/` macro, and
#: differ only in the prose.
LANGS = [
    {
        "code": "en",
        "dir": "",
        "html_lang": "en",
        "static": "assets",
        "templates": "",
        "label": "English",
        "other": "zh",
    },
    {
        "code": "zh",
        "dir": "zh",
        "html_lang": "zh-Hant",
        "static": "../assets",
        "templates": "zh/",
        "label": "中文",
        "other": "en",
    },
]

LANG_BY_CODE = {lang["code"]: lang for lang in LANGS}

#: The chrome around the prose: rail headings, the footer, and the label on the
#: link to the other language. A page template never writes these, so a new
#: page is translated by translating one file.
STRINGS = {
    "en": {
        "sidebar_label": "Documentation",
        "pages_group": "Documentation",
        "sections_group": "On this page",
        "language_group": "Language",
        "other_language": "中文",
        "footer_source": "source and issues",
        #: Three fragments rather than one string with placeholders: the two
        #: gaps are filled with `kbd()`, which yields Markup, and splitting the
        #: sentence keeps the template free of `|safe`.
        #: The request diagram's own labels. One SVG, two languages: the
        #: geometry has no business being copied for a translation.
        "diagram": {
            "alt": (
                "A browser sends POST /tasks with HX-Request headers; the FastAPI route calls the "
                "service, renders the _board.html partial, and returns an HTML fragment, which htmx "
                "swaps into the element named by hx-target."
            ),
            "browser": "BROWSER",
            "trigger": "the trigger — a click",
            "target_1": "hx-target — the element",
            "target_2": "that gets replaced",
            "body": "title=Ship+it (form body)",
            "service": "service — the real work",
            "partial": "the same partial the page embeds",
            "response": '<div id="board">…</div> — a fragment, not a page',
            "swap": "swap: outerHTML",
        },
        "footer_note": [
            "This site is a fjkit app: it extends ",
            " and passes ",
            ", so it cannot show you a component the package does not ship.",
        ],
    },
    "zh": {
        "sidebar_label": "文件",
        "pages_group": "文件",
        "sections_group": "本頁章節",
        "language_group": "語言",
        "other_language": "English",
        "footer_source": "原始碼與 issues",
        "diagram": {
            "alt": (
                "瀏覽器帶著 HX-Request 標頭送出 POST /tasks；FastAPI 的路由呼叫 service，"
                "渲染 _board.html 這份 partial，回傳一段 HTML fragment，htmx 再把它換進 "
                "hx-target 指名的那個元素裡。"
            ),
            "browser": "瀏覽器",
            "trigger": "觸發——一次點擊",
            "target_1": "hx-target——會被",
            "target_2": "換掉的那個元素",
            "body": "title=Ship+it（表單內容）",
            "service": "service——真正做事的地方",
            "partial": "頁面 include 的同一份 partial",
            "response": '<div id="board">…</div>——一段 fragment，不是一頁',
            "swap": "swap: outerHTML",
        },
        "footer_note": [
            "這個站本身就是一支 fjkit app：它 extends ",
            "，而且通過 ",
            "——所以它不可能展示套件裡沒有的元件。",
        ],
    },
}

#: Lesson 06 ("No HX-Request") quotes one route answering twice. Captured from
#: the demo — `GET /tasks/board?status=doing`, with and without the header —
#: rather than replayed during the build: the seeded rows carry timestamps, so a
#: live capture would rewrite `docs/` on every run and make the built site
#: unreviewable in a diff. `test_docs_site.py` checks that the two routes quoted
#: here are still the ones the demo declares.
NEGOTIATION = {
    "route": """\
@router.get("/tasks", name="tasks_page")
@render("tasks/page.html", partial="tasks/_board.html")
def tasks_page(service: ServiceDep, status: Status | None = None) -> BoardResponse:
    # A page route: it names a page and a partial, so it always has markup
    # waiting. A navigation gets the page; htmx gets the board.
    return _board(service, status)


@router.get("/tasks/board", name="tasks_board")
@render("tasks/_board.html")
def tasks_board(service: ServiceDep, status: Status | None = None) -> BoardResponse:
    # A fragment route: it names only a partial. htmx gets the board, and
    # anyone else gets BoardResponse as JSON — the API, at no extra cost.
    return _board(service, status)""",
    "json": """\
$ curl -s localhost:8000/tasks/board?status=doing

content-type: application/json
vary: HX-Request

{
  "tasks": [
    {
      "id": 4,
      "title": "Turn off auto_reload in the prod image",
      "status": "doing",
      "priority": "normal",
      "owner": "kai",
      "created_at": "2026-08-18T19:38:42.562805Z",
      "status_variant": "info",
      "priority_variant": "secondary"
    }
  ],
  "stats": {"total": 8, "todo": 4, "doing": 2, "done": 2, "done_pct": 25},
  "owners": ["kai", "mei"],
  "active_status": "doing",
  "filter_query": "?status=doing"
}""",
    "html": """\
$ curl -s -H 'HX-Request: true' localhost:8000/tasks/board?status=doing

content-type: text/html; charset=utf-8
vary: HX-Request

<div id="board">
  <div class="grid gap-6 lg:grid-cols-[1fr_19rem]">
    <form class="card" hx-post="/tasks" hx-target="#board" hx-swap="outerHTML">
      ...
    </form>
    <table class="table">
      <tr><td>Turn off auto_reload in the prod image</td>
          <td><span class="badge" data-variant="info">Doing</span></td>
      ...
    </table>
  </div>
</div>""",
}

#: Copied preserving the path `mount_fjkit()` serves them under, so `fjkit_static`
#: resolves the same string in the shell whether it is running in an app or
#: being written to disk here.
VENDORED = [
    (CSS, f"dist/fjkit-{DOCS_STYLE}.css", "uv run fjkit build-css"),
    (HTMX, "vendor/htmx/htmx.min.js", "uv run python packages/fjkit/scripts/vendor_ui.py"),
    (BASECOAT, "vendor/basecoat/js/all.min.js", "uv run python packages/fjkit/scripts/vendor_ui.py"),
    (MARK, "brand/torii-bolt.png", "git restore packages/fjkit/src/fjkit/static/brand/torii-bolt.png"),
]


def url_for(request, name: str, /, **path_params) -> str:
    """Static-site stand-in for the kit's `url_for`.

    Same signature, so `nav_links`, `sidebar_link` and `brand` are called
    exactly as an app calls them. A name may carry a fragment — `learn#wiring`
    — which is how the in-page rail addresses a section without a second
    mechanism, and it may carry a language — `zh:learn` — which is how the
    language switch addresses the same page in the other build.

    Every href this returns is **relative to the page being written**, because
    GitHub Pages serves these files from a project subpath
    (`/fjkit/`, not `/`) and an absolute `/learn.html` would leave the site.
    """
    lang_code, _, rest = name.rpartition(":")
    route, _, fragment = rest.partition("#")
    here = getattr(request, "lang", "en")
    there = lang_code or here
    if route not in ROUTES:
        raise KeyError(f"unknown docs route {route!r} (have: {', '.join(sorted(ROUTES))})")
    if there not in LANG_BY_CODE:
        raise KeyError(f"unknown docs language {there!r} (have: {', '.join(sorted(LANG_BY_CODE))})")
    # "" between two pages of one language, "zh/" going down into the Chinese
    # build, "../" coming back up out of it.
    if there == here:
        prefix = ""
    elif LANG_BY_CODE[here]["dir"]:
        prefix = "../" + (LANG_BY_CODE[there]["dir"] + "/" if LANG_BY_CODE[there]["dir"] else "")
    else:
        prefix = LANG_BY_CODE[there]["dir"] + "/"
    return prefix + ROUTES[route] + (f"#{fragment}" if fragment else "")


def is_active(request, name: str) -> bool:
    """True for the page being rendered. Section anchors are never active at
    build time — the scroll-spy in common.js owns that, because which section
    you are looking at is not something a static file can know. Neither is the
    link to the other language: it always points somewhere you are not."""
    if "#" in name or ":" in name:
        return False
    return getattr(request, "route", None) == name


def build() -> int:
    for path, _, hint in VENDORED:
        if not path.exists():
            print(f"missing {path}\nGenerate it first:  {hint}", file=sys.stderr)
            return 2

    # Renders every component preview through the real Environment. A subprocess
    # so a failure in it is a failure here, with its own traceback.
    result = subprocess.run([sys.executable, str(HERE / "build_data.py")])
    if result.returncode != 0:
        return result.returncode

    OUT_ASSETS.mkdir(parents=True, exist_ok=True)

    for path, rel, _ in VENDORED:
        target = OUT_ASSETS / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    for path in sorted(ASSETS.iterdir()):
        if path.is_file():
            shutil.copyfile(path, OUT_ASSETS / path.name)

    # The previews as a script rather than a fetch()ed .json: a page opened from
    # the filesystem cannot fetch a sibling file, and the docs should survive
    # being downloaded and read offline.
    data = json.dumps(json.loads(DATA.read_text(encoding="utf-8")), ensure_ascii=False, separators=(",", ":"))
    (OUT_ASSETS / "data.js").write_text(f"const DATA = {data};\n", encoding="utf-8")

    written = []
    for lang in LANGS:
        # One Environment per language, because `static_url` is the only thing
        # that differs and it is bound into `fjkit_static` when the Environment
        # is built. The pages in `zh/` sit one directory deeper, so every asset
        # they name has to climb back out.
        env = build_environment(
            FjkitConfig(
                template_dir=TEMPLATES,
                static_url=lang["static"],
                # Explicit, so the pack the shell links to and the file copied
                # into `assets/dist/` are the same one word.
                style=DOCS_STYLE,
                auto_reload=False,
                globals={"url_for": url_for, "is_active": is_active},
            )
        )
        out_dir = OUT / lang["dir"] if lang["dir"] else OUT
        out_dir.mkdir(parents=True, exist_ok=True)
        strings = STRINGS[lang["code"]]

        for page in PAGES:
            # The language's own label, title and description merged over the
            # shared route data, so a template says `page.title` either way.
            merged = {k: v for k, v in page.items() if k not in LANG_BY_CODE} | page[lang["code"]]
            html = env.get_template(f"{lang['templates']}{page['route']}.html").render(
                # Stands in for Starlette's Request. The macros only ever hand
                # it back to `url_for`/`is_active`, so a route name and the
                # language being written are all it needs.
                request=SimpleNamespace(route=page["route"], lang=lang["code"]),
                pages=[{k: v for k, v in p.items() if k not in LANG_BY_CODE} | p[lang["code"]] for p in PAGES],
                page=merged,
                lang=lang,
                t=strings,
                wire=NEGOTIATION,
            )
            out = out_dir / page["file"]
            out.write_text(html, encoding="utf-8")
            written.append(out)

    for out in written:
        print(f"{out.relative_to(REPO)}  {out.stat().st_size:,} bytes")
    total = sum(p.stat().st_size for p in OUT_ASSETS.rglob("*") if p.is_file())
    print(f"docs/assets/  {total:,} bytes in {sum(1 for p in OUT_ASSETS.rglob('*') if p.is_file())} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(build())
