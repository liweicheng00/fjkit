/* ------------------------------------------------------------ 01 · wiring */
const WIRING = [
  {
    file: "app/main.py",
    lang: "python",
    why: "Two calls. FjkitConfig holds every knob; mount_fjkit serves the kit's assets from inside the installed package and compiles the environment once, at construction.",
    code: `from fastapi import FastAPI
from fjkit import FjkitConfig, mount_fjkit

config = FjkitConfig(
    template_dir=APP_DIR / "templates",
    bytecode_cache_dir=ROOT_DIR / ".jinja-cache",
)

app = FastAPI()

# Serves the kit's assets, and compiles the environment once — compiling a
# template is expensive, a later lookup is a dict hit.
mount_fjkit(app, config)`,
  },
  {
    file: "app/templates/base.html",
    lang: "jinja",
    why: "ui/shell.html owns the <head>, the theme flash-guard, the asset links and the page skeleton. Your base supplies only what is actually yours.",
    code: `{% extends "ui/shell.html" %}
{% from "ui/nav.html" import brand, nav_links %}

{% block site_title %}Acme{% endblock %}

{% block brand %}
  {{ brand("Acme", url_for(request, "dashboard"), icon_name="gauge") }}
{% endblock %}

{% block nav %}
  {{ nav_links(request, [("dashboard", "Overview"), ("tasks_page", "Tasks")]) }}
{% endblock %}`,
  },
  {
    file: "app/features/tasks/router.py",
    lang: "python",
    why: "Routers read the request, call the service, name a template. The handler itself returns nothing but data — @render turns it into the page, and the return annotation is what FastAPI reads for response_model, so one declaration describes both the page and the JSON. Option lists and variant maps are built here: a template prints what it is handed.",
    code: `router = APIRouter(tags=["tasks"])

# Built once, not rebuilt per render.
STATUS_FILTERS = [(None, "All")] + [(s, s.value.capitalize()) for s in Status]

def board(service: TaskService) -> BoardResponse:
    """Everything tasks/_board.html reads, in one place.

    The page includes that partial and every htmx endpoint returns it
    bare, so both paths have to supply the identical names. Building the
    response once is what stops the two from drifting apart.
    """
    return BoardResponse(
        tasks=service.list(),
        stats=service.stats(),
        status_filters=STATUS_FILTERS,
    )

# @render goes below @router.get — the routing decorator registers
# whatever function it is handed. def, not async def: rendering is
# CPU-bound, so Starlette runs this in the threadpool.
@router.get("/tasks", name="tasks_page")
@render("tasks/page.html", partial="tasks/_board.html")
def tasks_page(service: ServiceDep) -> BoardResponse:
    return board(service)`,
  },
  {
    file: "app/templates/tasks/page.html",
    lang: "jinja",
    why: "The page extends base, sets a title, and includes the same partial the htmx endpoints return. Nothing about the board is written twice.",
    code: `{% extends "base.html" %}
{% from "ui/layout.html" import page_header %}
{% from "ui/button.html" import button %}

{% block title %}Tasks{% endblock %}

{% block content %}
  {% call page_header("Tasks", "One board, no page reloads") %}
    {{ button("New task", variant="primary", icon_name="plus") }}
  {% endcall %}

  {% include "tasks/_board.html" %}
{% endblock %}`,
  },
];

(function wiring() {
  const tabs = $("#wiring-tabs");
  const code = $("#wiring-code");
  const caption = $("#wiring-caption");

  WIRING.forEach((entry, index) => {
    const tab = document.createElement("button");
    tab.type = "button";
    tab.setAttribute("role", "tab");
    tab.setAttribute("aria-selected", index === 0 ? "true" : "false");
    tab.textContent = entry.file;
    tab.addEventListener("click", () => show(index));
    tabs.appendChild(tab);
  });

  function show(index) {
    [...tabs.children].forEach((tab, i) => tab.setAttribute("aria-selected", String(i === index)));
    setCode(code, WIRING[index].code, WIRING[index].lang);
    caption.textContent = WIRING[index].why;
  }

  show(0);
})();

/* ------------------------------------------------- the mock FastAPI server
 *
 * Routes answer with the fragments build_data.py rendered through the real
 * macros, so what htmx swaps in is fjkit's own markup. The task list is the
 * "database": mutations change it, then every response re-renders the whole
 * board — which is the pattern the lesson is teaching.
 */
const STATUSES = [
  { name: "Todo", variant: "secondary" },
  { name: "Doing", variant: "info" },
  { name: "Done", variant: "success" },
];

let nextId = 100;
const seed = () => [
  { id: nextId++, title: "Ship the closed vocabulary", status: 2, owner: "ana" },
  { id: nextId++, title: "Write the form field set", status: 1, owner: "kai" },
  { id: nextId++, title: "Audit focus states", status: 0, owner: "unassigned" },
];

/* Three lessons show a board, so each gets its own id and its own rows. Two
   elements answering to #demo-board would make hx-target ambiguous — htmx takes
   the first match in the document, which is the kind of bug this page is
   supposed to teach you to avoid. */
const BOARDS = { "demo-board": seed(), "swap-board": seed(), "live-board": seed() };

function renderRow(task, options = {}) {
  const { target = "#demo-board", swap = "outerHTML", query = "" } = options;
  return fill(DATA.live.row, {
    __ID__: task.id,
    __TITLE__: esc(task.title),
    __STATUS__: STATUSES[task.status].name,
    __VARIANT__: STATUSES[task.status].variant,
    __OWNER__: esc(task.owner),
    __TARGET__: target,
    __SWAP__: swap,
    __QUERY__: query,
  });
}

function renderBoard(id = "demo-board", rowOptions = null) {
  const list = BOARDS[id];
  const count = `${list.length} ${list.length === 1 ? "task" : "tasks"}`;
  const options = rowOptions || { target: `#${id}`, swap: "outerHTML", query: `?board=${id}` };
  if (!list.length) return fill(DATA.live.board_empty, { __BOARD__: id, __COUNT__: count });
  return fill(DATA.live.board, {
    __BOARD__: id,
    __COUNT__: count,
    __ROWS__: list.map((task) => renderRow(task, options)).join(""),
  });
}

