# fjkit documentation

**Build the interface where you build the routes.** fjkit is the UI layer
FastAPI does not ship: pages, tables, forms, navigation, dark mode and htmx
swaps, composed as Jinja macros in the same codebase as your handlers — with no
front-end toolchain on your side.

**Learn it by operating it:** the
[**published site**](https://liweicheng00.github.io/fjkit/) is three pages in
two languages — English at the root, 中文 under
[`zh/`](https://liweicheng00.github.io/fjkit/zh/) — two of which you can drive. Set macro parameters and watch the real output. Fire genuine htmx
requests and watch the swap land. Turn the brand knob and watch the page
repaint. Run the vocabulary checker on your own markup.

Rebuild it from this checkout with:

```bash
uv run python packages/fjkit/docs/workbench/build.py
```

Three pages and their shared assets, written to `docs/` at the repo root —
which is what GitHub Pages serves (*Settings → Pages → Deploy from a branch →
`main` / `docs`*):

| Output | Page | Covers |
|---|---|---|
| `docs/index.html` | Introduction | the landing page — what fjkit is, who it is for, five decisions, what ships in the wheel |
| `docs/learn.html` | Learn | wiring, the htmx exchange, hx-target/hx-swap/hx-trigger, partials, `hx-swap-oob`, `hx-indicator`/`hx-disabled-elt`, rebranding, `fjkit check` |
| `docs/components.html` | Components | every macro, live, with the Jinja call and the HTML it emits |
| `docs/assets/dist/`, `docs/assets/vendor/` | — | the default pack's `fjkit-vega.css`, htmx and Basecoat's JS, byte-identical to the wheel |
| `docs/assets/brand.css` | — | the site's own stylesheet — tokens, typography, and the gaps |
| `docs/zh/index.html`, `docs/zh/learn.html`, `docs/zh/components.html` | 中文 | the same three pages, translated — `templates/zh/`, one directory deeper, sharing every asset |

**Two languages, one skeleton.** `base.html`, `_parts.html`, the request
diagram and every `assets/*.js` file are shared; `templates/zh/` holds the three
translated pages and `build.py` holds the chrome strings (rail headings, the
footer, the diagram's labels). Each language is one `build_environment()` with
its own `static_url` — `assets` at the root, `../assets` from `zh/` — because
GitHub Pages serves the site from `/fjkit/`, where an absolute link leaves the
site. `test_docs_site.py` checks that on the built files: no link starts with
`/`, and every one of them resolves to a file that is actually there.

**The site is a fjkit app.** `templates/base.html` extends `ui/shell.html`, the
navigation is `sidebar` + `sidebar_link`, and the pages are built from
`page_header`, `section`, `card`, `table`, `grid` and `stack` — the same macros
`examples/fjkit-demo` calls. `fjkit check` runs over `templates/` in CI
(`tests/test_docs_site.py`) and it passes, so the site cannot show you a
component the package does not ship.

That makes it the kit's second acceptance test, and the harder one: a
documentation page reaches for shapes an admin never needs. What it cannot say
in the vocabulary is collected in PART 2 of `workbench/assets/brand.css`, each
block labelled with the macro that would remove it. **The length of part 2 is
the honest answer to "is the vocabulary closed?"** — today it is four, down from
seven: `code_block`, `tabs` and a vertical `button_group` are components now, so
their rules moved into `fjkit.css`.

Of the four left, one is deliberate (syntax highlighting — the kit renders code
as text and should never learn a language) and two are shapes only a docs page
wants. The fourth is the one that matters: the playground builds its controls in
the browser, so it cannot call `field_row`, and `fjkit check` reads templates and
never scripts. That is a missing capability and a hole in the gate, and the
second half is the more serious one.

Two knobs turn the app into a static site, both already on `FjkitConfig`:
`static_url="assets"` so `fjkit_static` resolves next to the page, and
`globals={"url_for": …, "is_active": …}` so route names still work without a
request. The shell is used unmodified.

**There is no prose copy of any of this in the repository.** The site is the
documentation, and `workbench/templates/` is its source. That is deliberate: a
Markdown page can describe a macro that the package stopped shipping, and a
rendered page cannot — every preview on the site is produced by the kit itself
at build time.

Offline, the authority is the source: `src/fjkit/templates/ui/*.html` opens
every macro with a signature comment, and `src/fjkit/static/src/fjkit.css`
holds the token table.

## The four contact points

Your app touches fjkit in exactly four places. Everything else is sealed inside
the package.

| Yours | Touches |
|---|---|
| `features/*/router.py` | imports `render` |
| `templates/base.html` | extends `ui/shell.html` |
| `templates/<feature>/*.html` | `{% from "ui/*.html" import … %}` |
| your own `brand.css` | overrides the `--primary` tokens |

All four are one-directional: your app depends on fjkit, and fjkit never
references your app.

## The promises, and what makes each one hold

| Promise | Mechanism |
|---|---|
| No build step on your side | Tailwind runs in fjkit's release pipeline. All eight `dist/fjkit-<pack>.css`, htmx and Basecoat's JS ship in the wheel |
| …which only works if | the class vocabulary is closed — layout is a component too, and `fjkit check` enforces it |
| Rebranding is one file | every colour is a token. Templates name a role, never a hue |
| A macro cannot be misused | signatures take closed enumerations and never a class string |
| Page and htmx swap cannot drift | one partial, embedded by the page and returned by the endpoints |

The diagrams behind these decisions are in `docs/architecture.md`, at the repo
root.

## Commands

```bash
uv run fastapi dev app/main.py       # no CSS watcher alongside it — there is nothing to rebuild
uv run fjkit check app/templates     # every class is part of the vocabulary
uv run fjkit eject <component>       # copy a component into your app to edit it
uv run pytest
```

Status: pre-release (0.1.0.dev0), under active development. Signatures are not
frozen until 1.0.
