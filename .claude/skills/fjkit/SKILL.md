---
name: fjkit
description: >
  fjkit — the FastAPI + Jinja2 + Basecoat + htmx UI kit in packages/fjkit.
  Use this skill for these tasks:
  build or change a page, partial, form, table or navigation in a fjkit app.
  Style, lay out or colour a template. Add an icon.
  Fix a violation reported by `fjkit check`. Find why a class has no effect.
  Wire an htmx swap. Show a validation error, or a toast. Rebrand, or change a
  theme token.
  Add or change a component inside fjkit itself.
  也適用於中文情境：「加一個頁面／表單／表格」「這裡要排版」「換品牌色」
  「htmx 局部刷新」「fjkit check 沒過」「表單錯誤要顯示」「加一個 fjkit 元件」。
---

# fjkit

fjkit ships a stylesheet compiled at **release** time. An app that uses it has no
Tailwind, no `package.json`, and nothing to rebuild after editing a template.
The promise holds only while app templates stay inside the closed vocabulary.
Every other rule here serves that one.

The prose documentation is the published site,
<https://liweicheng00.github.io/fjkit/>, and it is generated — there is no
Markdown copy of it in the repository. In the repo the authority is the source,
which is the better authority anyway: it cannot describe a macro the package
stopped shipping.

**Read the macro before you call it.** Each file in
`packages/fjkit/src/fjkit/templates/ui/` opens every macro with a signature
comment carrying its closed enumerations. A guessed parameter does not fail. It
renders wrong markup silently.

| Task | Where it is decided |
|---|---|
| macro signatures, shell blocks, closed enumerations | `src/fjkit/templates/ui/*.html` |
| template globals, `page()` vs `stream()`, config knobs | `src/fjkit/templating.py`, `config.py`, `rendering.py` |
| partials, swaps, forms, filter bars | `examples/fjkit-demo/app/features/*/` — the worked example |
| validation errors, toasts, the 500 page | `src/fjkit/errors.py`, `forms.py`, `messages.py` |
| tokens, rebranding, dark mode | `src/fjkit/static/src/fjkit.css`, `src/fjkit/styles.py` |
| a blocked class, `eject`, building the CSS | `src/fjkit/cli/` |
| what the benchmarks measured | `docs/jinja-performance.md` |

`examples/fjkit-demo` is the acceptance test, so a pattern that appears there is a
pattern the kit supports. Read it before inventing one.

## Non-negotiables

- **Compose macros. Arrangement is a macro too.** `stack` `row` `grid` `split`
  `section` `page_header` `divider` are why an app template contains no
  `class="flex gap-4"`. When a layout seems to need a utility, the missing thing
  is a macro parameter. Add that parameter to `ui/*.html`.
- **Name a role, never a hue.** `variant="success"`, `tone="muted"`,
  `bg-primary text-primary-foreground`. Every colour is a token defined in
  `packages/fjkit/src/fjkit/static/src/fjkit.css`.
- **Write classes verbatim.** Tailwind finds classes when it scans source text.
  A class built by interpolation (`text-{{ tone }}`) is therefore absent from the
  stylesheet. Map through a closed lookup instead. Its values must appear
  literally in the file, as they do in every fjkit macro.
- **Extend Basecoat's attribute API.** `data-variant="success"` on the existing
  class, never a parallel `badge-success`.
- **Templates print what they are handed.** Build option lists, variant maps and
  query strings in the router (`STATUS_FILTERS`, `status_variant`, `urlencode`),
  not in Jinja.
- **Handlers that render are `def`, not `async def`** — rendering is CPU-bound,
  and Starlette runs `def` handlers in the threadpool.

## Building a feature

1. **Router** (`app/features/<name>/router.py`) — routes, `Depends`, status
   codes, template choice. A handler returns its response model; `@render`
   names the template, **below** `@router.get` and never above it. Business
   logic goes to `service.py`. The response model, wire contracts and
   domain→variant maps go to `schemas.py`.

   ```python
   @router.get("/tasks", name="tasks_page")
   @render("tasks/page.html", partial="tasks/_board.html")
   def tasks_page(service: ServiceDep, status: Status | None = None) -> BoardResponse:
       return board(service, status)
   ```

   The return annotation is the contract for both representations: FastAPI
   infers `response_model` from it, and `@render` spreads the same model into
   the template context. A view value the page shows — a badge variant, a
   percentage — belongs on the model as `@computed_field`, so it reaches the
   JSON too instead of existing only in Jinja.