(function mockServer() {
  const { route } = window.__tMock;

  //: Which board a request belongs to, and how its rows should be wired on the
  //: way back — the mock equivalent of a route knowing what it is re-rendering.
  const boardOf = (request) => (BOARDS[request.query.get("board")] ? request.query.get("board") : "demo-board");
  const rowOptions = (request) => ({
    target: request.query.get("target") || "closest tr",
    swap: request.query.get("swap") || "outerHTML",
    query: `?${request.query.toString()}`,
  });

  route("GET", /^\/demo\/board$/, (request) => ({ text: renderBoard(boardOf(request)) }));

  route("POST", /^\/demo\/tasks$/, (request) => {
    const id = boardOf(request);
    const title = (request.body.get("title") || "").trim();
    if (title) {
      BOARDS[id].push({
        id: nextId++,
        title,
        status: 0,
        owner: (request.body.get("owner") || "").trim() || "unassigned",
      });
    }
    return { text: renderBoard(id) };
  });

  route("POST", /^\/demo\/tasks\/(\d+)\/advance$/, (request, match) => {
    const id = boardOf(request);
    const task = BOARDS[id].find((t) => t.id === Number(match[1]));
    if (task) task.status = Math.min(task.status + 1, STATUSES.length - 1);
    // The same state, rendered at whichever granularity the caller asked for:
    // one row for a row-level swap, the whole board for the fjkit pattern.
    if (request.query.get("as") === "row" && task) return { text: renderRow(task, rowOptions(request)) };
    return { text: renderBoard(id) };
  });

  route("DELETE", /^\/demo\/tasks\/(\d+)$/, (request, match) => {
    const id = boardOf(request);
    BOARDS[id] = BOARDS[id].filter((t) => t.id !== Number(match[1]));
    return { text: request.query.get("as") === "row" ? "" : renderBoard(id) };
  });

  route("GET", /^\/demo\/search$/, (request) => {
    const q = (request.query.get("q") || "").trim().toLowerCase();
    const list = BOARDS["live-board"];
    const hits = q ? list.filter((t) => (t.title + t.owner).toLowerCase().includes(q)) : list;
    if (!hits.length) return { text: DATA.live.results_empty };
    // Search results update themselves row by row, so a match can be advanced
    // without redrawing the list.
    const options = { target: "closest tr", swap: "outerHTML", query: "?board=live-board&as=row" };
    return { text: fill(DATA.live.results, { __ROWS__: hits.map((t) => renderRow(t, options)).join("") }) };
  });

  route("GET", /^\/demo\/panel$/, () => ({ text: DATA.live.panel }));

  let tick = 0;
  route("GET", /^\/demo\/status$/, () => {
    const states = [
      { __STATUS__: "queued", __VARIANT__: "secondary" },
      { __STATUS__: "building", __VARIANT__: "info" },
      { __STATUS__: "passing", __VARIANT__: "success" },
      { __STATUS__: "flaky", __VARIANT__: "warning" },
    ];
    return { text: fill(DATA.live.status, states[tick++ % states.length]) };
  });
})();

/* ------------------------------------------------------------ 04 · exchange */
(function exchange() {
  const log = $("#dg-log");
  const live = $("#dg-live");
  const label = $("#dg-stage-label");
  const stages = ["dg-browser", "dg-request", "dg-server", "dg-response", "dg-swap"];

  live.innerHTML = renderBoard("demo-board");
  htmx.process(live);

  const button = document.createElement("button");
  button.className = "btn";
  button.setAttribute("data-variant", "primary");
  button.setAttribute("hx-post", "/demo/tasks?board=demo-board");
  button.setAttribute("hx-vals", '{"title": "Ship it", "owner": "you"}');
  button.setAttribute("hx-target", "#demo-board");
  button.setAttribute("hx-swap", "outerHTML");
  button.textContent = "Fire the request";
  $("#dg-run").replaceWith(button);
  htmx.process(button);

  function light(upTo) {
    stages.forEach((id, i) => document.getElementById(id).setAttribute("data-lit", String(i <= upTo)));
  }

  function entry(request, response) {
    const headers = Object.entries(request.headers)
      .filter(([name]) => name.toLowerCase().startsWith("hx-"))
      .map(([name, value]) => `${name}: ${value}`)
      .join("  ·  ");
    const body = response.text
      ? `${esc(response.text.replace(/\s+/g, " ").slice(0, 220))}${response.text.length > 220 ? " …" : ""}`
      : "(empty body)";
    const node = document.createElement("div");
    node.className = "item";
    node.innerHTML = `<section>
      <h4>${esc(request.method)} ${esc(request.path)}</h4>
      <p>${esc(headers) || "no HX-* headers"}</p>
      <p>${response.status} text/html — ${body}</p>
    </section>`;
    if (log.firstElementChild && log.firstElementChild.matches("[data-empty]")) log.innerHTML = "";
    log.prepend(node);
    while (log.children.length > 12) log.lastElementChild.remove();
  }

  log.innerHTML = '<p data-empty>Nothing sent yet. Every request on this page lands here.</p>';
  window.__tMock.onExchange(entry);

  /* The diagram is driven by htmx's own events, so it cannot describe a step
     the request did not actually take. */
  document.body.addEventListener("htmx:beforeRequest", () => { light(1); label.textContent = "request sent"; });
  document.body.addEventListener("htmx:beforeSwap", () => { light(3); label.textContent = "fragment received"; });
  document.body.addEventListener("htmx:afterSwap", () => {
    light(4);
    label.textContent = "swapped";
    setTimeout(() => { light(0); label.textContent = "idle"; }, 1400);
  });

  light(0);
})();

