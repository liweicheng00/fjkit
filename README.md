# fjkit

**Build the interface where you build the routes.** fjkit is the UI layer FastAPI
does not ship: pages, tables, forms, navigation, dark mode and htmx swaps,
composed as Jinja macros in the same codebase as your handlers.

From an empty directory to a page with navigation and dark mode is about twenty
lines of Python. Everything a back-end developer needs to put up a real page is
here, and nothing that needs a front-end toolchain: the stylesheet is compiled
when fjkit is released, not when your app runs, so there is no `package.json`, no
`node_modules`, no Tailwind binary, and nothing to rebuild when you edit a
template.

```python
from fastapi import FastAPI
from fjkit import FjkitConfig, mount_fjkit

config = FjkitConfig(template_dir=APP_DIR / "templates")

app = FastAPI()
mount_fjkit(app, config)              # serves fjkit.css, htmx and Basecoat's JS,
                                      # and builds the Jinja Environment
```

```jinja
{% extends "ui/shell.html" %}
{% from "ui/layout.html" import page_header, grid %}
{% from "ui/data.html" import stat %}

{% block content %}
  {{ page_header("Overview", "How the board is doing") }}
  {% call grid(cols=4) %}
    {{ stat("Done", 18, tone="success", icon_name="check") }}
  {% endcall %}
{% endblock %}
```

Note what the template does not contain: no utility classes, no colour, no
`<svg>`. That is not a style preference — it is what makes the no-build promise
hold, and `fjkit check` enforces it.

## Learn it by operating it

**[The published site](https://liweicheng00.github.io/fjkit/)** is three pages —
an introduction, then Learn and Components, both of which you can drive. Set
macro parameters and watch the real output. Fire genuine htmx requests and watch
the swap land. Turn the brand knob and watch the page repaint. Every preview is
rendered by the kit itself, so the site cannot document a macro the package does
not ship — and the site is itself a fjkit app that passes `fjkit check`.

## Try the demo

```bash
uv sync
uv run fastapi dev examples/board/app/main.py
```

<http://127.0.0.1:8000> — an overview page, a task board with htmx swaps, and a
streamed 20,000-row report. There is no CSS build to run and no watcher to keep
open.

## The promises, and what makes each one hold

| Promise | Mechanism |
|---|---|
| A page is a handful of macro calls | components *and* layout ship as macros — `stack`, `row`, `grid`, `split`, `card`, `table`, `form` |
| It looks right without a designer | Basecoat's shadcn-derived components and token vocabulary, dark mode included |
| Interactivity without JavaScript | any macro forwards `hx_*` keywords, so htmx never appears in a component definition |
| Rebranding is one file | every colour is a token. Templates name a role, never a hue. |
| A macro cannot be misused | signatures take closed enumerations and never a class string |
| Page and htmx swap cannot drift | one partial, embedded by the page and returned by the endpoints |
| Every htmx endpoint is already a JSON API | a handler returns a model; `@render` serialises it when no browser is waiting for markup, so a swap route answers `curl` with its `response_model` — no second route, no serialiser |
| …and none of it needs a build step | Tailwind runs in fjkit's release pipeline. `dist/fjkit.css`, htmx and Basecoat's JS ship inside the wheel — which only holds because the class vocabulary is closed, and `fjkit check` enforces that. |

## Why this stack

| Layer | Choice | Why this one |
|---|---|---|
| HTTP | FastAPI | `Depends` gives a clean seam between router and service. |
| Templates | Jinja2 | Compiles to Python, so the cost model is knowable — see the benchmark. |
| Components | Basecoat | shadcn/ui's design and token vocabulary as plain CSS classes. Most of it needs no JavaScript. |
| Interactivity | htmx | The server already renders HTML. htmx swaps fragments of it, so there is no client state to keep in sync. |

**Why Basecoat over the alternatives.** daisyUI would also work; Basecoat wins
on token names that map to colour *roles* (`--primary`, `--muted-foreground`,
`--destructive`) rather than hues. Bootstrap's theming is a Sass rebuild, while
Basecoat retints from CSS custom properties, which keeps the brand knob a
runtime variable. Plain Tailwind pushes 15+ classes into every button, and
markup length is the thing you render on every request. A React or Vue kit means
a build step, a hydration story, and two sources of truth for one screen.

Cost: `fjkit.css` is 225 KB raw, **23.2 KB gzip**, against a 28 KB budget that
the build enforces. Basecoat's component layer is a single stylesheet and cannot
be tree-shaken, which is the trade for getting the full component set.

## Documentation

**[Docs](https://liweicheng00.github.io/fjkit/)**

## Performance, in one paragraph

Rendering is rarely the problem. The three things that are: **template
compilation on a cold process** (102 ms → 4.3 ms with the bytecode cache),
**peak memory on large pages** (22 MB → 16 KB by streaming), and **where the
render runs** (a heavy `async def` handler freezes the event loop for the
duration — 140 ms in the benchmark). Everything else people tune —
`auto_reload`, `StrictUndefined`, `with context` — does not measure at all: the
differences sit inside run-to-run noise and change sign between runs. Full
numbers and method: [docs/jinja-performance.md](docs/jinja-performance.md).

## Status

Pre-release (0.1.0.dev0), not yet on PyPI. Macro signatures are not frozen until
1.0. The roadmap and the rules this project holds itself to are in
[CHARTER.md](CHARTER.md).
