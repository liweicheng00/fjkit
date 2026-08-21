/* ------------------------------------------------------------ 02 · macros */
const ICON_CHOICES = Object.keys(DATA.icons);

const MACROS = {
  button: {
    label: "button",
    controls: [
      { key: "label", type: "text", label: "label", value: "Add task" },
      { key: "variant", type: "select", label: "variant", options: ["", "primary", "secondary", "outline", "ghost", "link", "destructive"], value: "primary" },
      { key: "size", type: "select", label: "size", options: ["", "xs", "sm", "lg", "icon", "icon-sm", "icon-xs"], value: "" },
      { key: "pos", type: "select", label: "icon", options: ["none", "start", "end"], value: "start" },
      { key: "icon", type: "select", label: "icon_name", options: ICON_CHOICES, value: "plus" },
      { key: "disabled", type: "check", label: "disabled", value: false },
    ],
    render: (p) => fill(DATA.buttons[`${p.variant}|${p.size}|${p.pos}|${p.disabled ? 1 : 0}`], {
      __LABEL__: esc(p.label),
      __ICON__: p.pos === "none" ? "" : DATA.icons[p.icon],
    }),
    jinja: (p) => {
      const args = [`"${p.label}"`];
      if (p.variant) args.push(`variant="${p.variant}"`);
      if (p.size) args.push(`size="${p.size}"`);
      if (p.pos !== "none") args.push(`icon_name="${p.icon}"`);
      if (p.pos === "end") args.push("icon_end=true");
      if (p.disabled) args.push("disabled=true");
      return `{% from "ui/button.html" import button %}\n\n{{ button(${args.join(", ")}) }}`;
    },
    caption: "href= switches the element to an <a> and drops type. Any extra keyword — hx_post, aria_label, data_* — becomes an attribute.",
  },

  badge: {
    label: "badge",
    controls: [
      { key: "label", type: "text", label: "label", value: "Done" },
      { key: "variant", type: "select", label: "variant", options: ["", "primary", "secondary", "outline", "destructive", "success", "warning", "info"], value: "success" },
    ],
    render: (p) => fill(DATA.badges[p.variant], { __LABEL__: esc(p.label) }),
    jinja: (p) => `{% from "ui/data.html" import badge %}\n\n{{ badge("${p.label}"${p.variant ? `, variant="${p.variant}"` : ""}) }}`,
    caption: "The variant is an attribute, not a class — data-variant=\"success\", never a parallel badge-success. Map a domain value to a variant in Python, not in the template.",
  },

  stat: {
    label: "stat",
    controls: [
      { key: "label", type: "text", label: "label", value: "In progress" },
      { key: "value", type: "text", label: "value", value: "12" },
      { key: "tone", type: "select", label: "tone", options: ["", "success", "warning", "info", "destructive", "muted"], value: "info" },
      { key: "hint", type: "text", label: "hint", value: "active right now" },
      { key: "icon", type: "select", label: "icon_name", options: ["", ...ICON_CHOICES], value: "sparkle" },
    ],
    render: (p) => fill(DATA.stats[`${p.tone}|${p.icon ? 1 : 0}|${p.hint ? 1 : 0}`], {
      __LABEL__: esc(p.label),
      __VALUE__: esc(p.value),
      __HINT__: esc(p.hint),
      __ICON18__: p.icon ? DATA.icons[p.icon].replace(/width="16" height="16"/, 'width="18" height="18"') : "",
    }),
    jinja: (p) => {
      const args = [`"${p.label}"`, isNaN(Number(p.value)) ? `"${p.value}"` : p.value];
      if (p.hint) args.push(`hint="${p.hint}"`);
      if (p.icon) args.push(`icon_name="${p.icon}"`);
      if (p.tone) args.push(`tone="${p.tone}"`);
      return `{% from "ui/data.html" import stat %}\n\n{{ stat(${args.join(", ")}) }}`;
    },
    caption: "The KPI tile. tone colours the number only — and it is a closed lookup, because an interpolated class like text-{{ tone }} would be absent from the stylesheet.",
  },

  progress: {
    label: "progress",
    controls: [
      { key: "value", type: "range", label: "value", value: 62, min: 0, max: 100 },
      { key: "label", type: "text", label: "label", value: "Done" },
    ],
    render: (p) => fill(p.label ? DATA.misc.progress : DATA.misc.progress_bare, {
      __VALUE__: esc(p.value),
      __LABEL__: esc(p.label),
    }),
    jinja: (p) => `{% from "ui/data.html" import progress %}\n\n{{ progress(${p.value}${p.label ? `, label="${p.label}"` : ""}) }}`,
    caption: "Carries role=\"progressbar\" and the aria-value* attributes, so it announces itself. Drop the label and the bar renders alone.",
  },

  card: {
    label: "card",
    controls: [
      { key: "preset", type: "select", label: "shape", options: ["titled", "plain", "described", "small", "actions", "flush"], value: "described" },
      { key: "title", type: "text", label: "title", value: "Throughput" },
      { key: "desc", type: "text", label: "description", value: "last 7 days" },
      { key: "body", type: "text", label: "body", value: "Nine tasks closed, two reopened." },
    ],
    render: (p) => fill(DATA.cards[p.preset], {
      __TITLE__: esc(p.title),
      __DESC__: esc(p.desc),
      __BODY__: esc(p.body),
      __ACTION__: "View all",
    }),
    jinja: (p) => {
      const args = { titled: `"${p.title}"`, plain: "", described: `"${p.title}", "${p.desc}"`, small: `"${p.title}", "${p.desc}", size="sm"`, actions: `"${p.title}", actions=filters`, flush: `"${p.title}", padded=false` }[p.preset];
      const pre = p.preset === "actions"
        ? `{% set filters %}\n  {{ button("View all", variant="outline", size="xs") }}\n{% endset %}\n\n`
        : "";
      return `{% from "ui/data.html" import card %}\n\n${pre}{% call card(${args}) %}\n  <p>${p.body}</p>\n{% endcall %}`;
    },
    caption: "actions takes pre-rendered markup rather than a second slot: a two-slot call block runs its body once per slot, which is wrong for a heavy body. padded=false lets a table sit flush against the edges.",
  },

  table: {
    label: "table",
    controls: [
      { key: "state", type: "select", label: "rows", options: ["3 rows", "empty"], value: "3 rows" },
    ],
    render: (p) => (p.state === "empty" ? DATA.tables.empty : DATA.tables.filled),
    jinja: () => `{% from "ui/table.html" import table, cell, row_actions %}
{% from "tasks/macros.html" import task_row %}

{% call table(TASK_COLUMNS, rows=tasks,
              empty_title="Nothing here",
              empty_description="No task matches this filter.") %}
  {% for task in tasks %}{{ task_row(request, task) }}{% endfor %}
{% endcall %}`,
    caption: "Pass rows and the macro owns the empty case, so no caller repeats the if-rows-else branch. A repeated row is a macro call in your loop — {% include %} there is a template lookup plus a fresh context per iteration.",
  },

  form: {
    label: "form",
    controls: [
      { key: "state", type: "select", label: "state", options: ["htmx form", "with an error"], value: "htmx form" },
    ],
    render: (p) => (p.state === "htmx form" ? DATA.forms.board : DATA.forms.error),
    jinja: (p) => (p.state === "htmx form"
      ? `{% from "ui/form.html" import form, field_row, text_field, select_field %}

{% call form(action=url_for(request, "tasks_create"),
             target="#board", reset_on_success=true) %}
  {% call field_row("wide-then-actions") %}
    {{ text_field("title", label="New task", required=true) }}
    {{ select_field("priority", label="Priority", options=priority_options) }}
    {{ text_field("owner", label="Owner", placeholder="unassigned") }}
    {{ button("Add", variant="primary", type="submit", icon_name="plus") }}
  {% endcall %}
{% endcall %}`
      : `{{ text_field("title", label="Title", required=true,
             error="Give the task a title.") }}`),
    caption: "target= is what makes it an htmx form; drop it and the same macro emits an ordinary POST that works without JavaScript. Every field already takes error= — wiring it to Pydantic is 0.3.",
  },
};

