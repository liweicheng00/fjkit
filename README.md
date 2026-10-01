# fjkit

The UI layer for FastAPI. Pages, tables, forms, navigation, dark mode and htmx swaps, written as Jinja macros next to your routes.

There is no front-end build. The stylesheet is compiled when fjkit is released, so your app has no `package.json`, no `node_modules` and nothing to rebuild when you edit a template.

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
| [Learn](https://liweicheng00.github.io/fjkit/learn.html) | wire an app, use htmx swaps, handle form errors, rebrand. Lessons 01–05 are the minimum. |
| [Components](https://liweicheng00.github.io/fjkit/components.html) | see every macro live, with the call that produced it |
| [Cheatsheet](https://liweicheng00.github.io/fjkit/cheatsheet.html) | look up a signature, a shell block or an htmx attribute |
| [Plugins](https://liweicheng00.github.io/fjkit/plugins.html) | add sign-in, flash messages, charts, an API console or the admin |

Rendering performance: [docs/jinja-performance.md](docs/jinja-performance.md).

## Status

0.1.0, on PyPI. Macro signatures can change before 1.0.

## License

MIT. See [LICENSE](LICENSE).
