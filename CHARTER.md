# fjkit — Charter

What this document settles: what fjkit is for, where it stops, and which
decisions are closed. It contains nothing that expires. Measurements and the
record of assumptions that turned out wrong live in
[`docs/BACKLOG.md`](docs/BACKLOG.md).

Version scope is not in the repository. It lives in `goal/ROADMAP.md`, which is
untracked, because a roadmap is the one document here that is wrong the moment
it is committed: it states what is true this week, and a reader who finds it in
git history reads a plan as a promise. Nothing in this file depends on it.

Read §2 before proposing a feature and §3 before proposing an architecture
change. Both are settled ground; reopening either needs an RFC.

---

## 1. Mission

**Let someone who writes FastAPI build a good-looking, usable, accessible site
without touching a front-end toolchain.**

Three verifiable forms of the same claim:

- Empty directory to a first page with navigation and dark mode: 5 minutes,
  20 lines of Python, 0 build steps.
- A back-office page with a list, filters, pagination and an add/edit form:
  one afternoon, no CSS, no JavaScript.
- The user's repository contains no `package.json`, no `node_modules`, and no
  Tailwind binary.

The third one is the constraint the rest of this document protects.

---

## 2. Scope

### 2.1 The line

**fjkit owns what the browser receives and sends back. It never owns what your
database contains.**

The test for any proposal: *does this require fjkit to know the shape of your
data?* If yes, it belongs in the app.

The line is drawn there because a UI kit that knows your schema has to be
re-taught every time the schema changes, and because the moment fjkit can
generate a screen from a model, the generated screen is right for a week and
wrong forever.

| Proposal | Verdict | Why |
|---|---|---|
| `table(columns, rows)` | in | Knows `columns` is a sequence. Does not know what a column means. |
| Admin generator over your ORM models | out | Must read your schema. |
| `fjkit.auth` — cookie ⇄ token, CSRF, refresh | in | Moves a credential between a cookie and a store. Holds no user, no password, no role. |
| `@requires("admin")` | out | Roles are domain vocabulary. |
| `chart()` macro and the figure contract | in | Renders a figure the app built. |
| A route that returns your chart's data | out | The app owns its data and its URLs. |

### 2.2 The page budget

**What a page costs is decided by the page.** Anything every page pays for
needs a stated reason in §4. Anything optional is loaded by the component that
needs it.

This is the rule behind decisions that otherwise look inconsistent: all eight
style packs ship in the wheel because a page loads one; Plotly's 1.1 MB ships
in the wheel because only a page that calls `chart_scripts()` downloads it;
`select.js` is loaded by `ui/table.html`, not by the shell.

Install size is not the budget. Bytes per page is.

### 2.3 Two gates

**A component** enters if both hold:

1. The pattern appears in at least two mainstream systems — shadcn/ui,
   Bootstrap, Tailwind UI, Django Unfold, Basecoat, Radix.
2. A FastAPI back-office or content site needs it in the first week.

and none of these hold:

- It needs a client-side framework to work.
- It needs a build step on the user's side.
- It wraps a native HTML element without adding accessibility, state or server
  interaction.
- Its parameters cannot be expressed without accepting a class string.

Ordering: first the things whose absence forces the user to write Tailwind,
then the things whose absence makes the page ugly. The promise breaks in that
order.

Measured corollary: Basecoat's CSS covers 38 components, and **CSS without a
macro is not a component.** `.item` had styling and no macro; every app would
have written that macro once. Those gaps pass gate 2 cheaply, because the
styling already shipped.

**A subsystem** — `auth`, `charts`, `apidocs` and anything like them — is held
to a separate gate, because gate one was written for macros and these three
entered without one. All four must hold:

1. **It is required to put a correct page in a browser**, not merely useful
   next to one. A page that omits CSRF, field-level error display or session
   transport is wrong, not just plainer.
2. **Getting it wrong is invisible to the app author.** A missing `SameSite`
   flag; an `HX-Trigger` payload htmx re-wraps into `{value: …}`; a 422 whose
   `loc` never reaches the field. These fail silently and identically in every
   app, which is what makes them the kit's job rather than the app's.
3. **It is the same for every app.** Anything that varies with the domain
   belongs in the app.
4. **It ships switched off.** A subsystem is a plugin. An app that does not
   register it imports nothing — measured: after `mount_fjkit`, `sys.modules`
   contains no `fjkit.charts`.

**On URLs.** A plugin owns a URL only when the thing it provides *is* a page.
`ChartsPlugin` owns none, because a chart is something on one of the app's
pages. `ApiDocsPlugin` owns `/api-docs`, because that is a section of a site.
Neither puts a route in front of the app's own data.

### 2.4 What fjkit will not do