(function macros() {
  const picker = $("#macro-picker");
  const tablist = picker.querySelector('[role="tablist"]');
  const preview = $("#macro-preview");
  const jinjaEl = $("#macro-jinja pre");
  const htmlEl = $("#macro-html pre");
  const caption = $("#macro-caption");

  let current = "button";
  const state = {};

  /* One tab and one panel per macro, which is the pattern the picker always
     was: a row of choices where exactly one set of knobs is showing. It used to
     be a `button-group`, and a `role="group"` of buttons gives a keyboard user
     no arrow keys and a screen reader no idea the row selects a view.

     Every panel is built once and kept, so switching costs nothing and a knob
     you set on `badge` is still set when you come back to it. */
  Object.entries(MACROS).forEach(([key, macro]) => {
    state[key] = Object.fromEntries(macro.controls.map((c) => [c.key, c.value]));

    const panel = document.createElement("div");
    panel.id = `macro-panel-${key}`;
    panel.setAttribute("role", "tabpanel");
    /* Pre-hidden, unlike a server-rendered `tab_panel`: nothing here exists
       without JavaScript anyway, so there is no reader to keep it legible for —
       only a stack of seven panels flashing before Basecoat's script runs. */
    panel.hidden = key !== current;
    buildControls(key, panel);
    picker.appendChild(panel);

    const tab = document.createElement("button");
    tab.type = "button";
    tab.setAttribute("role", "tab");
    tab.setAttribute("aria-controls", panel.id);
    tab.setAttribute("aria-selected", String(key === current));
    tab.dataset.macro = key;
    tab.textContent = macro.label;
    tablist.appendChild(tab);
  });

  /* Selection, the roving tabindex and the arrow keys are Basecoat's. What is
     left for this file is the three panes *outside* the tab group — preview,
     code, caption — which have to follow the selection.

     Watching the attribute rather than listening for a click is not defensive
     coding: Basecoat's arrow-key handler calls its own `select()` directly and
     dispatches no click, so a click listener leaves a keyboard user looking at
     one component's knobs and another's preview. `aria-selected` is the one
     place every path — pointer, keyboard, a script calling `picker.select()` —
     has to write, so it is the thing worth reading. */
  const follow = () => {
    const key = tablist.querySelector('[role="tab"][aria-selected="true"]')?.dataset.macro;
    if (!key || key === current) return;
    current = key;
    update();
  };
  new MutationObserver(follow).observe(tablist, {
    subtree: true,
    attributes: true,
    attributeFilter: ["aria-selected"],
  });

  /* Deferred scripts run in document order and Basecoat initialises on
     DOMContentLoaded, so it sees the tabs above and needs no help. The call is
     here for the day someone moves a <script> tag: `refresh` exists only once
     Basecoat has already run, and it re-reads a tablist that changed since. */
  picker.refresh?.();

  function buildControls(key, controlsEl) {
    MACROS[key].controls.forEach((control) => {
      const wrap = document.createElement("div");
      wrap.className = "field";
      // Basecoat's own knob for a control that sits beside its label.
      if (control.type === "check") wrap.dataset.orientation = "horizontal";
      const id = `mc-${key}-${control.key}`;
      const label = document.createElement("label");
      label.className = "label";
      label.htmlFor = id;
      label.textContent = control.label;

      let input;
      if (control.type === "select") {
        input = document.createElement("select");
        input.className = "select";
        control.options.forEach((option) => {
          const opt = document.createElement("option");
          opt.value = option;
          opt.textContent = option === "" ? "(default)" : option;
          input.appendChild(opt);
        });
        input.value = state[key][control.key];
      } else if (control.type === "check") {
        input = document.createElement("input");
        input.type = "checkbox";
        input.checked = Boolean(state[key][control.key]);
      } else if (control.type === "range") {
        input = document.createElement("input");
        input.type = "range";
        input.min = control.min;
        input.max = control.max;
        input.value = state[key][control.key];
      } else {
        input = document.createElement("input");
        input.className = "input";
        input.type = "text";
        input.value = state[key][control.key];
      }

      input.id = id;
      input.addEventListener("input", () => {
        state[key][control.key] = control.type === "check" ? input.checked : input.value;
        update();
      });

      if (control.type === "check") { wrap.append(input, label); } else { wrap.append(label, input); }
      controlsEl.appendChild(wrap);
    });
  }

  function update() {
    const macro = MACROS[current];
    const params = state[current];
    const html = macro.render(params);
    preview.innerHTML = html;
    setCode(jinjaEl, macro.jinja(params), "jinja");
    setCode(htmlEl, html.replace(/\n\s*\n/g, "\n"), "html");
    htmlEl.setAttribute("data-wrap", "");
    caption.textContent = macro.caption;
  }

  update();
})();