/* ------------------------------------------------------ 05 · target & swap */
(function targets() {
  const controls = $("#swap-controls");
  const host = $("#swap-live");
  const codeEl = $("#swap-code");
  const logEl = $("#swap-log");
  const caption = $("#swap-caption");

  const SWAPS = {
    outerHTML: "replaces the target element itself — the response must contain the wrapper. This is what fjkit's board does.",
    innerHTML: "the default: replaces what is inside the target, keeping the element. Return the contents, not the wrapper.",
    beforeend: "appends inside the target — an infinite list, a chat log, a row added without redrawing the table.",
    afterbegin: "prepends inside the target — newest first.",
    delete: "removes the target and ignores the response body. The row-level delete.",
    none: "swaps nothing. Useful when you only want the side effect, or a response header.",
  };

  const TARGETS = {
    "#swap-board": "a CSS selector — the usual case, and the one fjkit's partials are built around.",
    "closest tr": "walks up from the element that fired to the nearest matching ancestor. Row-level updates.",
    this: "the element that fired the request replaces itself.",
  };

  const state = { target: "#swap-board", swap: "outerHTML" };

  function select(id, options, value, onChange) {
    const el = document.createElement("select");
    el.id = id;
    Object.keys(options).forEach((option) => {
      const opt = document.createElement("option");
      opt.value = option;
      opt.textContent = option;
      el.appendChild(opt);
    });
    el.className = "select";
    el.value = value;
    el.addEventListener("change", () => onChange(el.value));
    return el;
  }

  function field(labelText, node) {
    const wrap = document.createElement("div");
    wrap.className = "field";
    const label = document.createElement("label");
    label.className = "label";
    label.textContent = labelText;
    label.htmlFor = node.id;
    wrap.append(label, node);
    return wrap;
  }

  const reset = document.createElement("button");
  reset.className = "btn";
  reset.dataset.variant = "outline";
  reset.dataset.size = "sm";
  reset.type = "button";
  reset.textContent = "reset the board";
  reset.addEventListener("click", () => {
    BOARDS["swap-board"] = seed();
    render();
  });

  const resetWrap = document.createElement("div");
  resetWrap.className = "field";
  resetWrap.append(
    Object.assign(document.createElement("span"), { className: "label", textContent: "board state" }),
    reset,
  );

  /* `field_row("three")` is the right component and this file cannot call it —
     these controls are built in the browser, not by a template. Writing its
     utility classes out by hand here would be the exact cheat this site says
     it does not do, so the shape is an attribute and brand.css carries it as a
     labelled gap. */
  const rowEl = document.createElement("div");
  rowEl.setAttribute("data-field-row", "");
  rowEl.append(
    field("hx-target", select("sw-target", TARGETS, state.target, (v) => { state.target = v; render(); })),
    field("hx-swap", select("sw-swap", SWAPS, state.swap, (v) => { state.swap = v; render(); })),
    resetWrap,
  );
  controls.append(rowEl);

  function render() {
    // A row-level target needs a row-shaped response; #swap-board needs the
    // whole board. The mock server answers whichever the query asks for, the
    // way a real route would branch on what it was asked to re-render.
    const rowScoped = state.target !== "#swap-board";
    const query =
      `?board=swap-board${rowScoped
        ? `&as=row&target=${encodeURIComponent(state.target)}&swap=${encodeURIComponent(state.swap)}`
        : ""}`;

    host.innerHTML = renderBoard("swap-board", { target: state.target, swap: state.swap, query });
    htmx.process(host);

    setCode(codeEl, `{{ button("Advance", variant="ghost", size="xs",
          hx_post=url_for(request, "tasks_advance", task_id=task.id),
          hx_target="${state.target}",
          hx_swap="${state.swap}") }}`, "jinja");

    caption.textContent = `${state.target} — ${TARGETS[state.target]}  ·  ${state.swap} — ${SWAPS[state.swap]}`;
  }

  window.__tMock.onExchange((request, response) => {
    if (!request.path.startsWith("/demo/tasks")) return;
    const node = document.createElement("div");
    node.className = "item";
    node.innerHTML = `<section>
      <h4>${esc(request.method)} ${esc(request.path)}</h4>
      <p>hx-target: ${esc(state.target)} · hx-swap: ${esc(state.swap)}</p>
      <p>${response.text ? `${esc(response.text.replace(/\s+/g, " ").slice(0, 140))} …` : "(empty body — nothing to swap)"}</p>
    </section>`;
    logEl.prepend(node);
    while (logEl.children.length > 6) logEl.lastElementChild.remove();
  });

  render();
})();

/* ---------------------------------------------------------- 06 · triggers */
(function triggers() {
  const searchField = $("#demo-search-field");
  searchField.innerHTML = DATA.live.search;
  htmx.process(searchField);

  const options = { target: "closest tr", swap: "outerHTML", query: "?board=live-board&as=row" };
  $("#demo-results").innerHTML = fill(DATA.live.results, {
    __ROWS__: BOARDS["live-board"].map((task) => renderRow(task, options)).join(""),
  });
  htmx.process($("#demo-results"));

  const lazyHost = $("#demo-lazy-host");
  function lazy() {
    lazyHost.innerHTML = `<div hx-get="/demo/panel" hx-trigger="revealed" hx-swap="outerHTML">
      <p>Waiting to be revealed — scroll this into view.</p>
    </div>`;
    htmx.process(lazyHost);
  }
  $("#demo-lazy-reset").addEventListener("click", lazy);
  lazy();

  const pollHost = $("#demo-poll-host");
  const pollToggle = $("#demo-poll-toggle");
  let polling = false;
  pollToggle.addEventListener("click", () => {
    polling = !polling;
    pollToggle.textContent = polling ? "stop polling" : "start polling";
    if (polling) {
      pollHost.innerHTML = `<p>Build status, refreshed by the server.</p>
        <div hx-get="/demo/status" hx-trigger="load, every 2s" hx-swap="innerHTML"></div>`;
      htmx.process(pollHost);
    } else {
      // Removing the element is how you stop a poll — there is no timer to clear.
      pollHost.innerHTML = '<p>Stopped. Removing the element ends the poll.</p>';
    }
  });
})();