| Not doing | Why |
|---|---|
| ORM, migrations, query builder | Requires your schema (§2.1). |
| Admin generator | Requires your schema, and generates a screen that is correct once. |
| Identity: users, passwords, roles, permissions | `fjkit.auth` carries an identity the app issued; it never issues one. |
| React / Vue / Svelte adapters | The cost model in §1 assumes the server renders. |
| Any build step on the user's side | The constraint everything else protects (A1). |
| Components that accept a class string | A parameter list must be able to say no (A4). |
| A JS control where a native element works | `<select>` before a listbox. Every JS control is accessibility you now own. |
| Basecoat's `chart` | Its CSS selects `.chart > canvas` and its JS contains no charting code — it is a Chart.js skin. Shipping it tells the user to install a third front-end library. The single deliberate blank among Basecoat's 38 components. |

**The JSON form of a route is not an exception to "no front-end frameworks."**
`FjkitConfig.render_mode` and `@render(mode=…)` describe *the data this page was
handed*, defined by the handler's return annotation (A9). It is not a second
contract maintained for a client renderer. A field the page does not need is not
added because JSON might want it.

### 2.5 What fjkit keeps that looks out of scope

| Kept | Why it passes |
|---|---|
| `fjkit.auth` | Cookie ⇄ token transport and CSRF. `TokenSource` and `SessionStore` are seams the app fills; the kit never sees a credential's meaning. |
| `fjkit.apidocs` | A page, replacing Swagger UI. It owns `/api-docs` under §2.3. |
| `fjkit.charts` | The `chart()` macro, the asset loader, and the figure contract. Data, service and route stay in the app — 370 of the demo's 517 chart lines. |
| Four `.js` files fjkit wrote | See §4.2. |

---

## 3. Architecture decisions

Settled. Implement against them; do not re-propose. Changing one needs an RFC
and human approval.

| # | Decision | Why |
|---|---|---|
| A1 | **No build step on the user's side.** Tailwind runs when fjkit is released; `dist/fjkit-<pack>.css` ships in the wheel. | Nobody should maintain a front-end pipeline to change one class. |
| A2 | **The class vocabulary is closed.** Layout is a component too (`page`, `section`, `stack`, `row`, `grid`). Users write no raw utility classes. | A1 holds only while the vocabulary is closed. |
| A3 | **Colour has one knob.** Users override `--primary` and its siblings — CSS variables, no build. Status colours (success, warning, info, destructive) are deliberately not attached to that knob. | Rebranding must not break "green means done". |
| A4 | **The macro signature is the contract.** No class strings; parameters are closed enumerations; `**attrs` passes through HTML and `hx-*` only. | A parameter list must be able to say no. |
| A5 | **`ChoiceLoader`, app directory first.** `fjkit eject <name>` copies a file into the user's repo to shadow the package version. | The escape hatch exists; it is not the main road. |
| A6 | **One partial, two entry points.** The fragment a full page embeds is the one the htmx endpoint returns, guaranteed in the package by `@render(…, partial=…)`. | Page and swap cannot drift. |
| A7 | **Conventions are failing tests, not prose.** `fjkit check` and the pytest plugin ship to users. | A convention nobody can break by accident is the only kind worth having. |
| A8 | **Repeated components are macros, never `{% include %}` in a loop.** | Measured 20–30% slower, degrading linearly with row count. |
| A9 | **The return annotation is the route's only contract.** The handler returns a response model; `@render` spreads that same model into the template context. OpenAPI and the template are fed by one declaration. Display values use `@computed_field`. | Two contracts always disagree. |
| A10 | **All eight style packs ship in the wheel; the pack is a config value.** `FjkitConfig(style=…)`, and nothing else. Install-time selection (`uv add "fjkit[nova]"`, eight marker distributions) was built, then withdrawn before 0.1.0 and never published. | The budget is per page and a page loads one. The markers cost eight PyPI names and eight version streams to carry one word the config already says; the ambiguity they created — appearance depending on metadata scan order — is a bug that cannot even be bisected, and removing them removed it. |
| A11 | **Third-party front-end assets in the wheel are a whitelist (§4); every asset is loaded by an explicit page.** Two separate claims. **(1)** Only whitelisted bundles enter the wheel: `htmx.org`, `htmx-ext-json-enc`, `basecoat-css`, `plotly.js-basic-dist-min`. Each is pinned in `fjkit/vendored.py`, downloaded by `scripts/vendor_ui.py`, committed to `static/vendor/`, and served by `mount_fjkit`'s static mount. **(2)** A plugin's own assets live with the plugin in the wheel, because the §4 ceiling governs *what a page downloads by default*, not what files exist. A plugin still may not inject markup into the shell; assets arrive through a macro the page calls in `{% block scripts %}`, and must degrade when a third-party asset is absent. | "No build" promises that *you* need not build, not that nobody may load anything. Naming the load per page is stricter than a shell hook any plugin could use to add a `<script>` to every page. Moving a plugin's 3 KB to another wheel is bookkeeping, not restraint — that page downloads it either way. |