/* ------------------------------------------------------------ 03 · layout */
(function layout() {
  const controls = $("#layout-controls");
  const preview = $("#layout-preview");
  const codeEl = $("#layout-code");
  const caption = $("#layout-caption");

  const state = { macro: "grid", gap: 4, cols: 3, aside: "md", count: 4 };

  const CAPTIONS = {
    stack: "Vertical flow, built on flex + gap rather than space-y-*: gap cannot collapse, and cannot double up when a child is conditionally absent.",
    row: "Horizontal flow. wrap defaults to true — a row of buttons that cannot wrap is a horizontal scrollbar waiting for a narrow screen.",
    grid: "cols is what you want on a wide screen; the breakpoints are fixed on purpose. Letting callers choose breakpoints turns a layout vocabulary back into Tailwind with extra steps.",
    split: "Two slots, so the body runs once per slot and each branch renders in exactly one of them. This is the board-plus-sidebar shape.",
  };

  const GAPS = { stack: [0, 1, 2, 3, 4, 5, 6, 8], row: [0, 1, 2, 3, 4, 5, 6, 8], grid: [2, 4, 6], split: [4, 6] };

  function field(labelText, node) {
    const wrap = document.createElement("div");
    wrap.className = "field";
    const label = document.createElement("label");
    label.textContent = labelText;
    label.htmlFor = node.id;
    wrap.append(label, node);
    return wrap;
  }

  function select(id, options, value, onChange) {
    const el = document.createElement("select");
    el.id = id;
    options.forEach((option) => {
      const opt = document.createElement("option");
      opt.value = option;
      opt.textContent = option;
      el.appendChild(opt);
    });
    el.value = value;
    el.addEventListener("change", () => onChange(el.value));
    return el;
  }

  function build() {
    controls.innerHTML = "";
    controls.append(
      field("macro", select("ly-macro", ["stack", "row", "grid", "split"], state.macro, (v) => {
        state.macro = v;
        if (!GAPS[v].includes(Number(state.gap))) state.gap = GAPS[v][Math.min(1, GAPS[v].length - 1)];
        build();
        update();
      })),
      field("gap", select("ly-gap", GAPS[state.macro], state.gap, (v) => { state.gap = Number(v); update(); })),
    );

    if (state.macro === "grid") {
      controls.append(field("cols", select("ly-cols", [2, 3, 4], state.cols, (v) => { state.cols = Number(v); update(); })));
    }
    if (state.macro === "split") {
      controls.append(field("aside", select("ly-aside", ["sm", "md", "lg"], state.aside, (v) => { state.aside = v; update(); })));
    }
    if (state.macro !== "split") {
      controls.append(field("your items", select("ly-count", [1, 2, 3, 4, 5, 6], state.count, (v) => { state.count = Number(v); update(); })));
    }
  }

  function tiles(count) {
    return Array.from({ length: count }, (_, i) => `<div data-tile>your content ${i + 1}</div>`).join("");
  }

  function update() {
    let html;
    let source;

    if (state.macro === "split") {
      html = fill(DATA.layouts[`split|${state.aside}|${state.gap}`], {
        __MAIN__: '<div data-tile>the board</div>',
        __ASIDE__: '<div data-tile>the stats panel</div>',
      });
      source = `{% from "ui/layout.html" import split %}

{% call(slot) split(aside="${state.aside}", gap=${state.gap}) %}
  {% if slot == "main" %}
    {% include "tasks/_board.html" %}
  {% else %}
    {% include "tasks/_stats.html" %}
  {% endif %}
{% endcall %}`;
    } else {
      const key = state.macro === "grid" ? `grid|${state.cols}|${state.gap}` : `${state.macro}|${state.gap}`;
      html = fill(DATA.layouts[key], { __ITEMS__: tiles(state.count) });
      const args = state.macro === "grid" ? `cols=${state.cols}, gap=${state.gap}` : `${state.gap}`;
      source = `{% from "ui/layout.html" import ${state.macro} %}

{% call ${state.macro}(${args}) %}
  {# your content #}
{% endcall %}`;
    }

    preview.innerHTML = html;
    setCode(codeEl, source, "jinja");
    caption.textContent = CAPTIONS[state.macro];
  }

  build();
  update();
})();


