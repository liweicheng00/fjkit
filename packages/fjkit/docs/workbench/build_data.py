"""Render every example on the learning page with the real fjkit Environment.

Nothing on that page is hand-drawn markup: each preview is what fjkit actually
emits, so the page cannot teach a signature the kit does not have.

Free-text and numeric parameters are rendered as literal placeholder tokens
(__LABEL__, __VALUE__ …) and substituted in the browser — Jinja prints whatever
it is handed, so the surrounding markup is still the genuine article.

    uv run python <this file>   ->  data.json
"""

from __future__ import annotations

import json
from itertools import product
from pathlib import Path

from fjkit import FjkitConfig, build_environment
from fjkit.cli.vocabulary import component_classes, emitted_classes

OUT = Path(__file__).parent / "data.json"

env = build_environment(FjkitConfig(auto_reload=False))

ICON_NAMES = [
    "plus", "trash", "check", "arrow-right", "list", "sparkle", "gauge",
    "circle-dot", "sun", "moon", "search", "pencil",
]


def render(source: str, **ctx) -> str:
    return env.from_string(source).render(**ctx).strip()


ICON_IMPORT = '{% from "ui/icon.html" import icon %}'
# Concatenated rather than interpolated: an f-string would have to escape every
# Jinja brace in the snippet, which is how these get miscopied.
ICONS = {name: render(ICON_IMPORT + '{{ icon("' + name + '") }}') for name in ICON_NAMES}
PLUS_SVG = ICONS["plus"]


def with_icon_placeholder(html: str) -> str:
    return html.replace(PLUS_SVG, "__ICON__")


# ---------------------------------------------------------------- button
BUTTON = '{% from "ui/button.html" import button %}'
VARIANTS = ["", "primary", "secondary", "outline", "ghost", "link", "destructive"]
SIZES = ["", "xs", "sm", "lg", "icon", "icon-sm", "icon-xs"]
ICON_POS = ["none", "start", "end"]

buttons: dict[str, str] = {}
for variant, size, pos, disabled in product(VARIANTS, SIZES, ICON_POS, [False, True]):
    call = (
        f'{{{{ button("__LABEL__", variant="{variant}", size="{size}", '
        f'icon_name={"\"plus\"" if pos != "none" else "none"}, '
        f'icon_end={"true" if pos == "end" else "false"}, '
        f'disabled={"true" if disabled else "false"}) }}}}'
    )
    key = f"{variant}|{size}|{pos}|{int(disabled)}"
    buttons[key] = with_icon_placeholder(render(BUTTON + call))

# ---------------------------------------------------------------- badge
DATA = (
    '{% from "ui/data.html" import badge, stat, progress, empty_state, card, '
    'metric_group, bullet_list, list_item, link, kbd %}'
)
badges = {
    v: render(f'{DATA}{{{{ badge("__LABEL__", variant="{v}") }}}}')
    for v in ["", "primary", "secondary", "outline", "destructive", "success", "warning", "info"]
}

# ---------------------------------------------------------------- stat
stats: dict[str, str] = {}
for tone, has_icon, has_hint in product(["", "success", "warning", "info", "destructive", "muted"], [0, 1], [0, 1]):
    call = (
        f'{{{{ stat("__LABEL__", "__VALUE__", '
        f'hint={"\"__HINT__\"" if has_hint else "none"}, '
        f'icon_name={"\"gauge\"" if has_icon else "none"}, '
        f'tone={f'"{tone}"' if tone else "none"}) }}}}'
    )
    html = render(DATA + call)
    if has_icon:
        gauge18 = render('{% from "ui/icon.html" import icon %}{{ icon("gauge", 18) }}')
        html = html.replace(gauge18, "__ICON18__")
    stats[f"{tone}|{has_icon}|{has_hint}"] = html

# ---------------------------------------------------------------- the rest
misc = {
    "progress": render(f'{DATA}{{{{ progress("__VALUE__", label="__LABEL__") }}}}'),
    "progress_bare": render(f'{DATA}{{{{ progress("__VALUE__") }}}}'),
    "empty_state": with_icon_placeholder(
        render(f'{DATA}{{{{ empty_state("__TITLE__", "__DESC__", icon_name="plus") }}}}')
    ),
    "metric_group": render(f'{DATA}{{{{ metric_group([("Todo", 4), ("Doing", 2), ("Done", 9)]) }}}}'),
    "kbd": render(f'{DATA}{{{{ kbd("⌘K") }}}}'),
    "link": render(f'{DATA}{{{{ link("the 20k-row report", "#") }}}}'),
    "bullet_list": render(
        f"{DATA}{{% call bullet_list() %}}"
        "{% call list_item() %}Templates are compiled once per process.{% endcall %}"
        "{% call list_item() %}A row costs a function call, not a template lookup.{% endcall %}"
        "{% endcall %}"
    ),
}

