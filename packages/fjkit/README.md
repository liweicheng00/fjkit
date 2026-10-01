# fjkit

fjkit is the UI layer FastAPI does not ship: pages, tables, forms, navigation,
dark mode and htmx swaps, composed as Jinja macros in the same codebase as your
handlers.

**Your app has no front-end build step.** The stylesheet is compiled when fjkit
is released, not when your app runs, so your repo has no `package.json`, no
`node_modules` and no Tailwind binary. Every other rule in fjkit protects that
one.

## Install

Requires Python 3.13+. The runtime dependencies are `fastapi`, `jinja2` and
`pydantic`, and `fastapi` already requires `pydantic`.

```bash
uv add fjkit
```

## A working page

`app/main.py`:

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

`app/templates/overview.html`:

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

Run `uv run fastapi dev app/main.py` and open <http://127.0.0.1:8000>.
`@render` goes below `@app.get` and passes the returned model's fields to the
template.

## Rebranding

One knob, plain CSS, no build:

```css
/* your own stylesheet, loaded after fjkit's */
:root { --primary: oklch(0.55 0.2 145); --primary-foreground: oklch(0.99 0 0); }
```

## One handler, two wire formats

A handler returns a model, not markup. `@render` picks the format from whether
the caller has markup waiting, so a fragment route is the app's JSON API
without a second route:

```console
$ curl -s localhost:8000/tasks/board
{"tasks": [...], "stats": {"total": 8, "done_pct": 25}}

$ curl -s -H 'HX-Request: true' localhost:8000/tasks/board
<div id="board">...</div>
```

The return annotation describes both, so FastAPI has already put the JSON in
`/docs`. `mode="html"` or `mode="json"` on the decorator forces one.

## Checking your templates

fjkit's class vocabulary is closed — apps compose macros rather than writing
utility classes. That is what makes the no-build promise hold, and it is
enforceable:

```bash
uv run fjkit check app/templates
```

## Documentation

**[Docs](https://liweicheng00.github.io/fjkit/)**

Status: 0.1.0. Macro signatures can change before 1.0.

## License

MIT. See [LICENSE](LICENSE).
