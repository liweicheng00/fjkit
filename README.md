# fjkit

The UI layer for FastAPI. Pages, tables, forms, navigation, dark mode and htmx swaps, written as Jinja macros next to your routes.

There is no front-end build. The stylesheet is compiled when fjkit is released, so your app has no `package.json`, no `node_modules` and nothing to rebuild when you edit a template.

Three claims the kit is held to, and where each one is checked:

- An empty directory to a first page with navigation and dark mode: **5 minutes, 20 lines of Python, 0 build steps.** The 20 lines are below.
- A back-office page with a list, filters, pagination and an add/edit form: **one afternoon, no CSS, no JavaScript.** `examples/fjkit-demo` is that page, and it is also the kit's acceptance test.
- Your repository contains **no `package.json`, no `node_modules` and no Tailwind binary.** That holds because the class vocabulary is closed, and `fjkit check` fails the build when a template steps outside it.

## Install

```bash
uv add fjkit
```

## A page in two files

```python
from pathlib import Path

from fastapi import FastAPI
from fjkit import FjkitConfig, mount_fjkit, render
from pydantic import BaseModel

app = FastAPI()
mount_fjkit(app, FjkitConfig(template_dir=Path(__file__).parent / "templates"))


class Overview(BaseModel):
    done: int


@app.get("/")
@render("overview.html")
def overview() -> Overview:
    return Overview(done=18)
```

`mount_fjkit` serves the CSS and JavaScript and builds the Jinja environment. The handler returns a model, and `@render` passes its fields to the template. `@render` goes below `@app.get`.

`templates/overview.html`:

```jinja
{% extends "ui/shell.html" %}
{% from "ui/layout.html" import page_header, grid %}
{% from "ui/data.html" import stat %}

{% block content %}
  {{ page_header("Overview", "How the board is doing") }}
  {% call grid(cols=4) %}
    {{ stat("Done", done, tone="success", icon_name="check") }}
  {% endcall %}
{% endblock %}
```

The template has no CSS classes, no colours and no `<svg>`. Macros take named options such as `tone="success"`, so the shipped stylesheet covers every page. `fjkit check` fails the build if a template adds its own.

## What you get

- **Layout and components as macros**: `stack`, `row`, `grid`, `card`, `table`, `form` and more.
- **htmx on any macro**: pass `hx_get=`, `hx_target=` and so on as keywords.
- **One partial for the page and the swap**: the page embeds the partial that the htmx endpoint returns, so the two cannot drift.
- **A JSON API for free**: an htmx endpoint returns HTML to htmx and its model as JSON to any other caller, such as `curl`.
- **Rebranding in one file**: templates name a colour role (`primary`, `destructive`), never a hue.

## When not to use fjkit

- **You want React, Vue or Svelte.** fjkit renders on the server and has no client-side component model. Use them instead.
- **You want screens generated from your models.** fjkit never reads your schema, because a generated screen is right for a week and wrong afterwards. `fjkit-admin` is the separate distribution that does read it.
- **You want to write Tailwind utilities in your templates.** The vocabulary is closed and `fjkit check` fails the build. A layout that seems to need a utility is a missing macro parameter.
- **You need a component fjkit has not written.** Signatures are closed enumerations with no class-string escape, and before 1.0 they can change. `fjkit eject` copies a macro into your repository, but it is the escape hatch, not the road.
- **You need identity.** `fjkit.auth` moves a credential between a cookie and a store. It issues no users, no passwords and no roles.

[Why fjkit, and when not](https://liweicheng00.github.io/fjkit/why.html) is the long version: what the three usual approaches cost, and what this one gives up in exchange. The full anti-goals list with the reasoning behind each line is [CHARTER.md §2.4](CHARTER.md#24-what-fjkit-will-not-do); [§2.1](CHARTER.md#21-the-line) is the one rule they all come from — fjkit owns what the browser receives and sends back, never what your database contains.

## Try the demo

```bash
uv sync
uv run fastapi dev examples/fjkit-demo/app/main.py
```

Open <http://127.0.0.1:8000>.

## Packages

| Package | What it is |
|---|---|
| [`fjkit`](packages/fjkit) | The UI kit |
| [`fjkit-admin`](packages/fjkit-admin) | A Django-style admin for SQLAlchemy models |
| [`fjkit-charts`](packages/fjkit-charts) | Server-rendered Plotly charts |
| [`fjkit-apidocs`](packages/fjkit-apidocs) | An API reference and console, in place of Swagger UI |
| [`fjkit-lsp`](tools/fjkit-lsp) | A language server that links routes, response models and templates |

## Built on

- [FastAPI](https://fastapi.tiangolo.com/) for routes and dependency injection
- [Jinja2](https://jinja.palletsprojects.com/) for templates
- [Basecoat](https://basecoatui.com/) for shadcn/ui-style components as plain CSS
- [htmx](https://htmx.org/) for swapping server-rendered HTML

The stylesheet is about 25 KB gzipped.

## Documentation

**[liweicheng00.github.io/fjkit](https://liweicheng00.github.io/fjkit/)**, in English and 中文. Every example on the site is rendered by the kit.

| Page | Read it to |
|---|---|
| [Why fjkit](https://liweicheng00.github.io/fjkit/why.html) | decide whether to use it: what the alternatives cost, and what this one gives up in exchange |
| [Architecture](https://liweicheng00.github.io/fjkit/architecture.html) | see the five closed decisions as pictures before you commit to the shape |
| [Learn](https://liweicheng00.github.io/fjkit/learn.html) | wire an app, use htmx swaps, handle form errors, rebrand. Lessons 01–05 are the minimum. |
| [Components](https://liweicheng00.github.io/fjkit/components.html) | see every macro live, with the call that produced it |
| [Cheatsheet](https://liweicheng00.github.io/fjkit/cheatsheet.html) | look up a signature, a shell block or an htmx attribute |
| [Plugins](https://liweicheng00.github.io/fjkit/plugins.html) | add sign-in, flash messages, charts, an API console or the admin |

Rendering performance: [notes/jinja-performance.md](notes/jinja-performance.md). Why the kit is shaped this way — the scope, the closed decisions and the quality budgets — is [CHARTER.md](CHARTER.md).

## Status

0.4.1, on PyPI. Macro signatures can change before 1.0.

## License

MIT. See [LICENSE](LICENSE).