CARD_BODY = "<p>__BODY__</p>"
cards = {
    "plain": render(f"{DATA}{{% call card() %}}{CARD_BODY}{{% endcall %}}"),
    "titled": render(f'{DATA}{{% call card("__TITLE__") %}}{CARD_BODY}{{% endcall %}}'),
    "described": render(f'{DATA}{{% call card("__TITLE__", "__DESC__") %}}{CARD_BODY}{{% endcall %}}'),
    "small": render(f'{DATA}{{% call card("__TITLE__", "__DESC__", size="sm") %}}{CARD_BODY}{{% endcall %}}'),
    "actions": render(
        f'{DATA}{BUTTON}{{% set a %}}{{{{ button("__ACTION__", variant="outline", size="xs") }}}}{{% endset %}}'
        f'{{% call card("__TITLE__", actions=a) %}}{CARD_BODY}{{% endcall %}}'
    ),
    "flush": render(
        f'{DATA}{{% call card("__TITLE__", padded=false) %}}<div class="p-4">__BODY__</div>{{% endcall %}}'
    ),
}

# ---------------------------------------------------------------- layout
LAYOUT = '{% from "ui/layout.html" import stack, row, grid, split, page_header, section, divider %}'
ITEMS = "__ITEMS__"

layouts: dict[str, str] = {}
for gap in [0, 1, 2, 3, 4, 5, 6, 8]:
    layouts[f"stack|{gap}"] = render(f"{LAYOUT}{{% call stack({gap}) %}}{ITEMS}{{% endcall %}}")
    layouts[f"row|{gap}"] = render(f"{LAYOUT}{{% call row(gap={gap}) %}}{ITEMS}{{% endcall %}}")
for cols, gap in product([2, 3, 4], [2, 4, 6]):
    layouts[f"grid|{cols}|{gap}"] = render(f"{LAYOUT}{{% call grid(cols={cols}, gap={gap}) %}}{ITEMS}{{% endcall %}}")
for aside, gap in product(["sm", "md", "lg"], [4, 6]):
    layouts[f"split|{aside}|{gap}"] = render(
        f'{LAYOUT}{{% call(slot) split(aside="{aside}", gap={gap}) %}}'
        '{% if slot == "main" %}__MAIN__{% else %}__ASIDE__{% endif %}{% endcall %}'
    )

structure = {
    "page_header": render(f'{LAYOUT}{{{{ page_header("__TITLE__", "__DESC__") }}}}'),
    "page_header_actions": render(
        f'{LAYOUT}{BUTTON}{{% call page_header("__TITLE__", "__DESC__") %}}'
        f'{{{{ button("__ACTION__", variant="primary", size="sm") }}}}{{% endcall %}}'
    ),
    "section": render(f'{LAYOUT}{{% call section("__TITLE__", "__DESC__") %}}__ITEMS__{{% endcall %}}'),
    "divider": render(f"{LAYOUT}{{{{ divider() }}}}"),
}

# ---------------------------------------------------------------- table + form
TABLE = '{% from "ui/table.html" import table, cell, row_actions %}'
COLUMNS = (
    '[{"label": "Task"}, {"label": "Status"}, {"label": "Owner"}, '
    '{"label": "Points", "align": "end"}, {"width": "min"}]'
)
ROWS = [
    ("Ship the closed vocabulary", "Done", "success", "ana", 5),
    ("Write the form field set", "Doing", "info", "kai", 3),
    ("Audit focus states", "Todo", "secondary", "unassigned", 2),
]
row_src = "".join(
    f"<tr>{{{{ cell('{title}', tone='strong') }}}}"
    f"{{{{ cell(badge('{status}', variant='{variant}')) }}}}"
    f"{{{{ cell('{owner}', tone='muted') }}}}"
    f"{{{{ cell({points}, numeric=true, align='end') }}}}"
    "{% call row_actions() %}"
    f"{{{{ button('', variant='ghost', size='icon-xs', icon_name='pencil', aria_label='Edit {title}') }}}}"
    f"{{{{ button('', variant='ghost', size='icon-xs', icon_name='trash', aria_label='Delete {title}') }}}}"
    "{% endcall %}</tr>"
    for title, status, variant, owner, points in ROWS
)