2. **Partial** (`app/templates/<name>/_*.html`) — extends nothing. It declares
   its own imports. It reads only what the router put in the context. It wraps
   itself in the element the swap replaces (`<div id="board">`).
3. **Page** (`app/templates/<name>/page.html`) — extends `base.html` and sets
   `{% block title %}`. It includes that same partial. Each fragment then has one
   definition, so the page and the swap cannot drift.
4. **htmx endpoints** return the same partial via `@render("<name>/_board.html")`
   — a partial is not a special response type. A page that also answers swaps at
   its own URL takes `partial=` instead of a second route.
5. **Repeated rows** become a macro in `<name>/macros.html` taking `request` as a
   parameter, called inside the caller's loop.
6. **A form that can be rejected** needs nothing at all to behave. Declare the
   model in the handler's signature and stop:

   ```python
   @render("tasks/_board.html")
   def create_task(service: ServiceDep, payload: Annotated[TaskCreate, Form()]) -> BoardResponse:
   ```

   A rejected submit is FastAPI's own 422 — the list of fields and messages it
   always wrote — and the form that is still on the page draws it: the shell
   loads `js/errors.js`, which writes each message under the control named in
   its `loc` and leaves everything the person typed in place. No `invalid=`
   template, no context to rebuild, no `values` to echo back, no retarget. The
   template is one form, written once, with `value=task.title` and nothing
   about errors in it. A plain `<form method="post">` with no `target=` is the
   one case that gets a document instead — `errors/page.html`, through your
   shell — because the browser has already left the page.

   `Form()` fields or a whole model, urlencoded or `form(encoding="json")`:
   the reply is the same shape either way, and a nested body is named the way
   an HTML form would post it — `{"items": [{"title": …}]}` fails as
   `items.0.title`. A JSON form's page has to load the extension —
   `{% block scripts %}{{ form_scripts() }}{% endblock %}` — and needs a
   `target`, because only an htmx submit can carry JSON.

   Two rules, and each is a trap when broken:

   - **The model goes in the signature, not in the body.** `TaskCreate(**form)`
     inside a handler raises the same error one layer too late, where it is
     the shape of a bug — `Task(**row)` failing in a service — and is treated
     as one: it travels, and lands as a 500. fjkit does not guess which it was.
   - **A control's `name` is the field's `loc`.** That is how the script finds
     it; a field posted under one name and declared under another is an error
     the script can only raise as a toast. Same for a control that has no
     `<p>` to write under — `select_menu` — which is why its options and its
     type are one enum: a value the form never offered cannot be picked.

   Raise a message of your own with `messages.add(request, "Saved",
   category="success")`. It goes into the page's toaster on a full render and
   out as `HX-Trigger` on a swap; the caller never picks. Use `FlashPlugin`
   **only** for a message that has to survive a redirect — that is the one
   thing `messages` cannot do, and the only reason the plugin exists.

## Verify before reporting done

```bash
uv run fjkit check app/templates    # every class is in the vocabulary
uv run pytest                       # app suite + fjkit's own
uv run ruff check
```

**A green suite is not the whole check.** Tests assert on what the server sent;
several of the ways this kit breaks happen after the browser has it — a toast
that renders empty, an input reading `None`, a class the stylesheet does not
contain. Open the page for anything that changes what a form or a message
looks like.

A class blocked by `fjkit check` is information, not an obstacle. That class
names the component or the parameter that does not exist yet. Add it to
`ui/*.html`. Do not widen `EXTRA_ALLOWED`, and do not use `fjkit eject`.

Re-run `uv run python bench/render_bench.py` after you change a rendering knob
that is meant to be an optimisation.

## Failure modes tests will not catch

- **Composite macro raises `No caller defined`.** A macro that forwards its body
  into another block macro must capture the body first: `{% set body = caller() %}`,
  then `{% call row() %}{{ body }}{% endcall %}`. Inside a `{% call %}` block,
  Jinja rebinds `caller` to that block's own caller.
