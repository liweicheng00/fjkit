# fjkit-lsp

A language server that links the three things a fjkit page is made of: the
route (`@render("tasks/page.html", partial="tasks/_board.html")`), the response
model it returns (`-> BoardResponse`), and the templates.

What it answers:

| Cursor on | Go to definition | Find references | Hover |
|---|---|---|---|
| `tasks` in a template | `BoardResponse.tasks` in `schemas.py` | every `tasks` in the templates that model reaches | model, annotation, routes |
| `task.title` (loop var or macro parameter) | `Task.title` | every `x.title` where `x` is a `Task` | type of the chain head |
| `task_row` (imported macro) | the `{% macro %}` | every call, in every template | source template |
| `"tasks/_board.html"` (Jinja tag or Python string) | the file | `include`/`extends`/`import` tags and `@render` decorators | routes and parents |
| `"tasks_advance"` inside `url_for(...)` | the handler | every template naming the route | handler location |
| `url_for` | `env.globals["url_for"]` in `templating.py` | — | — |
| a field in a model class (Python) | — | its uses in templates | occurrence count |
| a model class name (Python) | — | the routes returning it | routes and templates |
| `"task-changed"` in an `hx-trigger` value, or in `subscribe(request, x, ["task-changed"])` | every `@render(…, hx_trigger=…)` raising it | every listener, and every emitter | which routes raise it, as `HX-Trigger` or `HX-Trigger-After-Swap`, via which constant |
| `CHANGED_EVENT` in Python, when its value is an event a route raises | — (Pyright's) | every template listening for it | the same |
| `hx-target="#board"` (attribute or macro kwarg) | the element with `id="board"` | every `hx-*` naming `#board` | where the id is |
| `id="board"` | — | every `hx-*` naming `#board` | how many |
| `hx-get="/tasks/7/advance"` — a literal URL | the route whose path it hits, router prefix included | the route | method, path template, handler |

Context is followed the way Jinja passes it: a route's model reaches its
template, whatever that template includes, and whatever it extends. Macro
parameters have no annotation, so their type is inferred from what the call
sites pass. Only code inside `{{ }}` / `{% %}` and outside string literals
counts as a reference, and a comment counts for nothing — a macro's signature
note quoting `hx_target="#board"` is not a target.

Model fields and classes have no *definition* on the Python side on purpose:
the cursor is on the definition already and Pyright answers it; a second copy
would only lengthen the editor's list. What the kit adds there is references.

Files under `tests/` are not indexed. A route in a test never ships.

## One repository, several applications

A template name is only unique inside one application's loader chain. This
repository has three `base.html` files — one per demo, one for the docs site —
so the index keeps a chain per application rather than a single name table,
mirroring the `ChoiceLoader` that `build_environment` assembles:

| Kind of root | Who sees it | Here |
|---|---|---|
| an application's own `templates/` | that application only | each demo, the docs workbench |
| a distribution's, under `src/` | every application, plugins before the kit | `fjkit-admin`, `fjkit-apidocs`, `fjkit-charts`, then `fjkit` |

Every lookup is made from the file that wrote the name, so `base.html` in a demo
page means that demo's, and `admin/page.html` means the one fjkit-admin ships.
`fjkit/ui/form.html` always means the kit's own copy, exactly as
`_ReservedNamespace` guarantees at runtime.

## In an editor

The client is the repository's own extension, `tools/fjkit-vscode` — plain
JavaScript on the VS Code API, no npm, packaged by a Python script:

```bash
uv sync                                          # puts the server in .venv
uv run python tools/fjkit-vscode/build.py        # dist/fjkit-vscode-<version>.vsix
code   --install-extension tools/fjkit-vscode/dist/fjkit-vscode-*.vsix
cursor --install-extension tools/fjkit-vscode/dist/fjkit-vscode-*.vsix
```

It attaches to `html`, `jinja-html`, `jinja` and `python`, so a `@render`
string opens its template and a model field finds its uses without leaving the
editor. [Its README](../fjkit-vscode/README.md) has the rest — how it finds
the server, and why by path.

Neovim, Helix, Zed and Emacs configure a language server themselves and need
no extension: point them at `.venv/bin/fjkit-lsp`.

## Command line

```bash
uv run fjkit-lsp index                              # the roots, and what was indexed
uv run fjkit-lsp where tasks/_board.html            # who renders / includes / imports it
uv run fjkit-lsp var tasks/_board.html tasks        # where a template identifier comes from
uv run fjkit-lsp at app/templates/tasks/macros.html 13 20   # definition + references at a cursor
```

Paths are relative to the current directory; run from the repository root. A
bare template name is read on the default chain, so pass the path instead when
two applications share the name:

```bash
uv run fjkit-lsp where examples/fjkit-demo/app/templates/base.html
```