tables = {
    "filled": render(
        f"{TABLE}{DATA}{BUTTON}{{% call table({COLUMNS}, rows=[1, 2, 3]) %}}{row_src}{{% endcall %}}"
    ),
    "empty": render(
        f'{TABLE}{{% call table({COLUMNS}, rows=[], empty_title="Nothing here", '
        f'empty_description="No task matches this filter.", empty_icon="list") %}}{{% endcall %}}'
    ),
}

FORM = (
    '{% from "ui/form.html" import form, field_row, text_field, select_field,'
    ' textarea_field, checkbox_field, switch_field, radio_group, fieldset %}'
)
PRIORITIES = '[("low", "Low"), ("normal", "Normal"), ("high", "High")]'
OWNERS = '[("ana", "Ana"), ("kai", "Kai"), ("unassigned", "Unassigned")]'
forms = {
    "board": render(
        f'{FORM}{BUTTON}{{% call form(action="/tasks", target="#board", reset_on_success=true) %}}'
        f'{{% call field_row("wide-then-actions") %}}'
        f'{{{{ text_field("title", label="New task", placeholder="What needs doing?", required=true) }}}}'
        f'{{{{ select_field("priority", label="Priority", options={PRIORITIES}, selected="normal") }}}}'
        f'{{{{ text_field("owner", label="Owner", placeholder="unassigned") }}}}'
        f'{{{{ button("Add", variant="primary", type="submit", icon_name="plus") }}}}'
        f"{{% endcall %}}{{% endcall %}}"
    ),
    "error": render(
        f'{FORM}{{% call form(card=true) %}}{{% call field_row("two") %}}'
        f'{{{{ text_field("title", label="Title", value="", required=true, '
        f'error="Give the task a title.") }}}}'
        f'{{{{ text_field("owner", label="Owner", value="ana", hint="Leave blank for unassigned.") }}}}'
        f"{{% endcall %}}{{% endcall %}}"
    ),
    #: The three controls a create form runs out of `text_field` for. Stacked
    #: rather than in a `field_row`, because a textarea and a checkbox want
    #: different widths and a grid would give them the same one.
    "long": render(
        f'{FORM}{LAYOUT}{BUTTON}{{% call form(card=true) %}}{{% call stack(4) %}}'
        f'{{{{ textarea_field("notes", label="Notes", placeholder="What changed, and why?", '
        f'hint="Grows with what you type — no rows to guess at.") }}}}'
        f'{{{{ checkbox_field("blocked", label="Blocked on something else", '
        f'hint="Shows a marker on the board.") }}}}'
        f'{{% call row(justify="end") %}}'
        f'{{{{ button("Save", variant="primary", type="submit") }}}}'
        f"{{% endcall %}}{{% endcall %}}{{% endcall %}}"
    ),
    #: Radios and a select over the same `options` list, side by side. The point
    #: of the pair is that swapping one for the other is a one-word edit.
    "choice": render(
        f'{FORM}{LAYOUT}{{% call form(card=true) %}}{{% call field_row("two") %}}'
        f'{{{{ radio_group("priority", label="Priority", options={PRIORITIES}, '
        f'selected="normal", hint="Three options — show them all.") }}}}'
        f'{{{{ select_field("owner", label="Owner", options={OWNERS}, selected="ana", '
        f'hint="Twelve of them — collapse the list.") }}}}'
        f"{{% endcall %}}{{% endcall %}}"
    ),
    #: A settings panel: switches grouped by subject, each group a real
    #: <fieldset> so the legend belongs to the controls under it.
    "settings": render(
        f'{FORM}{LAYOUT}{{% call form(card=true) %}}{{% call stack(6) %}}'
        f'{{% call fieldset("Notifications", hint="Applies to this board only.") %}}'
        f'{{{{ switch_field("email", label="Email me when a task moves", checked=true) }}}}'
        f'{{{{ switch_field("digest", label="Weekly digest", '
        f'hint="Monday morning, one message.") }}}}'
        f"{{% endcall %}}"
        f'{{% call fieldset("Danger zone") %}}'
        f'{{{{ switch_field("archive", label="Archive done tasks nightly", '
        f'error="Pick a retention window first.") }}}}'
        f"{{% endcall %}}{{% endcall %}}{{% endcall %}}"
    ),
}