- **`@render` above `@router.get`.** `@router.get` registers whatever function it
  is handed, so the route keeps the undecorated handler and quietly answers with
  JSON. No error, no traceback — the page is just gone. `@render` goes below.
- **`{% include %}` inside a loop.** A template lookup plus a fresh context per
  iteration — 20–30% slower, growing linearly with row count. Use a macro.
- **A utility passed through a macro argument** (`icon(name, 16, "gap-2")`), or
  built by interpolation. `fjkit check` scans `class="…"` attributes only. Both
  pass the check. Both break on the day fjkit stops emitting that class.
- **A partial that renders only inside its page.** The full page looks correct,
  but the htmx swap returns a 500 error. The cause is a missing import, or a
  variable the partial inherited from the page's context.
- **`hx-swap` or `hx-target` inherited from an ancestor.** Both are inherited.
  A button inside a card that polls itself with `hx-swap="outerHTML"` inherits
  that swap and replaces the element it meant to fill — taking its `id` with
  it, so every later open of the same dialog quietly finds no target. Spell
  both out on any trigger nested inside another htmx element
  (`jobs/macros.html` is the worked case).
- **An icon-only button with no `aria_label`.** The label is empty, so nothing
  else names it.
- **A utility the stylesheet does not contain.** The CSS is built from what the
  kit's own templates use, so a plausible Tailwind class an app invents — or one
  a *kit* template invents, which `fjkit check` does not scan for — compiles,
  renders, and styles nothing. `grep` the class in
  `src/fjkit/static/dist/fjkit-vega.css` before believing it works.
- **`HX-Trigger` carrying a JSON array.** htmx passes a JSON *object* through as
  `event.detail` and wraps anything else — arrays included — as `{value: …}`.
  A listener reading `event.detail` directly then finds nothing, and the symptom
  is an empty toast rather than an error. Send an object.
- **`None` in `value=`.** It renders the four letters `None` into the box. Only
  `errors.<field>` answers `None` for an absent name; `values.<field>` answers
  `""`, because a field with nothing typed in it has a value and that value is
  empty.
- **A body taken with `Body(embed=True)`, or a second body parameter.** FastAPI
  then names the failure `body.payload.title`, so the key is `payload.title` and
  a template asking `errors.title` gets `None` — which is the same answer a
  field with nothing wrong with it gives. The red text never appears and nothing
  says why. Take the model as a single un-embedded parameter, or look the error
  up under its whole key.
- **`encoding="json"` on a page that never called `form_scripts()`.** The
  extension is not loaded, htmx submits urlencoded to a route that only reads
  JSON, and the reply is a 422 whose message is about the body not being an
  object — no field is named, so nothing turns red and the toast is addressed
  to a developer. `form_scripts()` is per page for the same reason
  `chart_scripts()` is: CHARTER §7 budgets what every page loads by default.
- **A form that clears itself when it is rejected.** `htmx:afterRequest` fires
  whether the request succeeded or not, so any `hx-on::after-request` that
  resets or navigates must test `event.detail.successful` first.

## Working on fjkit itself

`packages/fjkit/` is the package. `app/` is the demo, and it is also the
acceptance test. A component is done when it meets the ten-point definition in
`CHARTER.md` §6. That definition requires:

- closed enumerations, and no class-string parameter
- `**attrs` pass-through
- correct keyboard behaviour and ARIA
- both colour schemes verified
- contract tests
- documentation

When you change the package:

- Macro comments say **why**, not what. `ui/button.html` and `ui/attrs.html` are
  the house style.
- After touching `ui/*.html` or `static/src/fjkit.css`: `uv sync --group build &&
  uv run fjkit build-css`. It prints the size and fails over budget (28 KB gzip).
  Record the number in `docs/BACKLOG.md`.
- Files under `static/vendor/` are upstream — regenerate with
  `packages/fjkit/scripts/vendor_ui.py`. Upstream's own Jinja macros are not
  vendored; fjkit writes its own against the same CSS.
- `static/dist/fjkit.css` is a build artefact, not source.

Stop and ask the user before you do any of these:

- add a runtime dependency (there are exactly two: `fastapi` and `jinja2`)
- change a published macro signature
- add hand-written JavaScript
- add npm, `package.json` or `node_modules`
- relax a budget in `CHARTER.md` §7