/* -------------------------------------------------------- 11 · cheatsheet */
setCode($("#cheatsheet-code"), `layout.html   stack(gap=4, align)                     ·  block
              row(gap=3, align="center", justify, wrap=true)
              grid(cols=3, gap=4)                     ·  cols 2|3|4
              split(aside="md", gap=6)                ·  two slots
              page_header(title, description)         ·  block = actions
              section(title, description, gap=4)
              divider()

button.html   button(label, variant, size, type="button", href,
                     icon_name, icon_end=false, disabled=false, **attrs)
              button_group(gap=2)                     ·  block

data.html     badge(label, variant)
              card(title, description, size, actions, padded=true)
              stat(label, value, hint, icon_name, tone)
              metric_group(items, cols=3)   progress(value, label)
              empty_state(title, description, icon_name)
              bullet_list(tone) / list_item()         ·  blocks
              link(label, href)   kbd(keys)

form.html     form(action, method="post", target, swap="outerHTML",
                   reset_on_success=false, card=true) ·  block
              field_row(template="two", gap=3)        ·  block
              text_field(name, label, value, placeholder, type,
                         required, hint, error, id)
              select_field(name, label, options, selected, blank,
                           hint, error, id)

table.html    table(columns, rows, empty_title, empty_description)
              cell(value, tone, numeric, align)   row_actions()

nav.html      brand(label, href, icon_name)
              nav_links(request, links)   theme_toggle()

icon.html     icon(name, size=16)                     ·  1,767 Lucide names

globals       url_for(request, name, **params)   is_active(request, name)
              fjkit_static(path)   fjkit_version   fjkit_icon_path(name)

── htmx ─────────────────────────────────────────────────────────────────
  Pass any of these to any macro as hx_* keywords: hx_post="/tasks"
  Upstream: htmx.org/reference · htmx.org/examples · htmx.org/docs

  request     hx-get  hx-post  hx-put  hx-patch  hx-delete
  where       hx-target="#board" | "closest tr" | "this" | "next .row"
  how         hx-swap="outerHTML | innerHTML | beforeend | afterbegin
                       | beforebegin | afterend | delete | none"
              …with modifiers: swap:200ms  settle:100ms  scroll:top
  when        hx-trigger="click | submit | change            (defaults)
                          keyup changed delay:400ms          search
                          revealed                           lazy load
                          load                               on insert
                          every 2s                           polling
                          click from:body                    elsewhere"
  extras      hx-vals='{"id": 3}'      values sent with the request
              hx-include="#filters"    other fields to send
              hx-confirm="Sure?"       native confirm before firing
              hx-indicator="#spinner"  gets the htmx-request class
              hx-push-url="true"       put the URL in the address bar
              hx-swap-oob="true"       in a RESPONSE: swap a second element

  response    HX-Request: true         set on every htmx request
   headers    HX-Trigger: {"toast": …} fire a client event
              HX-Redirect / HX-Refresh full-page navigation
              HX-Retarget               change the target from the server`, "text");