Five architecture diagrams — package boundary, template resolution, build
timing, render path, gate loop — are in `docs/architecture.md`. That file is
authoritative.

---

## 4. Quality budgets

Hard numbers. CI checks them; over budget is a red build.

### 4.1 Size

The CSS budget is **per page**: eight packs ship, a page loads one.

| Item | Budget | Measured 2026-09-05 |
|---|---|---|
| `fjkit-<pack>.css`, gzip — **the governed number** | ≤ 28 KB | 24.3–24.9 KB across eight packs (vega 24.7) |
| `fjkit-<pack>.css`, uncompressed — blowout guard | ≤ 260 KB | 219.1–237.2 KB (sera smallest, nova largest) |
| fjkit runtime dependencies | `fastapi`, `jinja2`, `pydantic`. A fourth needs an RFC | 3 |
| Third-party JS permitted in the wheel — **whitelist** | Only what `fjkit/vendored.py` pins: `htmx.org`, `htmx-ext-json-enc`, `basecoat-css` (with `all.min.js`), `plotly.js-basic-dist-min`. Adding one edits this cell (A11) | 4 |
| Single-page render regression | No more than 10% slower than the previous version | Threshold definition still open |

**Why gzip and not raw.** CSS compresses about 10:1, and the user downloads the
compressed bytes; raw is an implementation detail. The budget uses stdlib
`gzip` rather than brotli because it is everywhere, needs no dependency, and
reproduces. Brotli is roughly 20% smaller — a reference number, not the gate.

**Size is not a one-way ratchet** — the original assumption, overturned by
measurement. About 217 KB of the total is Basecoat's component layer;
`@layer components` is author CSS, Tailwind does not tree-shake it, and all 38
components ship regardless of how many macros fjkit writes. Verified six times:
`dialog` +54 bytes gzip, `sidebar` +102, the `tabs`/`code_block`/`item` batch
+0.6 KB, and 21 macros filling Basecoat's gaps for **+384 bytes gzip** combined
— 13 overlay macros cost 26 bytes between them. Only the utilities fjkit's own
templates use can grow, and all of those together measure 8 KB.

Shipping eight packs adds 167 KB (deflate) of install size and zero downloaded
bytes. Reference point: Bootstrap 5 minified is about 232 KB raw / 30 KB gzip.

The only real lever left is subsetting Basecoat, and `styles/<pack>.css` is one
file covering every component — splitting it means hand-editing a vendored file.
That needs an RFC first.

### 4.2 JavaScript

**Every page downloads:** htmx and Basecoat (both vendored), `js/errors.js`
(4,223 bytes raw / 1,798 gzip), and two inline blocks in `ui/shell.html`
totalling 517 bytes — theme anti-flash, and the listener that turns an
`HX-Trigger` event into a toast.

**Everything else loads from the macro that needs it**, through a
`<script defer>` inside the component:

| File | Loaded by | raw / gzip |
|---|---|---|
| `reveal.js` | `ui/form.html` | 2,506 / 1,280 |
| `select.js` | `ui/table.html` | 5,353 / 2,252 |
| `multiselect.js` | `ui/overlay.html` | 5,459 / 2,470 |
| `charts.js` | `chart_scripts()` | 8,953 / 3,822 |
| `json-enc.js` | `form_scripts()` | vendored |

**Adding a file fjkit wrote requires a named reason why no-JS is worse, and its
bytes recorded here.** This replaces the earlier rule that fjkit would write no
JavaScript at all. That rule failed four times, and each failure was correct:
Basecoat exposes the toaster as a method on an element rather than a
document-level listener, so something has to call it; the alternative for
error display was making 5xx swappable, which is a larger side effect. A
prohibition that is broken whenever it binds teaches readers that the charter
is decorative. The budget above binds.

---

## 5. Definition of done — components

Nine items. A component is not finished until all nine hold.

1. **Macro in `templates/ui/<name>.html`**, closed-enumeration parameters, no
   class string, `**attrs` passing HTML and `hx-*` through.
2. **No colour literals** — `fjkit check` passes.
3. **Keyboard operable, correct ARIA, visible focus** — native elements first;
   if `<select>` works, do not build a JS listbox.
4. **Verified in both colour schemes.**
5. **htmx usage** demonstrated in the signature comment and the docs page,
   where it applies.
6. **Tests**: renders standalone, asserts the load-bearing attributes, renders
   every value of every closed enumeration once.
7. **In the closed class whitelist** — normally automatic, derived from
   Basecoat's CSS.
8. **Documented**: a rendered example on the docs site's Components page, via
   an entry in `docs/workbench/build_data.py`. There is no Markdown copy in the
   repo; the parameter table comes from the macro's signature comment.
