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
| `fjkit` | The UI kit |
| `fjkit-admin` | A Django-style admin for SQLAlchemy models |
| `fjkit-charts` | Server-rendered Plotly charts |
| `fjkit-apidocs` | An API reference and console, in place of Swagger UI |
| `fjkit-lsp` | A language server that links routes, response models and templates |

## Built on

- [FastAPI](https://fastapi.tiangolo.com/) for routes and dependency injection
- [Jinja2](https://jinja.palletsprojects.com/) for templates
- [Basecoat](https://basecoatui.com/) for shadcn/ui-style components as plain CSS
- [htmx](https://htmx.org/) for swapping server-rendered HTML

The stylesheet is about 25 KB gzipped.

## Documentation

**[liweicheng00.github.io/fjkit](https://liweicheng00.github.io/fjkit/)** — every example on the site is rendered by the kit, and you can change macro parameters and see the result.

Rendering performance: [docs/jinja-performance.md](docs/jinja-performance.md).

## Status

Pre-release (`0.1.0.dev0`). Macro signatures can change until 1.0.

## License

MIT. See [LICENSE](LICENSE).