/* --------------------------------------------------------- 03/04 · showcase
 * The macros with nothing to configure. Same data.json as every other preview
 * on the site: the markup is what fjkit emitted at build time, and the `jinja`
 * string beside it is the call that produced it. Placeholders (__TITLE__ …)
 * are substituted here for the same reason they are in the playground — Jinja
 * prints whatever it is handed, so the surrounding markup is still genuine. */
const TILE = '<div data-tile>your content</div>';

const SHOWCASE = {
  page_header: {
    html: () => fill(DATA.structure.page_header_actions, {
      __TITLE__: "Tasks",
      __DESC__: "Everything the team has open right now.",
      __ACTION__: "New task",
    }),
    jinja: `{% from "ui/layout.html" import page_header %}

{% call page_header("Tasks", "Everything the team has open right now.") %}
  {{ button("New task", variant="primary", size="sm") }}
{% endcall %}`,
    caption: "Called without a block it is just the two lines of text. The block is the actions slot, so the buttons stay level with the title at every width.",
  },

  section: {
    html: () => fill(DATA.structure.section, {
      __TITLE__: "This week",
      __DESC__: "Grouping inside a page, one level down from page_header.",
      __ITEMS__: TILE + TILE,
    }),
    jinja: `{% from "ui/layout.html" import section %}

{% call section("This week", "Grouping inside a page.") %}
  {# whatever belongs under that heading #}
{% endcall %}`,
    caption: "A heading plus a stack. Reach for it when a page has more than one thing on it and the second thing needs a name.",
  },

  divider: {
    html: () => DATA.structure.divider,
    jinja: `{% from "ui/layout.html" import divider %}

{{ divider() }}`,
    caption: "A horizontal rule that uses the border token, so it stays a hairline in both schemes. Prefer a section heading where the split has a name.",
  },

  empty_state: {
    html: () => fill(DATA.misc.empty_state, {
      __TITLE__: "Nothing here yet",
      __DESC__: "Add the first task with the form above.",
      __ICON__: DATA.icons.list,
    }),
    jinja: `{% from "ui/data.html" import empty_state %}

{{ empty_state("Nothing here yet",
               "Add the first task with the form above.",
               icon_name="list") }}`,
    caption: "table renders this for you when rows is empty — pass empty_title, empty_description and empty_icon instead of writing the branch yourself.",
  },

  metric_group: {
    html: () => DATA.misc.metric_group,
    jinja: `{% from "ui/data.html" import metric_group %}

{{ metric_group([("Todo", 4), ("Doing", 2), ("Done", 9)]) }}`,
    caption: "The compact row above a table. Build the list in Python — a template that zips two lists is doing work the router should have finished.",
  },

  bullet_list: {
    html: () => DATA.misc.bullet_list,
    jinja: `{% from "ui/data.html" import bullet_list, list_item %}

{% call bullet_list() %}
  {% call list_item() %}Templates are compiled once per process.{% endcall %}
  {% call list_item() %}A row costs a function call, not a lookup.{% endcall %}
{% endcall %}`,
    caption: "Two blocks rather than a list argument, because an item is markup: it can hold a badge, a link or a kbd without the caller escaping anything.",
  },

  inline: {
    html: () => `<p>Read ${DATA.misc.link}, or press ${DATA.misc.kbd} to search.</p>`,
    jinja: `{% from "ui/data.html" import link, kbd %}

<p>Read {{ link("the 20k-row report", "#") }},
   or press {{ kbd("⌘K") }} to search.</p>`,
    caption: "The two that live inside a sentence. link carries the underline and focus ring the token layer defines; kbd renders the key cap.",
  },
};

(function showcases() {
  Object.entries(SHOWCASE).forEach(([key, item]) => {
    const host = document.querySelector(`[data-showcase="${key}"]`);
    if (!host) return;
    host.innerHTML = item.html();
    setCode(document.querySelector(`[data-showcase-code="${key}"]`), item.jinja, "jinja");
    document.querySelector(`[data-showcase-caption="${key}"]`).textContent = item.caption;
  });
})();

/* ------------------------------------------------------------- 05 · icons */
(function icons() {
  const grid = $("#icon-grid");
  if (!grid) return;

  
  grid.innerHTML = Object.entries(DATA.icons)
    .map(([name, svg]) => `<figure>${svg}<figcaption>${esc(name)}</figcaption></figure>`)
    .join("");

  setCode($("#icon-code"), `{% from "ui/icon.html" import icon %}

{{ icon("plus") }}            {# 16px, currentColor #}
{{ icon("gauge", 18) }}       {# any size #}

{# or, far more often, by name on the macro that needs one #}
{{ button("Add", variant="primary", icon_name="plus") }}
{{ stat("Throughput", 12, icon_name="gauge") }}`, "jinja");
})();
