# fjkit

**Build the interface where you build the routes.** fjkit is the UI layer FastAPI
does not ship: pages, tables, forms, navigation, dark mode and htmx swaps,
composed as Jinja macros in the same codebase as your handlers.

Nothing here needs a front-end toolchain. The stylesheet is compiled when fjkit
is released, not when your app runs, so your repo has no `package.json`, no
`node_modules` and no Tailwind binary.

```python
from pathlib import Path

from fastapi import FastAPI
from fjkit import FjkitConfig, mount_fjkit

config = FjkitConfig(template_dir=Path(__file__).parent / "templates")

app = FastAPI()
mount_fjkit(app, config)
```

```jinja
{% extends "ui/shell.html" %}
{% from "ui/layout.html" import page_header, grid %}
{% from "ui/data.html" import stat %}

{% block content %}
  {{ page_header("Overview", "How the board is doing") }}
  {% call grid(cols=4) %}
    {{ stat("Total", 42, icon_name="list") }}
  {% endcall %}
{% endblock %}
```

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

Status: pre-release, under active development.