/* ---------------------------------------------------------- 07 · partials */
(function liveBoard() {
  const form = $("#demo-form");
  const host = $("#demo-board-host");
  form.innerHTML = fill(DATA.live.form, { __QUERY__: "?board=live-board", __TARGET__: "#live-board" });
  host.innerHTML = renderBoard("live-board");
  htmx.process(form);
  htmx.process(host);

  const busy = $("#demo-board-busy");
  document.body.addEventListener("htmx:beforeRequest", (event) => {
    if (host.contains(event.target) || form.contains(event.target)) busy.classList.add("htmx-request");
  });
  document.body.addEventListener("htmx:afterRequest", () => busy.classList.remove("htmx-request"));
})();

(function partials() {
  const picker = $("#flow-picker");
  const nodesEl = $("#flow-nodes");
  const codeEl = $("#flow-code");
  const caption = $("#flow-caption");

  const NODES = [
    { id: "req", page: "GET /tasks", swap: "POST /tasks", subPage: "a browser address bar", subSwap: "hx-post on the form" },
    { id: "handler", page: "tasks_page()", swap: "create_task()", subPage: "builds the board context", subSwap: "creates, then builds the same context" },
    { id: "template", page: "tasks/page.html", swap: "—", subPage: "extends base.html", subSwap: "skipped entirely" },
    { id: "partial", page: "tasks/_board.html", swap: "tasks/_board.html", subPage: "included by the page", subSwap: "returned on its own", shared: true },
  ];

  let mode = "page";

  picker.addEventListener("click", (event) => {
    const button = event.target.closest("[data-flow]");
    if (!button) return;
    mode = button.dataset.flow;
    [...picker.children].forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.flow === mode)));
    update();
  });

  function update() {
    nodesEl.innerHTML = NODES.map((node) => {
      const label = mode === "page" ? node.page : node.swap;
      const sub = mode === "page" ? node.subPage : node.subSwap;
      const lit = !(mode === "swap" && node.id === "template");
      return `<div class="item" data-lit="${lit}" data-shared="${Boolean(node.shared)}">
        <b>${esc(label)}</b><span>${esc(sub)}</span>
      </div>`;
    }).join("");

    if (mode === "page") {
      setCode(codeEl, `@router.get("/tasks", name="tasks_page")
@render("tasks/page.html", partial="tasks/_board.html")
def tasks_page(service: ServiceDep) -> BoardResponse:
    return board(service)`, "python");
      caption.textContent = "The full page renders the shell and includes tasks/_board.html for the first paint.";
    } else {
      setCode(codeEl, `@router.post("/tasks", name="tasks_create")
@render("tasks/_board.html")
def create_task(service: ServiceDep, payload: TaskCreate) -> BoardResponse:
    service.create(payload)
    # The same partial, bare. hx-swap="outerHTML" drops it back over #board.
    return board(service)`, "python");
      caption.textContent = "No doctype, no shell — just the fragment. An htmx endpoint is an @render naming a _*.html file.";
    }
  }

  update();
})();