9. **CSS size delta recorded** in the pull request body.

Not every macro gets its own gallery entry. `menu_item`, `command_item` and
`avatar_group` are demonstrated inside their parent component, because a
display cell showing a menu item outside a menu teaches the wrong shape.

**Half of item 8 is enforced and half is not.** A macro added without a
cheatsheet row fails `test_the_cheatsheet_names_every_macro`, which walks
`ui/*.html` against the index; `test_the_cheatsheet_block_column_matches_the_macros`
goes further and checks the Block column against whether the body calls
`caller()`. Nothing yet fails when a macro ships with no *gallery* entry in
`docs/workbench/build_data.py` — that half still depends on someone
remembering, and guarding it needs an exemption list for the macros
demonstrated inside a parent.

Signature comments explain *why the design is this shape*, not what the macro
is. `ui/button.html` and `ui/attrs.html` are the reference.

---

## 6. Decisions that need a human

Stop and ask; do not decide these alone.

1. Changing a published macro signature.
2. Adding a runtime dependency, or a major-version bump of htmx or Basecoat.
3. Adding a JavaScript file fjkit wrote — see §4.2 for what the answer has to
   contain.
4. Any `npm`, `package.json` or `node_modules`, anywhere.
5. Branding, naming, the PyPI project name, licensing.
6. Publishing credentials, GitHub secrets, anything needing account access.
7. Reordering the roadmap by more than one version.
8. Relaxing a quality budget.

Everything else — opening issues, writing code, pull requests, merges,
documentation, releasing an `0.x` — proceeds without asking.

After 1.0, a breaking change needs an RFC and a deprecation period spanning two
minor versions.

---

## 7. Settled, kept here to avoid re-arguing

- **Charts are a plugin, and users can get one.** Basecoat's `chart` is not
  shipped; `fjkit.charts` is. The plugin owns the `chart()` macro, the asset
  macros, `charts.js`, and the figure contract (`PlotlyFigure`, `figure_of()`).
  The app owns the data, the service and the URL.
- **`fjkit.charts` lives inside the fjkit wheel** (`822891b`). A separate
  `fjkit-charts` distribution was proposed and rejected on measurement: of its
  three arguments, two were factually wrong and one was a tie. `plotly` is not
  and never was a fjkit dependency — `figure_of()` needs only an object with
  `to_plotly_json()`. `apidocs`, `auth` and `charts` are the same kind of
  thing: in the wheel, inert until registered. An app that draws no charts pays
  13,979 compressed bytes.
- **`pydantic` is the third runtime dependency.** Declared, not avoided.
  `field_errors()` reads `.errors()` and its `loc`/`msg` — that is pydantic's
  contract, and not importing it removes the declaration, not the coupling.
  Install cost is zero: `importlib.metadata.requires("fastapi")` lists
  `pydantic>=2.9.0` with no extra marker. The narrower rule that replaced the
  old exemption: **nothing in the kit may import a plotting library.**
- **Form errors are handled by a global exception handler**, not by dependency
  injection. Three designs were compared; the constraint that decided it was
  *change nothing about how FastAPI is normally written*. `Annotated[str, Form()]`,
  `ServiceDep` and return models all stay as they were; configuration attaches
  to `@render`. `FieldErrors` goes into **every** render's context, empty
  included, so a form has one version rather than a first-draw and a rejected
  one. The redraw boundary is the form, not the section containing it — the
  handler never ran, so the section's context does not exist. `hx-target`
  describes the success case, so a rejected response corrects it with
  `HX-Retarget`.
- **Messages are not delivered by flash.** Three layers — presentation, this
  response, surviving a redirect — and only the third needs a secret, so only
  the third is a plugin. Using flash for a response that does not redirect
  writes a cookie for a message being drawn right now.
- **Eight themes all ship**; the pack is a config value (A10). The size worry
  was measured away: the budget is per page.
- **The documentation site is the documentation.** Static HTML from GitHub
  Pages, built by fjkit's own Environment with the shell extending
  `ui/shell.html`. No Markdown copy exists in the repo.
- **`fjkit eject` copies macros, not files.** The override file owns only the
  macros named; the rest are re-exported from the kit through a reserved
  namespace an app cannot hijack, so upstream fixes keep arriving. Measured:
  `fjkit eject badge` produces 49 lines against the 289-line source file, owning
  1 macro and re-exporting 14. Stamps are per-macro, because a file-level digest
  would report your `badge` as stale when the kit changed `avatar`, and a
  warning you learn to ignore is not a warning. Known trade-off: private macros
  (`_`-prefixed) must be copied, since Jinja keeps them out of the module
  namespace. `form.html`'s `_message` is the only one. Removing the underscore
  would fix it by promoting an implementation detail to public API, so it stays.