# ---------------------------------------------------------------- live htmx
# Fragments the page's in-browser mock server hands back to real htmx requests.
# Rendered by the same macros a router would use, with placeholders where a
# server would substitute data — so the bytes htmx swaps in are fjkit's, not a
# hand-written imitation of them.
LIVE_COLUMNS = '[{"label": "Task"}, {"label": "Status"}, {"label": "Owner"}, {"width": "min"}]'

ADVANCE = (
    '{{ button("Advance", variant="ghost", size="xs", icon_name="arrow-right", icon_end=true, '
    'hx_post="/demo/tasks/__ID__/advance__QUERY__", hx_target="__TARGET__", hx_swap="__SWAP__") }}'
)
REMOVE = (
    '{{ button("", variant="ghost", size="icon-xs", icon_name="trash", '
    'aria_label="Delete __TITLE__", '
    'hx_delete="/demo/tasks/__ID____QUERY__", hx_target="__TARGET__", hx_swap="__SWAP__") }}'
)

live_row = render(
    f"{TABLE}{DATA}{BUTTON}<tr id=\"task-__ID__\">"
    '{{ cell("__TITLE__", tone="strong") }}'
    '{{ cell(badge("__STATUS__", variant="__VARIANT__")) }}'
    '{{ cell("__OWNER__", tone="muted") }}'
    f"{{% call row_actions() %}}{ADVANCE}{REMOVE}{{% endcall %}}</tr>"
)

live = {
    #: The swap target. Returned whole by every mutating route, exactly like
    #: `tasks/_board.html` — the wrapper is inside the fragment, so
    #: hx-swap="outerHTML" puts the new copy where the old one was.
    "board": render(
        f'{DATA}{TABLE}<div id="__BOARD__">'
        f'{{% call card("__COUNT__", padded=false) %}}'
        f"{{% call table({LIVE_COLUMNS}, rows=[1]) %}}__ROWS__{{% endcall %}}"
        f"{{% endcall %}}</div>"
    ),
    "board_empty": render(
        f'{DATA}{TABLE}<div id="__BOARD__">'
        f'{{% call card("__COUNT__", padded=false) %}}'
        f'{{% call table({LIVE_COLUMNS}, rows=[], empty_title="Nothing here", '
        f'empty_description="Add one with the form above.", empty_icon="list") %}}{{% endcall %}}'
        f"{{% endcall %}}</div>"
    ),
    "row": live_row,
    "form": render(
        f'{FORM}{BUTTON}{{% call form(action="/demo/tasks__QUERY__", target="__TARGET__", reset_on_success=true) %}}'
        f'{{% call field_row("wide-then-actions") %}}'
        f'{{{{ text_field("title", label="New task", placeholder="What needs doing?", required=true) }}}}'
        f'{{{{ select_field("priority", label="Priority", options={PRIORITIES}, selected="normal") }}}}'
        f'{{{{ text_field("owner", label="Owner", placeholder="unassigned") }}}}'
        f'{{{{ button("Add", variant="primary", type="submit", icon_name="plus") }}}}'
        f"{{% endcall %}}{{% endcall %}}"
    ),
    #: keyup + delay on the input itself: the field is the trigger, so no
    #: submit button and no form is involved.
    "search": render(
        f'{FORM}{{{{ text_field("q", label="Search tasks", placeholder="Type a name…", '
        f'type="search", hx_get="/demo/search", hx_trigger="keyup changed delay:400ms", '
        f'hx_target="#demo-results", hx_swap="innerHTML", hx_indicator="#demo-searching") }}}}'
    ),
    "results": render(
        f"{TABLE}{DATA}{BUTTON}{{% call table({LIVE_COLUMNS}, rows=[1]) %}}__ROWS__{{% endcall %}}"
    ),
    "results_empty": render(
        f'{TABLE}{{% call table({LIVE_COLUMNS}, rows=[], empty_title="No match", '
        f'empty_description="Nothing here is called that.", empty_icon="search") %}}{{% endcall %}}'
    ),
    "panel": render(
        f'{DATA}{{% call card("Loaded on reveal", "hx-trigger=\\"revealed\\"") %}}'
        "<p>This card was not in the page you loaded. htmx asked for it the moment it "
        "scrolled into view, and the server answered with the markup you are reading.</p>"
        "{% endcall %}"
    ),
    "status": render(f'{DATA}{{{{ badge("__STATUS__", variant="__VARIANT__") }}}}'),
    "spinner": render('{% from "ui/icon.html" import icon %}{{ icon("loader-circle", 14) }}'),
}