/* ---------------------------------------------------------- 08 · patterns */
const PATTERNS = [
  {
    name: "Search as you type",
    tag: 'hx-trigger="keyup changed delay:400ms"',
    doc: { label: "examples/active-search", href: "https://htmx.org/examples/active-search/" },
    when: "<b>A list narrows while the user types</b> — and you want one request, not one per keystroke.",
    caption: "changed drops the request when the value did not actually move: arrows, modifiers, a retyped character. delay:400ms restarts the countdown on every keystroke, so a fast typist sends one request instead of twelve. The extra search event catches the native clear button that type=“search” gets for free.",
    files: [
      {
        label: "tasks/_search.html",
        lang: "jinja",
        code: `{% from "ui/form.html" import text_field %}

{{ text_field("q", label="Search", type="search", placeholder="Title or owner",
              hx_get=url_for(request, "tasks_search"),
              hx_trigger="keyup changed delay:400ms, search",
              hx_target="#results", hx_swap="innerHTML",
              hx_indicator="#searching") }}

{# The same partial the endpoint returns — first paint and every swap after. #}
{% include "tasks/_results.html" %}`,
      },
      {
        label: "router.py",
        lang: "python",
        code: `@router.get("/tasks/search", name="tasks_search")
@render("tasks/_results.html")
def tasks_search(service: ServiceDep, q: str = "") -> ResultsResponse:
    """Where the keystrokes land. No client-side rendering — just rows."""
    return ResultsResponse(tasks=service.search(q))`,
      },
    ],
  },

  {
    name: "A filter bar",
    tag: 'hx-push-url="true"',
    doc: { label: "attributes/hx-push-url", href: "https://htmx.org/attributes/hx-push-url/" },
    when: "<b>Chips or tabs that re-render a list</b>, with the active one lit and the URL kept honest.",
    caption: "The active variant is a comparison, not a class the template invents. hx-push-url puts the filtered URL in the address bar, so reload and Back land where the user was — which works only because the full GET answers the same query string, and it already does.",
    files: [
      {
        label: "tasks/_board.html",
        lang: "jinja",
        code: `{% from "ui/button.html" import button, button_group %}

{% call button_group() %}
  {% for value, label in status_filters %}
    {{ button(label, size="xs",
              variant="secondary" if active_status == value else "ghost",
              hx_get=url_for(request, "tasks_board") ~ ("?status=" ~ value if value else ""),
              hx_target="#board", hx_swap="outerHTML",
              hx_push_url="true") }}
  {% endfor %}
{% endcall %}`,
      },
      {
        label: "router.py",
        lang: "python",
        code: `# The option list is a module constant, not a comprehension in the template.
STATUS_FILTERS: list[tuple[Status | None, str]] = [(None, "All")] + [
    (s, s.value.capitalize()) for s in Status
]


@router.get("/tasks/board", name="tasks_board")
@render("tasks/_board.html")
def tasks_board(service: ServiceDep, status: Status | None = None) -> BoardResponse:
    """The htmx door. GET /tasks is the other one, over the same response."""
    return board(service, status)`,
      },
    ],
  },

  {
    name: "Carrying the filter",
    tag: "filter_query — built in Python",
    doc: { label: "docs/#parameters", href: "https://htmx.org/docs/#parameters" },
    when: "<b>A row action inside a filtered list</b>, whose response has to come back filtered the same way.",
    caption: "The quietest bug in an htmx app: the mutation succeeds, the board returns unfiltered, and the view resets under the user. urlencode gets the ? and the & right, and an empty filter produces an empty string rather than a bare ?. Build it in Python — a template that grows filter chains is one nobody can read.",
    files: [
      {
        label: "router.py",
        lang: "python",
        code: `from urllib.parse import urlencode


def board(service, status=None, owner=None) -> BoardResponse:
    """One response builder, used by the page and by every swap."""
    active = {k: v for k, v in (("status", status), ("owner", owner)) if v}
    return BoardResponse(
        tasks=service.list(status=status, owner=owner),
        active_status=status,
        # Every row action appends this, so the swap comes back filtered.
        filter_query=f"?{urlencode(active)}" if active else "",
    )`,
      },
      {
        label: "tasks/macros.html",
        lang: "jinja",
        code: `{{ button("Advance", variant="ghost", size="xs",
          icon_name="arrow-right", icon_end=true,
          hx_post=url_for(request, "tasks_advance", task_id=task.id) ~ filter_query,
          hx_target="#board", hx_swap="outerHTML") }}`,
      },
    ],
  },

  {
    name: "Confirm, then delete",
    tag: 'hx-confirm="Delete …?"',
    doc: { label: "attributes/hx-confirm", href: "https://htmx.org/attributes/hx-confirm/" },
    when: "<b>A destructive button</b> that should ask first — with no dialog component in the way.",
    caption: "hx-confirm is the browser's own confirm(): no JavaScript, no component, and it is the version that ships today. An icon-only button still needs aria_label, and the checker cannot catch that one for you. Re-rendering the whole board instead of deleting the row is what keeps the count in the card header true.",
    files: [
      {
        label: "tasks/macros.html",
        lang: "jinja",
        code: `{{ button("", variant="ghost", size="icon-xs", icon_name="trash",
          aria_label="Delete " ~ task.title,
          hx_delete=url_for(request, "tasks_delete", task_id=task.id) ~ filter_query,
          hx_target="#board", hx_swap="outerHTML",
          hx_confirm="Delete “" ~ task.title ~ "”?") }}`,
      },
      {
        label: "router.py",
        lang: "python",
        code: `@router.delete("/tasks/{task_id}", name="tasks_delete")
@render("tasks/_board.html")
def delete_task(service: ServiceDep, task_id: int,
                status: Status | None = None) -> BoardResponse:
    service.delete(task_id)
    # Not 204. The body of a successful delete is the board that replaces it.
    return board(service, status)`,
      },
    ],
  },

  {
    name: "Poll until it is done",
    tag: 'hx-trigger="load delay:2s"',
    doc: { label: "docs/#polling", href: "https://htmx.org/docs/#polling" },
    when: "<b>A job, an import, a build.</b> Refresh while it runs, and stop when it finishes.",
    caption: "Polling that ends when the work does: while the job runs the partial re-arms itself, and the finished render simply carries no hx-trigger, so the last response is the one that stopped asking. hx-trigger=“every 2s” never stops on its own — the server has to answer 286, htmx's stop-polling status, or something has to remove the element. Either shape costs one request per interval per open tab, so keep the handler cheap and the interval honest; past a couple of seconds, reach for SSE rather than a shorter one.",
    files: [
      {
        label: "jobs/_job.html",
        lang: "jinja",
        code: `{# A partial that asks for itself again, for exactly as long as there is news. #}
{% from "ui/data.html" import badge, progress %}

<div id="job-{{ job.id }}"
     {%- if job.running %}
     hx-get="{{ url_for(request, 'job_status', job_id=job.id) }}"
     hx-trigger="load delay:2s"
     hx-swap="outerHTML"
     {%- endif %}>
  {{ badge(job.status | capitalize, variant=job.variant) }}
  {{ progress(job.percent, label="Importing") }}
</div>`,
      },
      {
        label: "router.py",
        lang: "python",
        code: `@router.get("/jobs/{job_id}/status", name="job_status")
@render("jobs/_job.html")
def job_status(service: JobsDep, job_id: int) -> JobResponse:
    """job.running is false in the last response, and that ends the poll."""
    return JobResponse(job=service.get(job_id))`,
      },
    ],
  },

  {
    name: "Defer the slow panel",
    tag: 'hx-trigger="revealed"',
    doc: { label: "examples/lazy-load", href: "https://htmx.org/examples/lazy-load/" },
    when: "<b>A chart, a report, a tab nobody may open.</b> Keep it off the first paint's critical path.",
    caption: "revealed fires when the placeholder scrolls into view; load fires as soon as it is inserted — load for something heavy that is on screen immediately, revealed for anything below the fold. The response replaces the placeholder, so the endpoint returns the panel partial and nothing else. When the row count is user-controlled, that decorator takes stream=True instead.",
    files: [
      {
        label: "tasks/page.html",
        lang: "jinja",
        code: `{% from "ui/data.html" import empty_state %}

<div hx-get="{{ url_for(request, 'tasks_report') }}"
     hx-trigger="revealed"
     hx-swap="outerHTML">
  {{ empty_state("Report", "Renders when you scroll this far", icon_name="clock") }}
</div>`,
      },
      {
        label: "router.py",
        lang: "python",
        code: `@router.get("/tasks/report", name="tasks_report")
@render("tasks/_report.html", stream=True)
def tasks_report(service: ServiceDep) -> ReportResponse:
    # The expensive one. The page shipped a placeholder instead of waiting.
    return ReportResponse(rows=service.report())`,
      },
    ],
  },

  {
    name: "Load more",
    tag: 'hx-target="closest tr"',
    doc: { label: "examples/click-to-load", href: "https://htmx.org/examples/click-to-load/" },
    when: "<b>A long list, one page at a time</b> — with no page number living in the browser.",
    caption: "The sentinel row replaces itself with the next page, which carries the next sentinel — or nothing, when the rows run out. Nothing is counted on the client: the only thing that advances is the cursor the server sent. Swap the trigger to revealed and the same endpoint becomes infinite scroll; keep the button and the list stays reachable from the keyboard.",
    files: [
      {
        label: "tasks/_rows.html",
        lang: "jinja",
        code: `{# One page of rows, then the control that fetches the next. #}
{% from "ui/button.html" import button %}
{% from "ui/table.html" import cell %}
{% from "tasks/macros.html" import task_row %}

{% for task in tasks %}{{ task_row(request, task) }}{% endfor %}

{% if next_cursor %}
  <tr>
    {% call cell(colspan=5, align="center") %}
      {{ button("Load more", variant="outline", size="sm",
                hx_get=url_for(request, "tasks_rows") ~ "?after=" ~ next_cursor,
                hx_target="closest tr", hx_swap="outerHTML") }}
    {% endcall %}
  </tr>
{% endif %}`,
      },
      {
        label: "router.py",
        lang: "python",
        code: `@router.get("/tasks/rows", name="tasks_rows")
@render("tasks/_rows.html")
def tasks_rows(service: ServiceDep, after: int | None = None) -> RowsResponse:
    page = service.page(after=after, limit=20)
    return RowsResponse(tasks=page.items, next_cursor=page.next_cursor)`,
      },
    ],
  },

  {
    name: "Edit a row in place",
    tag: 'hx-include="closest tr"',
    doc: { label: "examples/click-to-edit", href: "https://htmx.org/examples/click-to-edit/" },
    when: "<b>Edit one row without a modal</b> and without navigating to an edit page.",
    caption: "Which partial is on screen is the state — there is no editing flag anywhere in the app, and Cancel is a plain hx-get that fetches the read-only row back. A form cannot wrap table rows, which is what hx-include is for: it gathers the inputs in the row and sends them with the request. The two one-line partials exist because an endpoint returns a template, while a repeated row stays a macro.",
    files: [
      {
        label: "tasks/macros.html",
        lang: "jinja",
        code: `{% macro task_row(request, task) -%}
  <tr>
    {{ cell(task.title, tone="strong") }}
    {{ cell(task.owner, tone="muted") }}
    {% call row_actions() %}
      {{ button("", variant="ghost", size="icon-xs", icon_name="pencil",
                aria_label="Edit " ~ task.title,
                hx_get=url_for(request, "tasks_edit_row", task_id=task.id),
                hx_target="closest tr", hx_swap="outerHTML") }}
    {% endcall %}
  </tr>
{%- endmacro %}

{% macro task_row_edit(request, task) -%}
  <tr>
    {% call cell() %}{{ text_field("title", value=task.title) }}{% endcall %}
    {% call cell() %}{{ text_field("owner", value=task.owner) }}{% endcall %}
    {% call row_actions() %}
      {{ button("Save", variant="primary", size="xs",
                hx_put=url_for(request, "tasks_update", task_id=task.id),
                hx_include="closest tr",
                hx_target="closest tr", hx_swap="outerHTML") }}
      {{ button("Cancel", variant="ghost", size="xs",
                hx_get=url_for(request, "tasks_row", task_id=task.id),
                hx_target="closest tr", hx_swap="outerHTML") }}
    {% endcall %}
  </tr>
{%- endmacro %}`,
      },
      {
        label: "the two partials",
        lang: "jinja",
        code: `{# tasks/_row.html #}
{% from "tasks/macros.html" import task_row %}
{{ task_row(request, task) }}

{# tasks/_row_edit.html #}
{% from "tasks/macros.html" import task_row_edit %}
{{ task_row_edit(request, task) }}`,
      },
      {
        label: "router.py",
        lang: "python",
        code: `@router.get("/tasks/{task_id}/row", name="tasks_row")
@render("tasks/_row.html")
def task_row(service: ServiceDep, task_id: int) -> RowResponse:
    """Cancel comes here. The read-only row is the resting state."""
    return RowResponse(task=service.get(task_id))


@router.get("/tasks/{task_id}/edit", name="tasks_edit_row")
@render("tasks/_row_edit.html")
def edit_row(service: ServiceDep, task_id: int) -> RowResponse:
    return RowResponse(task=service.get(task_id))


@router.put("/tasks/{task_id}", name="tasks_update")
@render("tasks/_row.html")
def update_task(service: ServiceDep, task_id: int, title: Annotated[str, Form()],
                owner: Annotated[str, Form()]) -> RowResponse:
    return RowResponse(task=service.update(task_id, TaskUpdate(title=title, owner=owner)))`,
      },
    ],
  },

  {
    name: "One field feeds another",
    tag: "change — and hx-include",
    doc: { label: "examples/value-select", href: "https://htmx.org/examples/value-select/" },
    when: "<b>Pick a project, and the owner list narrows</b> to the people on it.",
    caption: "A select fires on change by default, so there is no hx-trigger to write, and htmx sends the value of the element that fired — the query parameter is simply the field's name. When the endpoint needs more than that one field, hx-include names the rest. The options are (value, label) pairs built in the service; the template never maps a domain value to a label.",
    files: [
      {
        label: "tasks/_form.html",
        lang: "jinja",
        code: `{% from "ui/form.html" import select_field %}

{{ select_field("project", label="Project", options=projects, selected=project_id,
                hx_get=url_for(request, "tasks_owner_field"),
                hx_target="#owner-field", hx_swap="outerHTML") }}

{% include "tasks/_owner_field.html" %}`,
      },
      {
        label: "tasks/_owner_field.html",
        lang: "jinja",
        code: `{# The swap target is the partial's own wrapper, so outerHTML lands here. #}
{% from "ui/form.html" import select_field %}

<div id="owner-field">
  {{ select_field("owner", label="Owner", options=owners, blank="Anyone") }}
</div>`,
      },
      {
        label: "router.py",
        lang: "python",
        code: `@router.get("/tasks/owner-field", name="tasks_owner_field")
@render("tasks/_owner_field.html")
def owner_field(service: ServiceDep, project: int | None = None) -> OwnerFieldResponse:
    """project arrives on its own: a select sends its value with the request."""
    return OwnerFieldResponse(owners=service.members(project))`,
      },
    ],
  },
];

