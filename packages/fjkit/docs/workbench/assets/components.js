/* The Components page, one section per file in `src/fjkit/templates/ui/`.
 *
 * `MACROS` is the knobs; `SHOWCASE` is the macros with nothing to turn;
 * `SNIPPET` is the two files that render no preview at all. Each entry names
 * the section that hosts it, and the sections are the directory listing — so
 * "which section does this go in" is answered by the macro's own file. */

/* ------------------------------------------------- the playground entries */
const ICON_CHOICES = Object.keys(DATA.icons);

/* The form picker's five states. Kept out of the entry itself because each one
   carries a Jinja snippet, and five of those inline turn one macro's definition
   into half the file. */
const FORM_STATE = {
  "htmx form": "board",
  "with an error": "error",
  "textarea + checkbox": "long",
  "radios vs select": "choice",
  "switches in a fieldset": "settings",
};

const FORM_JINJA = {
  "htmx form": `{% from "ui/form.html" import form, field_row, text_field, select_field %}

{% call form(action=url_for(request, "tasks_create"),
             target="#board", reset_on_success=true) %}
  {% call field_row("wide-then-actions") %}
    {{ text_field("title", label="New task", required=true) }}
    {{ select_field("priority", label="Priority", options=priority_options) }}
    {{ text_field("owner", label="Owner", placeholder="unassigned") }}
    {{ button("Add", variant="primary", type="submit", icon_name="plus") }}
  {% endcall %}
{% endcall %}`,

  "with an error": `{{ text_field("title", label="Title", required=true,
             error="Give the task a title.") }}`,

  "textarea + checkbox": `{% from "ui/form.html" import form, textarea_field, checkbox_field %}
{% from "ui/layout.html" import stack, row %}

{% call form(action=url_for(request, "tasks_update", task_id=task.id)) %}
  {% call stack(4) %}
    {{ textarea_field("notes", label="Notes",
                      hint="Grows with what you type — no rows to guess at.") }}
    {{ checkbox_field("blocked", label="Blocked on something else",
                      checked=task.blocked) }}
    {% call row(justify="end") %}
      {{ button("Save", variant="primary", type="submit") }}
    {% endcall %}
  {% endcall %}
{% endcall %}`,

  "radios vs select": `{% from "ui/form.html" import radio_group, select_field %}

{# One options shape for both, so this is a one-word edit either way.
   Radios show every choice and cost a line each: they win up to about
   five and lose after that. #}
{{ radio_group("priority", label="Priority", options=priority_options,
               selected=task.priority) }}

{{ select_field("owner", label="Owner", options=owner_options,
                selected=task.owner) }}`,

  "switches in a fieldset": `{% from "ui/form.html" import form, fieldset, switch_field %}
{% from "ui/layout.html" import stack %}

{% call form(action=url_for(request, "settings_save")) %}
  {% call stack(6) %}
    {% call fieldset("Notifications", hint="Applies to this board only.") %}
      {{ switch_field("email", label="Email me when a task moves",
                      checked=prefs.email) }}
      {{ switch_field("digest", label="Weekly digest",
                      hint="Monday morning, one message.") }}
    {% endcall %}

    {% call fieldset("Danger zone") %}
      {# error= replaces the hint rather than stacking on it, and marks the
         control aria-invalid. Same three parameters on every field. #}
      {{ switch_field("archive", label="Archive done tasks nightly",
                      error=errors.archive) }}
    {% endcall %}
  {% endcall %}
{% endcall %}`,
};

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

  button_group: {
    label: "button_group",
    controls: [
      { key: "orientation", type: "select", label: "orientation", options: ["horizontal", "vertical"], value: "horizontal" },
      { key: "gap", type: "select", label: "gap", options: [1, 2, 3, 4], value: 2 },
    ],
    render: (p) => DATA.groups[`${p.gap}|${p.orientation}`],
    jinja: (p) => `{% from "ui/button.html" import button_group %}

{% call button_group(${p.orientation === "vertical" ? 'orientation="vertical"' : `gap=${p.gap}`}) %}
  {{ button("Save", variant="primary") }}
  {{ button("Cancel", variant="outline") }}
  {{ button("Delete", variant="destructive") }}
{% endcall %}`,
    caption: "Horizontal is a row, so gap is yours. Vertical is Basecoat's .button-group, which joins the buttons into one control and shares their borders — there is no gap to set, and setting one would be asking for a column of separate buttons instead.",
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
      { key: "state", type: "select", label: "state", options: ["htmx form", "with an error", "textarea + checkbox", "radios vs select", "switches in a fieldset"], value: "htmx form" },
    ],
    render: (p) => DATA.forms[FORM_STATE[p.state]],
    jinja: (p) => FORM_JINJA[p.state],
    caption: "target= is what makes it an htmx form; drop it and the same macro emits an ordinary POST that works without JavaScript. Every field takes the same label/hint/error trio, an error replaces the hint rather than stacking on it, and wiring error= to Pydantic is 0.3.",
  },
};