# ---------------------------------------------------------------- gallery
# The macros with nothing to turn: one rendered example each, which is what
# CHARTER §6 item 8 asks of every component. Rendered here rather than written
# into components.js for the reason every other preview is — the page must not
# be able to show markup the kit does not emit.
FEEDBACK = '{% from "ui/feedback.html" import spinner, dialog, alert, skeleton %}'
DISCLOSURE = '{% from "ui/disclosure.html" import collapsible, accordion, tooltip %}'
OVERLAY = (
    '{% from "ui/overlay.html" import popover, dropdown_menu, menu_item, menu_group,'
    ' menu_separator, select_menu, combobox, drawer, drawer_trigger, command,'
    ' command_group, command_item %}'
)
NAV = '{% from "ui/nav.html" import breadcrumb %}'
AVATARS = '{% from "ui/data.html" import avatar, avatar_group %}'
CONTENT = '{% from "ui/data.html" import code_block, item_list, item %}'
TABS = '{% from "ui/tabs.html" import tabs, tab_panel %}'
RANGE = '{% from "ui/form.html" import range_field, input_group_field %}'

gallery = {
    # -- the six that were owed a rendered example before this batch
    "spinner": render(
        f'{FEEDBACK}{LAYOUT}{{% call row(gap=4) %}}'
        '{{ spinner(size="sm") }}{{ spinner() }}{{ spinner(size="lg", tone="primary") }}'
        '{{ spinner(label="Saving") }}{% endcall %}'
    ),
    "dialog": render(
        f'{FEEDBACK}{BUTTON}{{% set f %}}{{{{ button("Save", variant="primary") }}}}{{% endset %}}'
        '{% call dialog("gallery-dialog", "Delete this task?", '
        '"This cannot be undone.", footer=f) %}'
        "<p>The task and its history go with it.</p>{% endcall %}"
    ),
    "tabs": render(
        f'{TABS}{{% call tabs([{{"id": "g-a", "label": "Overview"}}, '
        '{"id": "g-b", "label": "Activity"}], label="Task") %}'
        '{% call tab_panel("g-a") %}<p>What the task is.</p>{% endcall %}'
        '{% call tab_panel("g-b") %}<p>What has happened to it.</p>{% endcall %}'
        "{% endcall %}"
    ),
    "code_block": render(
        f'{CONTENT}{{{{ code_block("{{{{ button(\'Add\', variant=\'primary\') }}}}", label="Jinja") }}}}'
    ),
    "item_list": render(
        f"{CONTENT}{{% call item_list() %}}"
        '{% call item("Closed vocabulary") %}Every class an app may write.{% endcall %}'
        '{% call item("Prebuilt CSS") %}Compiled when fjkit is released.{% endcall %}'
        "{% endcall %}"
    ),
    # -- the batch that closes the Basecoat gap
    "alert": render(
        f'{FEEDBACK}{LAYOUT}{{% call stack(3) %}}'
        '{{ alert("Account updated", "Your changes are live.", variant="success") }}'
        '{{ alert("Payment failed", "Check the card and try again.", variant="destructive") }}'
        "{% endcall %}"
    ),
    "skeleton": render(
        f'{FEEDBACK}{LAYOUT}{{% call row(gap=4) %}}'
        '{{ skeleton(shape="avatar") }}'
        '{% call stack(2) %}{{ skeleton(lines=3) }}{% endcall %}'
        "{% endcall %}"
    ),
    "breadcrumb": render(
        f'{NAV}{{{{ breadcrumb([("Board", "#"), ("Tasks", "#"), ("Ship the vocabulary", none)]) }}}}'
    ),
    "avatar": render(
        f'{AVATARS}{LAYOUT}{{% call row(gap=4) %}}'
        '{{ avatar("Ana Ruiz", badge_tone="success") }}'
        '{{ avatar("Kai Ito", size="lg") }}'
        '{% call avatar_group(overflow=3) %}'
        '{{ avatar("Ana Ruiz") }}{{ avatar("Kai Ito") }}{{ avatar("Noor Haddad") }}'
        "{% endcall %}{% endcall %}"
    ),
    "range_field": render(f'{RANGE}{{{{ range_field("weight", "Weight", value=40, output=true) }}}}'),
    "input_group_field": render(
        f'{RANGE}{ICON_IMPORT}{{% set glyph %}}{{{{ icon("search", 16) }}}}{{% endset %}}'
        '{{ input_group_field("q", "Search", placeholder="Type a name…", '
        'start=glyph, end="12 results") }}'
    ),
    "collapsible": render(
        f'{DISCLOSURE}{{% call accordion() %}}'
        '{% call collapsible("Does it need Node?", open=true) %}'
        "<p>No. The stylesheet is compiled when fjkit is released.</p>{% endcall %}"
        '{% call collapsible("Can I edit a component?") %}'
        "<p>Yes — <code>fjkit eject</code> copies it into your app.</p>{% endcall %}"
        "{% endcall %}"
    ),
    "tooltip": render(
        f'{DISCLOSURE}{BUTTON}{{% call tooltip("Saves without leaving the page") %}}'
        '{{ button("Save", variant="outline") }}{% endcall %}'
    ),
    "popover": render(
        f'{OVERLAY}{LAYOUT}{{% call popover("g-pop", "Dimensions") %}}'
        "<header><h4>Dimensions</h4><p>Set the size of the layer.</p></header>{% endcall %}"
    ),
    "dropdown_menu": render(
        f'{OVERLAY}{{% call dropdown_menu("g-menu", "Account") %}}'
        '{% call menu_group("My account") %}'
        '{{ menu_item("Profile", shortcut="⇧⌘P") }}'
        '{{ menu_item("Billing", shortcut="⌘B") }}'
        "{% endcall %}"
        "{{ menu_separator() }}"
        '{% call menu_group() %}'
        '{{ menu_item("Wrap long lines", checked=true) }}'
        '{{ menu_item("API", disabled=true) }}'
        "{% endcall %}"
        "{{ menu_separator() }}"
        '{{ menu_item("Log out", variant="destructive") }}'
        "{% endcall %}"
    ),
    "select_menu": render(
        f'{OVERLAY}{{{{ select_menu("theme", [("light", "Light"), ("dark", "Dark"), '
        '("system", "System")], selected="dark", label="Theme") }}'
    ),
    "combobox": render(
        f'{OVERLAY}{{{{ combobox("framework", [("next", "Next.js"), ("astro", "Astro"), '
        '("remix", "Remix")], placeholder="Select a framework", label="Framework") }}'
    ),
    "drawer": render(
        f'{OVERLAY}{{{{ drawer_trigger("Open drawer", "g-drawer") }}}}'
        '{% call drawer("g-drawer", "Move goal", "Set your daily target.") %}'
        "<p>350 calories a day.</p>{% endcall %}"
    ),
    "command": render(
        f'{OVERLAY}{{% call command("g-command") %}}'
        '{% call command_group("Suggestions") %}'
        '{{ command_item("Calendar", keywords="date event schedule", icon_name="circle-dot") }}'
        '{{ command_item("Search tasks", keywords="find filter", icon_name="search", shortcut="⌘K") }}'
        "{% endcall %}"
        '{% call command_group("Settings") %}'
        '{{ command_item("Profile", icon_name="pencil") }}'
        '{{ command_item("Billing", disabled=true) }}'
        "{% endcall %}{% endcall %}"
    ),
}

# ---------------------------------------------------------------- vocabulary
vocab = {
    "component_classes": sorted(component_classes()),
    "emitted_classes": sorted(emitted_classes()),
}

OUT.write_text(
    json.dumps(
        {
            "buttons": buttons,
            "badges": badges,
            "stats": stats,
            "misc": misc,
            "cards": cards,
            "layouts": layouts,
            "structure": structure,
            "tables": tables,
            "forms": forms,
            "live": live,
            "gallery": gallery,
            "icons": ICONS,
            "vocab": vocab,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    ),
    encoding="utf-8",
)
print(f"{OUT}  {OUT.stat().st_size:,} bytes")