(function patterns() {
  const list = $("#pattern-list");
  const tabs = $("#pattern-tabs");
  const code = $("#pattern-code");
  const when = $("#pattern-when");
  const caption = $("#pattern-caption");
  const tag = $("#pattern-tag");
  const doc = $("#pattern-doc");

  PATTERNS.forEach((pattern, index) => {
    const entry = document.createElement("button");
    entry.type = "button";
    entry.className = "btn";
    entry.dataset.size = "sm";
    entry.setAttribute("role", "tab");
    entry.setAttribute("aria-selected", index === 0 ? "true" : "false");
    entry.textContent = pattern.name;
    entry.addEventListener("click", () => show(index, 0));
    list.appendChild(entry);
  });

  function show(index, fileIndex) {
    const pattern = PATTERNS[index];
    [...list.children].forEach((entry, i) => {
      entry.setAttribute("aria-selected", String(i === index));
      entry.dataset.variant = i === index ? "secondary" : "ghost";
    });

    // The file tabs belong to the pattern, so they are rebuilt with it rather
    // than hidden and reshown.
    tabs.replaceChildren(...pattern.files.map((file, i) => {
      const tab = document.createElement("button");
      tab.type = "button";
      tab.setAttribute("role", "tab");
      tab.setAttribute("aria-selected", String(i === fileIndex));
      tab.textContent = file.label;
      tab.addEventListener("click", () => show(index, i));
      return tab;
    }));

    window.basecoat?.refresh(tabs.closest(".tabs"));

    tag.textContent = pattern.tag;
    when.innerHTML = pattern.when;
    caption.textContent = pattern.caption;
    // Where this shape is documented upstream — htmx's own page, not a
    // restatement of it here.
    doc.href = pattern.doc.href;
    doc.textContent = `htmx.org/${pattern.doc.label} ↗`;
    setCode(code, pattern.files[fileIndex].code, pattern.files[fileIndex].lang);
  }

  show(0, 0);
})();

