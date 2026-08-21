# CLAUDE.md

**fjkit** is what this repository builds: the UI layer for FastAPI — pages,
tables, forms, navigation and htmx swaps, composed as Jinja macros in the same
codebase as the routes. It reaches that with **no front-end build step on the
user's side**, which is the constraint every rule below protects.
`examples/fjkit-demo` is the demo, and it is also the kit's acceptance test.

Toolchain is **uv only**. Never add `npm`, `package.json` or `node_modules` —
not to the kit, and not to the demo.

## Where things are

```
packages/fjkit/        the package — this is the product
  src/fjkit/           templating, mounting, config, icons, cli
  src/fjkit/templates/ui/   the component macros
  src/fjkit/static/    src/fjkit.css (tokens), dist/ (built), vendor/ (htmx, Basecoat)
  docs/                the docs-site source — workbench generator and templates
  tests/               component contracts, vocabulary, loader override
examples/fjkit-demo/        the demo app — a workspace member, depends on fjkit
  app/                 main.py, features/<name>/, templates/<name>/
  tests/               routes, htmx contract, parity, conventions
bench/                 render_bench.py — guards the performance claims
docs/                  the published site (3 pages × 2 languages, built) + the evaluations
CHARTER.md             mission, architecture decisions, roadmap, authority limits
```

## Commands

```bash
uv run fastapi dev examples/fjkit-demo/app/main.py    # the demo
uv run pytest                                    # kit suite + demo suite
uv run ruff check
uv run fjkit check examples/fjkit-demo/app/templates  # closed-vocabulary gate
uv run python bench/render_bench.py              # performance
```

Only when working on the kit itself:

```bash
uv sync --group build && uv run fjkit build-css        # rebuild dist/fjkit.css
uv run python packages/fjkit/scripts/vendor_ui.py      # re-download htmx/Basecoat
uv run python packages/fjkit/docs/workbench/build.py   # rebuild the docs site
```

The docs site is the documentation — there is no Markdown copy of it in the
repo. `docs/` at the root is a build artefact, so **rebuild it and commit the
result before every push** that touched `packages/fjkit/docs/workbench/`,
`src/fjkit/templates/ui/` or `static/src/fjkit.css`. `.githooks/pre-push`
enforces this; enable it once with `git config core.hooksPath .githooks`.

An app author runs none of the second group. That asymmetry is the product.

## Which document decides what

| Question | Authority |
|---|---|
| How do I build a page with fjkit? | `.claude/skills/fjkit/SKILL.md`, then <https://liweicheng00.github.io/fjkit/> |
| What does this macro accept? | its signature comment in `packages/fjkit/src/fjkit/templates/ui/*.html` |
| Should this feature exist? What is next? | `CHARTER.md` §8, §9 |
| What am I allowed to do without asking? | `CHARTER.md` §0, §11 |
| What did the benchmarks actually measure? | `docs/jinja-performance.md` |

Read the authority rather than restating it here. This file is loaded on every
turn, so it stays a map.

## Layer boundaries in the demo

| Layer | Owns | Must not contain |
|---|---|---|
| `routers/` | routes, `Depends`, status codes, template choice | business logic, DB queries |
| `services/` | business logic, transaction boundaries | `Request`/`Response`, template names |
| `schemas/` | wire contracts, domain→variant maps | a mirror of the DB table |
| `templates/` | markup | data reshaping, business rules |

Three kinds of template, three rules:

| Kind | Path | Extends the shell | Returned by a route |
|---|---|---|---|
| Page | `<feature>/page.html` | always | full GET |
| Partial | `<feature>/_*.html` | never | htmx swaps |
| Macros | `<feature>/macros.html`, `ui/*.html` | never | never |

1. A partial renders standalone. It declares its own imports and reads only
   what the router put in the context.
2. The page embeds the same partial the htmx endpoints return.
3. A repeated component is a macro, never `{% include %}` in a loop.

`examples/fjkit-demo/tests/test_conventions.py` enforces 1, 2 and the naming rules.

## Colour

Every colour is defined once, in
`packages/fjkit/src/fjkit/static/src/fjkit.css`. Templates name a **role**
(`variant="success"`, `bg-primary text-primary-foreground`), never a hue.
Status colours are deliberately not tied to `--primary`, because "green means
done" has to survive a rebrand. `fjkit check` fails the build on hex codes,
`rgb()`/`oklch()`, Tailwind palette hues and `text-white`/`text-black`.

The token table is that file itself; rebranding is covered on the site's Learn
page.

## Rendering

- `templates.page()` for normal responses. `templates.stream()` when the row
  count is user-controlled.
- Streaming must be buffered. Unbuffered is 65× slower over ASGI.
- A handler that renders should be `def`, not `async def`, so Starlette runs it
  in the threadpool.
- Every Jinja knob lives in `FjkitConfig`. Re-run `bench/render_bench.py` when
  a change is meant to be an optimisation.