/* One playground, instantiated once per file that has knobs to offer.
 *
 * `slug` names the section — `button`, `data`, `form`, `table` — and
 * the template renders the same skeleton under it either way:
 *
 *     #<slug>-picker      the tab strip, when the file has more than one macro
 *     #<slug>-controls    the knobs, when it has exactly one
 *     #<slug>-preview     #<slug>-jinja pre   #<slug>-html pre   #<slug>-caption
 *
 * A one-macro file gets no tab strip, because a tablist with a single tab is a
 * control that cannot be operated. */
function playground(slug, keys) {
  const picker = document.getElementById(`${slug}-picker`);
  const tablist = picker?.querySelector('[role="tablist"]');
  const preview = $(`#${slug}-preview`);
  const jinjaEl = $(`#${slug}-jinja pre`);
  const htmlEl = $(`#${slug}-html pre`);
  const caption = $(`#${slug}-caption`);
  if (!preview) return;

  let current = keys[0];
  const state = {};

  /* One tab and one panel per macro, which is the pattern the picker always
     was: a row of choices where exactly one set of knobs is showing. It used to
     be a `button-group`, and a `role="group"` of buttons gives a keyboard user
     no arrow keys and a screen reader no idea the row selects a view.

     Every panel is built once and kept, so switching costs nothing and a knob
     you set on `badge` is still set when you come back to it. */
  keys.forEach((key) => {
    const macro = MACROS[key];
    state[key] = Object.fromEntries(macro.controls.map((c) => [c.key, c.value]));

    if (!tablist) {
      buildControls(key, document.getElementById(`${slug}-controls`));
      return;
    }

    const panel = document.createElement("div");
    panel.id = `${slug}-panel-${key}`;
    panel.setAttribute("role", "tabpanel");
    /* Pre-hidden, unlike a server-rendered `tab_panel`: nothing here exists
       without JavaScript anyway, so there is no reader to keep it legible for —
       only a stack of panels flashing before Basecoat's script runs. */
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
  if (tablist) {
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
  }

  function buildControls(key, controlsEl) {
    MACROS[key].controls.forEach((control) => {
      const wrap = document.createElement("div");
      wrap.className = "field";
      // Basecoat's own knob for a control that sits beside its label.
      if (control.type === "check") wrap.dataset.orientation = "horizontal";
      const id = `mc-${slug}-${key}-${control.key}`;
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
}

/* The sections that carry knobs, in the order the page lists them — which is
   the order `ls src/fjkit/templates/ui/` prints. */
playground("button", ["button", "button_group"]);
playground("data", ["badge", "stat", "progress", "card"]);
playground("form", ["form"]);
playground("table", ["table"]);

/* ------------------------------------------------------- layout.html */
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


/* ------------------------------------------------------------- showcases
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

  centered: {
    html: () => fill(DATA.structure.centered, {
      __XS__: '<div data-tile>xs — 20rem</div>',
      __SM__: '<div data-tile>sm — 24rem</div>',
      __MD__: '<div data-tile>md — 28rem</div>',
      __LG__: '<div data-tile>lg — 32rem</div>',
      __XL__: '<div data-tile>xl — 36rem</div>',
      __PROSE__: '<div data-tile>prose — 65ch, a measure rather than a width</div>',
    }),
    jinja: `{% from "ui/layout.html" import centered %}

{% call centered("sm") %}
  {{ page_header("Sign in", "Use your work address.") }}
  {% call card() %}…{% endcall %}
{% endcall %}`,
    caption: "The width cap the rest of ui/layout.html cannot express: stack centres without capping, grid divides a width it is given, and split's numbers belong to the aside. Without it the only ways to narrow a column were max-w-sm, which fjkit check rejects, and an inline style, which it cannot see. It centres horizontally only — a card in the middle of the viewport is the shell's job, and you get it by leaving the header and footer blocks empty.",
  },

  reveal: {
    html: () => DATA.gallery.reveal,
    jinja: `{% from "ui/form.html" import input_group_field, reveal_scripts %}

{{ input_group_field("password", "Password", type="password",
                     required=true, revealable=true) }}

{% block scripts %}{{ reveal_scripts() }}{% endblock %}`,
    caption: "Live on this page — click Show. The button is markup and the script is four lines, but the two things that make it correct are not obvious: the listener is delegated from document, because the form a password sits in is the one most likely to be swapped out by a 422 and a listener bound to the old button goes with it; and the input is found through aria-controls, so nothing hard-codes the id the macro chose. reveal_scripts() is per page, never in the shell.",
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

  /* --- the gallery: one rendered example per macro that has nothing to turn.
   * `html` reads DATA.gallery, so these previews are what fjkit emitted at
   * build time — the page cannot show markup the kit does not produce. */

  spinner: {
    html: () => DATA.gallery.spinner,
    jinja: `{% from "ui/feedback.html" import spinner %}

{{ spinner(size="sm") }}
{{ spinner(size="lg", tone="primary") }}
{{ spinner(label="Saving") }}          {# label = a live region #}
{{ spinner(indicator=true) }}          {# hidden until htmx fires #}`,
    caption: "indicator=true adds htmx-indicator, so the spinner is invisible until a request is in flight. label makes it a live region; leave it off when text beside it already says what is loading.",
  },

  dialog: {
    html: () => DATA.gallery.dialog,
    jinja: `{% from "ui/feedback.html" import dialog %}

{% set confirm %}{{ button("Delete", variant="destructive") }}{% endset %}
{% call dialog("delete-7", "Delete this task?",
               "This cannot be undone.", footer=confirm) %}
  <p>The task and its history go with it.</p>
{% endcall %}

{{ button("Delete", popovertarget="delete-7") }}   {# the opener #}`,
    caption: "The Popover API, not showModal(): no JavaScript, Esc and click-outside for free. Open it from any button with popovertarget — a plain HTML attribute, so no macro of its own. Use drawer when it must be modal.",
  },

  tabs: {
    html: () => DATA.gallery.tabs,
    jinja: `{% from "ui/tabs.html" import tabs, tab_panel %}

{% call tabs([{"id": "overview", "label": "Overview"},
              {"id": "activity", "label": "Activity"}], label="Task") %}
  {% call tab_panel("overview") %}…{% endcall %}
  {% call tab_panel("activity") %}…{% endcall %}
{% endcall %}`,
    caption: "Basecoat owns which tab is selected, the roving tabindex and the arrow keys. The ids tie a tab to its panel — pass them once, in the list.",
  },

  code_block: {
    html: () => DATA.gallery.code_block,
    jinja: `{% from "ui/data.html" import code_block %}

{{ code_block(source, label="Jinja") }}
{{ code_block(source, wrap=true) }}   {# wrap instead of scroll #}`,
    caption: "tabindex=\"0\" so a keyboard can scroll it, and a visible focus ring because that is the other half of the same requirement. Escaping is Jinja's — pass a string, never Markup.",
  },

  item_list: {
    html: () => DATA.gallery.item_list,
    jinja: `{% from "ui/data.html" import item_list, item %}

{% call item_list() %}
  {% call item("Closed vocabulary") %}Every class an app may write.{% endcall %}
  {% call item("Prebuilt CSS") %}Compiled when fjkit is released.{% endcall %}
{% endcall %}`,
    caption: "A definition list in a card. clamp=false lets a description run past two lines — Basecoat clamps by default, which is right for a feed and wrong for a reference.",
  },

  alert: {
    html: () => DATA.gallery.alert,
    jinja: `{% from "ui/feedback.html" import alert %}

{{ alert("Account updated", "Your changes are live.", variant="success") }}

{% call alert("Dark mode is available") %}   {# block = the actions slot #}
  {{ button("Enable", size="xs") }}
{% endcall %}`,
    caption: "The variant picks the icon, so an alert cannot say \"destructive\" and show a tick. destructive also takes role=\"alert\", which interrupts a screen reader; every other variant is role=\"status\", which waits for a pause.",
  },

  skeleton: {
    html: () => DATA.gallery.skeleton,
    jinja: `{% from "ui/feedback.html" import skeleton %}

{{ skeleton(shape="avatar") }}
{{ skeleton(lines=3) }}                    {# last line is short #}
{{ skeleton(shape="heading", width="half") }}`,
    caption: "Upstream sizes this with utilities at the call site; here shape and width are closed lookups, because an app template may not write h-4 w-[150px]. One role=\"status\" wraps the group — six bars are one thing loading, not six.",
  },

  brand: {
    html: () => DATA.gallery.brand,
    jinja: `{% from "ui/nav.html" import brand %}

{{ brand("Acme", url_for(request, "home"), icon_name="gauge") }}
{{ brand("Acme", url_for(request, "home"),
         icon_src=url_for(request, "static", path="logo.svg")) }}`,
    caption: "icon_name draws a Lucide glyph on a bg-primary tile, so the mark follows a rebrand; icon_src places real artwork and stops following it, which is the trade a brand asset always makes. The two are mutually exclusive.",
  },

  nav_links: {
    html: () => DATA.gallery.nav_links,
    jinja: `{% from "ui/nav.html" import nav_links %}

{% block nav %}
  {{ nav_links(request, [("tasks", "Tasks"),
                         ("board", "Board"),
                         ("settings", "Settings")]) }}
{% endblock %}`,
    caption: "Route names, not URLs: the active state compares routes rather than string-matching paths, so it stays right when a URL grows a query string. Past about six destinations this is the wrong component — fill the shell's sidebar block instead.",
  },

  theme_toggle: {
    html: () => DATA.gallery.theme_toggle,
    jinja: `{% from "ui/nav.html" import theme_toggle %}

{% block header_actions %}{{ theme_toggle() }}{% endblock %}`,
    caption: "The button above is live — it toggles this page. Two inline lines rather than a file, because it has to run before any bundle would have loaded; the shell's flash-guard reads the same localStorage key on the next paint. It is the shell's default header_actions, so an app that fills that block re-adds it.",
  },

  breadcrumb: {
    html: () => DATA.gallery.breadcrumb,
    jinja: `{% from "ui/nav.html" import breadcrumb %}

{{ breadcrumb([("Board", "/"),
               ("Tasks", "/tasks"),
               ("Ship the vocabulary", none)]) }}`,
    caption: "A pair whose href is none is the current page: it renders as a span with aria-current, not a link. That is the shape of the argument, so a trail cannot be built with the current page linked to itself.",
  },

  avatar: {
    html: () => DATA.gallery.avatar,
    jinja: `{% from "ui/data.html" import avatar, avatar_group %}

{{ avatar("Ana Ruiz", badge_tone="success") }}
{{ avatar("Kai Ito", src=user.photo, size="lg") }}

{% call avatar_group(overflow=3) %}
  {{ avatar("Ana Ruiz") }}{{ avatar("Kai Ito") }}
{% endcall %}`,
    caption: "The name is the alt text and the fallback initials, so the two cannot disagree — and the initials leave the accessibility tree once an image carries the name. The badge names a role, never a hue.",
  },

  range_field: {
    html: () => DATA.gallery.range_field,
    jinja: `{% from "ui/form.html" import range_field %}

{{ range_field("weight", "Weight", value=40, output=true) }}
{{ range_field("volume", min=0, max=11, step=1) }}`,
    caption: "A native input, so keyboard and screen-reader behaviour arrive free. The filled part of the track is set here for first paint — Basecoat only updates it from JS on drag, so without it the bar disagrees with the number beside it.",
  },

  input_group_field: {
    html: () => DATA.gallery.input_group_field,
    jinja: `{% from "ui/form.html" import input_group_field %}

{% set glyph %}{{ icon("search", 16) }}{% endset %}
{{ input_group_field("q", "Search", start=glyph, end="12 results") }}`,
    caption: "start and end are rendered slots rather than a caller block, because both are optional and a block cannot say \"nothing here\" — an empty addon still takes its padding.",
  },

  collapsible: {
    html: () => DATA.gallery.collapsible,
    jinja: `{% from "ui/disclosure.html" import accordion, collapsible %}

{% call accordion() %}                    {# multiple=true: no JS at all #}
  {% call collapsible("Does it need Node?", open=true) %}
    <p>No.</p>
  {% endcall %}
  {% call collapsible("Can I edit a component?") %}…{% endcall %}
{% endcall %}`,
    caption: "A native <details>: open state, keyboard operation and the disclosure role all come from the element. accordion adds the class Basecoat watches to close the siblings; multiple withholds it, so allowing several open panels ships no JS rather than JS asked to do nothing.",
  },

  tooltip: {
    html: () => DATA.gallery.tooltip,
    jinja: `{% from "ui/disclosure.html" import tooltip %}

{% call tooltip("Saves without leaving the page", side="top") %}
  {{ button("Save", variant="outline") }}
{% endcall %}`,
    caption: "Drawn from a data-tooltip attribute and CSS content() — no second element, no JavaScript. That also means the text is not in the accessibility tree: a tooltip is a hint, never the only label a control has.",
  },

  popover: {
    html: () => DATA.gallery.popover,
    jinja: `{% from "ui/overlay.html" import popover %}

{% call popover("dimensions", "Dimensions", side="bottom", width="lg") %}
  <header><h4>Dimensions</h4></header>
  {# any content — a form, a summary, a preview #}
{% endcall %}`,
    caption: "One id in, three out: trigger, panel and the aria-controls between them. A mismatch there fails silently — the panel opens and is never announced — which is the whole reason this is a macro.",
  },

  dropdown_menu: {
    html: () => DATA.gallery.dropdown_menu,
    jinja: `{% from "ui/overlay.html" import dropdown_menu, menu_item,
                                menu_group, menu_separator %}

{% call dropdown_menu("account", "Account") %}
  {% call menu_group("My account") %}
    {{ menu_item("Profile", shortcut="⇧⌘P") }}
  {% endcall %}
  {{ menu_separator() }}
  {{ menu_item("Wrap long lines", checked=true) }}
  {{ menu_item("Log out", variant="destructive") }}
{% endcall %}`,
    caption: "menu_item switches role with the state it reports: menuitemcheckbox when checked is given, menuitemradio for radio. A menu is not a select — it runs commands and leaves nothing in a form submission.",
  },

  select_menu: {
    html: () => DATA.gallery.select_menu,
    jinja: `{% from "ui/overlay.html" import select_menu %}

{{ select_menu("theme", [("light", "Light"), ("dark", "Dark")],
               selected="dark", label="Theme") }}`,
    caption: "Prefer select_field. A native <select> is correct for free and costs one element; this is thirty and needs JS. Reach for it when a row needs markup an <option> cannot hold. The value travels in a hidden input, pre-filled so an untouched form still posts.",
  },

  combobox: {
    html: () => DATA.gallery.combobox,
    jinja: `{% from "ui/overlay.html" import combobox %}

{{ combobox("framework", options, placeholder="Select a framework") }}`,
    caption: "Filtering is client-side, over the options rendered here. For server-side search this is the wrong component — use a text_field with hx_get and swap the listbox from the response.",
  },

  /* The multiple= pair. Rendered as first paint, so the select preview shows
     its selection and the combobox preview does not — which is the difference
     worth seeing before choosing between them. */
  select_menu_multiple: {
    html: () => DATA.gallery.select_menu_multiple,
    jinja: `{% from "ui/overlay.html" import select_menu, multiselect_scripts %}

{{ select_menu("labels", label_options, selected=task.labels,
               multiple=true, width="xl", label="Labels") }}

{% block page_scripts %}{{ multiselect_scripts() }}{% endblock %}`,
    caption: "selected takes a list once multiple is on, and the trigger joins the labels onto itself. The hidden input carries Basecoat's JSON array — multiselect_scripts() re-emits it on submit as labels=bug&labels=ui, so the route stays labels: list[str] = Form([]). Forget the script and the field posts one JSON-shaped string, which is a 422 on a page that looks correctly filled in.",
  },

  combobox_multiple: {
    html: () => DATA.gallery.combobox_multiple,
    jinja: `{% from "ui/overlay.html" import combobox, multiselect_scripts %}

{{ combobox("labels", label_options, selected=task.labels,
            multiple=true, placeholder="Add a label", label="Labels") }}`,
    caption: "Same hidden input and the same script as select_menu; what differs is where the selection is shown — Basecoat draws it as chips from JS, so this preview starts empty while the select's does not. Both are worth their cost only past about a dozen options; below that a checkbox group in a fieldset posts the same thing and needs no script at all.",
  },

  drawer: {
    html: () => DATA.gallery.drawer,
    jinja: `{% from "ui/overlay.html" import drawer, drawer_trigger %}

{{ drawer_trigger("Open drawer", "goal") }}

{% call drawer("goal", "Move goal", "Set your daily target.",
               side="bottom") %}
  …
{% endcall %}`,
    caption: "A native <dialog> opened with showModal(), which is where the top layer, the backdrop, the focus trap and Esc come from. dialog is the non-modal one; mixing both open-state mechanisms in one macro would be a worse component than two clear ones.",
  },

  command: {
    html: () => DATA.gallery.command,
    jinja: `{% from "ui/overlay.html" import command, command_group, command_item %}

{% call command("palette", dialog=true) %}
  {% call command_group("Suggestions") %}
    {{ command_item("Calendar", keywords="date event schedule") }}
  {% endcall %}
{% endcall %}`,
    caption: "keywords extend the filter beyond what is on screen — the difference between a palette that finds things and one that confirms what you already typed. It binds no keystroke: which key, on which pages, and whether it beats the browser's own is the application's call.",
  },
};

/* ------------------------------------------- shell.html and sidebar.html
 * The two files with no preview to give, for opposite reasons. `shell.html`
 * *is* the page you are reading — a copy inside a card would be a second
 * document. `sidebar`'s panel is `position: fixed`, so a live one here would
 * cover the page instead of sitting in it; the rail on the left is the running
 * example, rendered by `base.html` from the call printed below.
 *
 * Same rule as everywhere else on this page: what is shown is a call, and the
 * live instance is named rather than imitated. */
const SNIPPET = {
  shell: {
    code: () => `{% extends "ui/shell.html" %}
{% from "ui/nav.html" import brand, nav_links %}

{% block site_title %}Acme{% endblock %}
{% block brand %}{{ brand("Acme", url_for(request, "home"), icon_name="gauge") }}{% endblock %}
{% block nav %}{{ nav_links(request, [("tasks", "Tasks")]) }}{% endblock %}

{% block stylesheets %}
  <link rel="stylesheet" href="{{ url_for(request, 'static', path='brand.css') }}">
{% endblock %}`,
    caption: "Your base.html, in full. The <head>, the theme flash-guard, the asset links, the toaster and the header/main/footer skeleton stay in the kit; this file is your identity and nothing structural. This site's own base.html is the same shape.",
  },

  shell_blocks: {
    /* Read out of shell.html at build time, so this list cannot offer a block
       the shell stopped having. */
    code: () => DATA.shell.blocks.map((name) => `{% block ${name} %}`).join("\n"),
    caption: "Read out of shell.html at build time, so this cannot list a block the shell stopped having. Fill sidebar and the skeleton becomes a side column plus a thin top bar — the shell tests the block for emptiness and grows a sidebar_trigger in the header on its own.",
  },

  sidebar: {
    code: () => `{% from "ui/nav.html" import brand %}
{% from "ui/sidebar.html" import sidebar, sidebar_group,
                                 sidebar_link, sidebar_submenu %}

{% block sidebar %}
  {% set mark %}{{ brand("Acme", url_for(request, "home"), icon_name="gauge") }}{% endset %}
  {% call sidebar(header=mark, label="Main") %}
    {% call sidebar_group("Workspace") %}
      {{ sidebar_link(request, "tasks", "Tasks", icon_name="list") }}
      {{ sidebar_link(request, "board", "Board", icon_name="gauge") }}
    {% endcall %}

    {% call sidebar_group("Admin") %}
      {% call sidebar_submenu("Reports", icon_name="chart-column") %}
        {{ sidebar_link(request, "report_daily", "Daily") }}
      {% endcall %}
    {% endcall %}
  {% endcall %}
{% endblock %}`,
    caption: "The rail on the left of this page is this call. Route names again, so the current page is decided by comparing routes; open=false is the desktop starting state only, because a narrow screen renders the panel as a full-screen overlay and a page that opens under its own navigation is a bug. sidebar_submenu is a <details>, so the open state and the keyboard are the browser's.",
  },

  toaster: {
    code: () => `# the route — nothing in the template
from fjkit import messages

@router.post("/tasks", name="tasks_create")
def create(request: Request, service: ServiceDep) -> BoardResponse:
    messages.add(request, "Task added", "It is at the top of the board.",
                 category="success")
    return _board(service)`,
    lang: "python",
    caption: "The shell already renders toaster() and loops fjkit_messages() into toast(), so a route raises one and no template changes. Iterating is what marks a message delivered, which is how the flash cookie gets cleared. On a response that only swapped a fragment the toaster is not in the fragment — messages sends those as HX-Trigger and the shell's listener turns the event back into a toast.",
  },
};

(function snippets() {
  Object.entries(SNIPPET).forEach(([key, item]) => {
    const code = document.querySelector(`[data-snippet-code="${key}"]`);
    if (!code) return;
    setCode(code, item.code(), item.lang ?? "jinja");
    const caption = document.querySelector(`[data-snippet-caption="${key}"]`);
    if (caption) caption.textContent = item.caption;
  });
})();

(function showcases() {
  Object.entries(SHOWCASE).forEach(([key, item]) => {
    const host = document.querySelector(`[data-showcase="${key}"]`);
    if (!host) return;
    host.innerHTML = item.html();
    setCode(document.querySelector(`[data-showcase-code="${key}"]`), item.jinja, "jinja");
    document.querySelector(`[data-showcase-caption="${key}"]`).textContent = item.caption;
  });
})();

/* --------------------------------------------------------- icon.html */
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