/* -------------------------------------------------------------- 09 · knob */
(function knob() {
  const hue = $("#hue");
  const chroma = $("#chroma");
  const preview = $("#knob-preview");
  const codeEl = $("#knob-code");
  const swatches = $("#swatches");
  const themePicker = $("#theme-picker");

  const PRESETS = [
    { name: "fjkit indigo", h: 275, c: 19 },
    { name: "forest", h: 152, c: 16 },
    { name: "ember", h: 42, c: 17 },
    { name: "crimson", h: 22, c: 20 },
    { name: "teal", h: 195, c: 13 },
    { name: "graphite", h: 275, c: 2 },
  ];

  PRESETS.forEach((preset) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "btn";
    button.dataset.size = "icon-sm";
    button.title = preset.name;
    button.setAttribute("aria-label", preset.name);
    button.setAttribute("aria-pressed", String(preset.h === 275 && preset.c === 19));
    // On a swatch the colour *is* the content, so it has to cover `.btn`'s 1px
    // border as well. That border is transparent, and inside a button group
    // every button keeps its right edge — so painting only the background left
    // a hairline of card between each pair of swatches and around the strip.
    const swatch = `oklch(0.52 ${preset.c / 100} ${preset.h})`;
    button.style.background = swatch;
    button.style.borderColor = swatch;
    button.addEventListener("click", () => {
      hue.value = preset.h;
      chroma.value = preset.c;
      apply();
    });
    swatches.appendChild(button);
  });

  function apply() {
    const h = Number(hue.value);
    const c = (Number(chroma.value) / 100).toFixed(2);
    const dark = document.documentElement.classList.contains("dark");
    const lightness = dark ? 0.72 : 0.52;
    const fg = dark ? `oklch(0.18 0.03 ${h})` : `oklch(0.985 0.005 ${h})`;

    document.documentElement.style.setProperty("--primary", `oklch(${lightness} ${c} ${h})`);
    document.documentElement.style.setProperty("--primary-foreground", fg);
    document.documentElement.style.setProperty("--ring", `oklch(${dark ? 0.55 : 0.52} ${c} ${h})`);

    [...swatches.children].forEach((button, i) => {
      button.setAttribute("aria-pressed", String(PRESETS[i].h === h && PRESETS[i].c === Number(chroma.value)));
    });

    setCode(codeEl, `/* app/static/brand.css — loaded after fjkit's stylesheet */
:root {
  --primary: oklch(0.52 ${c} ${h});
  --primary-foreground: oklch(0.985 0.005 ${h});
  --ring: oklch(0.52 ${c} ${h});
}

.dark {
  --primary: oklch(0.72 ${c} ${h});
  --primary-foreground: oklch(0.18 0.03 ${h});
}`, "css");
  }

  hue.addEventListener("input", apply);
  chroma.addEventListener("input", apply);

  themePicker.addEventListener("click", (event) => {
    const button = event.target.closest("[data-theme-choice]");
    if (!button) return;
    const choice = button.dataset.themeChoice;
    [...themePicker.children].forEach((b) => b.setAttribute("aria-pressed", String(b === button)));
    if (choice === "auto") {
      window.__tThemeLocked = false;
      window.__tApplyHostTheme();
    } else {
      window.__tThemeLocked = true;
      document.documentElement.classList.toggle("dark", choice === "dark");
      
    }
    apply();
  });

  preview.innerHTML = `
    <div style="display:flex;flex-direction:column;gap:1rem">
      ${fill(DATA.structure.page_header, { __TITLE__: "Overview", __DESC__: "Brand moves. Status does not." })}
      ${fill(DATA.layouts["grid|4|4"], {
        __ITEMS__: [
          fill(DATA.stats["|1|0"], { __LABEL__: "Total", __VALUE__: "27", __ICON18__: DATA.icons.list.replace(/width="16" height="16"/, 'width="18" height="18"') }),
          fill(DATA.stats["info|1|1"], { __LABEL__: "Doing", __VALUE__: "4", __HINT__: "active now", __ICON18__: DATA.icons.sparkle.replace(/width="16" height="16"/, 'width="18" height="18"') }),
          fill(DATA.stats["success|1|1"], { __LABEL__: "Done", __VALUE__: "18", __HINT__: "67% of the board", __ICON18__: DATA.icons.check.replace(/width="16" height="16"/, 'width="18" height="18"') }),
          fill(DATA.stats["warning|1|0"], { __LABEL__: "Blocked", __VALUE__: "2", __ICON18__: DATA.icons["circle-dot"].replace(/width="16" height="16"/, 'width="18" height="18"') }),
        ].join(""),
      })}
      ${fill(DATA.layouts["row|2"], {
        __ITEMS__: ["primary", "secondary", "outline", "success", "warning", "info", "destructive"]
          .map((v) => fill(DATA.badges[v], { __LABEL__: v })).join(""),
      })}
      ${fill(DATA.layouts["row|2"], {
        __ITEMS__: [
          fill(DATA.buttons["primary||start|0"], { __LABEL__: "Primary action", __ICON__: DATA.icons.plus }),
          fill(DATA.buttons["outline||none|0"], { __LABEL__: "Secondary", __ICON__: "" }),
          fill(DATA.buttons["destructive|sm|start|0"], { __LABEL__: "Delete", __ICON__: DATA.icons.trash }),
        ].join(""),
      })}
      ${fill(DATA.misc.progress, { __VALUE__: "67", __LABEL__: "Completion" })}
    </div>`;

  apply();
})();

/* ------------------------------------------------------------- 10 · check */
const SAMPLES = {
  bad: `{# The way you'd write it in any other Tailwind project #}
<div class="grid gap-6 lg:grid-cols-[1fr_19rem]">
  <div class="space-y-4">
    <div class="rounded-lg bg-white p-4 shadow">
      <h3 class="text-lg font-semibold text-slate-900">5 tasks</h3>
      <span class="rounded bg-green-100 px-2 text-green-700">Done</span>
      <button class="bg-[#4f46e5] text-white px-3 py-1.5">Add</button>
    </div>
  </div>
</div>`,
  good: `{# The same board, in the vocabulary #}
{% from "ui/data.html" import badge, card %}
{% from "ui/button.html" import button %}
{% from "ui/layout.html" import split, stack %}

{% call(slot) split() %}
  {% if slot == "main" %}
    {% call stack(4) %}
      {% call card("5 tasks") %}
        {{ badge("Done", variant="success") }}
        {{ button("Add", variant="primary") }}
      {% endcall %}
    {% endcall %}
  {% endif %}
{% endcall %}`,
};

(function checker() {
  const input = $("#checker-input");
  const output = $("#checker-output");
  const allowed = new Set(DATA.vocab.component_classes);
  const emitted = new Set(DATA.vocab.emitted_classes);

  $("#vocab-count").textContent = `${allowed.size} component classes`;

  /* Ported from fjkit/cli/check.py — same patterns, same messages. */
  const COLOUR_CHECKS = [
    [/\b(?:bg|text|border|ring|outline|fill|stroke|from|via|to|divide|shadow|accent|caret|decoration)-(?:slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-\d{2,3}\b/g,
      "Tailwind palette hue — name a role instead (primary / muted / destructive / success …)"],
    [/#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})\b/g,
      "hex literal — colours live in the token layer, not in markup"],
    [/\b(?:rgb|rgba|hsl|hsla|oklch|oklab|lab|lch)\(/g,
      "raw colour function — colours live in the token layer, not in markup"],
    [/\b(?:bg|text|border|ring|fill|stroke)-(?:white|black)\b/g,
      "absolute white/black — use the matching -foreground token"],
  ];

  function check(text) {
    const violations = [];

    text.split("\n").forEach((line, index) => {
      COLOUR_CHECKS.forEach(([pattern, reason]) => {
        for (const match of line.matchAll(pattern)) {
          violations.push({ line: index + 1, token: match[0], reason });
        }
      });
    });

    for (const match of text.matchAll(/class\s*=\s*"([^"]*)"/gs)) {
      const line = text.slice(0, match.index).split("\n").length;
      const stripped = match[1].replace(/\{\{[\s\S]*?\}\}|\{%[\s\S]*?%\}|\{#[\s\S]*?#\}/g, " ");
      stripped.split(/\s+/).filter(Boolean).forEach((token) => {
        if (token.includes("{") || token.includes("}")) return;
        const bare = token.split(":").pop();
        if (allowed.has(bare) || allowed.has(bare.replace(/^-+/, ""))) return;
        violations.push({
          line,
          token,
          reason: emitted.has(bare)
            ? "utility class in an app template — use a fjkit layout or component macro (stack / row / grid / split / card / table …). Utilities that fjkit happens to emit today are not part of its public vocabulary."
            : "not a fjkit class — it is absent from the shipped stylesheet, so it has no effect. Check the spelling, or use a component macro.",
        });
      });
    }

    return violations.sort((a, b) => a.line - b.line);
  }

  function run() {
    const violations = check(input.value);
    if (!violations.length) {
      output.innerHTML = `<div class="alert" data-variant="success"><h2>clean</h2>
        <section>Every class is part of the fjkit vocabulary. This is what CI sees.</section></div>`;
      return;
    }
    output.innerHTML =
      `<p>${violations.length} violation${violations.length === 1 ? "" : "s"}</p>` +
      violations.map((v) => `<div class="alert" data-variant="destructive"><h2>:${v.line}&nbsp; ${esc(v.token)}</h2><section>${esc(v.reason)}</section></div>`).join("");
  }

  document.querySelectorAll("[data-sample]").forEach((button) => {
    button.addEventListener("click", () => {
      input.value = SAMPLES[button.dataset.sample];
      run();
    });
  });

  input.value = SAMPLES.bad;
  input.addEventListener("input", run);
  run();
})();

