"""The macro index behind the Cheatsheet page, as data rather than pre-formatted
text.

It used to be one string: ninety macros aligned with spaces, annotated with a
`·` no legend explained. That notation carried the fact a reader most often
needs — does this macro take a `{% call %}` block, and what goes inside it — so
the fact became a badge on the macro's own row, written out in words.

One row per macro, in one place, for both languages:

* `call` is the signature, copied from the macro definition. It is the same
  string in every language: a parameter name is not prose.
* `block` names what goes between `{% call %}` and `{% endcall %}`, or is empty
  when the macro takes no block. Two kinds of value, both plain text by the
  time a template sees them: a slot key out of `SLOTS`, which is translated,
  and a literal `macro()` name, which is not.
* `note` is the one line of prose, and the only field written twice.

`for_lang(code)` flattens all of that into what the template prints, so neither
page template reshapes anything and the two cannot describe the kit differently.
`tests/test_docs_site.py` walks `GROUPS` against the real
`src/fjkit/templates/ui/` and fails when a macro ships without a row here.
"""

from __future__ import annotations

#: The translated block slots. A key here names a role — what the block is for —
#: rather than describing the markup, which is the macro's business.
SLOTS = {
    "body": {"en": "the body", "zh": "內容"},
    "children": {"en": "the children", "zh": "子元素"},
    "actions": {"en": "the actions", "zh": "動作按鈕"},
    "buttons": {"en": "the buttons", "zh": "按鈕"},
    "fields": {"en": "the fields", "zh": "欄位"},
    "trigger": {"en": "the element it wraps", "zh": "被它包住的元素"},
    "text": {"en": "the text", "zh": "文字"},
    "panel": {"en": "the panel body", "zh": "展開後的內容"},
    "rows": {"en": "the rows", "zh": "資料列"},
    "groups": {"en": "the groups", "zh": "群組"},
    "slots": {"en": "two slots — main and aside", "zh": "兩個插槽——main 與 aside"},
    "content": {"en": "the cell content", "zh": "儲存格內容"},
}

#: Appended to a block that the macro renders only when it is given one.
OPTIONAL = {"en": " (optional)", "zh": "（可省略）"}

#: Appended to a literal `macro()` block value: the block is a run of calls to
#: that macro, not free markup.
CALLS = {"en": " calls", "zh": " 呼叫"}

#: In front of every one of them. The badge has to read on its own: a reader who
#: lands mid-page from the rail has not read the legend, and "the actions" alone
#: does not say what it is the actions of.
PREFIX = {"en": "block: ", "zh": "區塊："}


def _m(call: str, block: str = "", en: str = "", zh: str = "", optional: bool = False) -> dict:
    """Build one row. `block` is a `SLOTS` key, a literal `macro()`, or empty."""
    return {"call": call, "block": block, "optional": optional, "en": en, "zh": zh}


GROUPS = [
    {
        "id": "basics",
        "en": {
            "title": "Buttons and icons",
            "lead": "The two smallest things, and the plumbing every other macro forwards through.",
        },
        "zh": {
            "title": "按鈕與圖示",
            "lead": "最小的兩個元件，加上其他每一支 macro 都會轉手的那段管線。",
        },
        "files": [
            {
                "name": "ui/button.html",
                "macros": [
                    _m(
                        'button(label, variant="", size="", type="button", href=none,\n'
                        "       icon_name=none, icon_end=false, disabled=false)",
                        en="Passing href renders an <a> that still looks and behaves like a button.",
                        zh="傳了 href 就會渲染成 <a>，外觀與行為仍然是一顆按鈕。",
                    ),
                    _m(
                        'button_group(gap=2, orientation="horizontal")',
                        block="buttons",
                        en="Spacing only. Each button keeps its own variant.",
                        zh="只負責間距。每顆按鈕保有自己的 variant。",
                    ),
                ],
            },
            {
                "name": "ui/icon.html",
                "macros": [
                    _m(
                        'icon(name, size=16, cls="")',
                        en="1,767 Lucide names. An unknown name raises at render time rather than "
                        "drawing nothing.",
                        zh="1,767 個 Lucide 名稱。名稱不存在時會在渲染階段丟例外，而不是畫出一片空白。",
                    ),
                ],
            },
            {
                "name": "ui/attrs.html",
                "macros": [
                    _m(
                        "attrs(mapping)",
                        en="An app never calls this. Every macro ends with **kwargs and runs it "
                        'through here, which is how hx_post="/tasks" reaches the markup as '
                        'hx-post="/tasks".',
                        zh="app 不會呼叫它。每一支 macro 都以 **kwargs 收尾並交給它處理，"
                        'hx_post="/tasks" 因此在標記裡變成 hx-post="/tasks"。',
                    ),
                ],
            },
        ],
    },
    {
        "id": "layout",
        "en": {
            "title": "Layout and page structure",
            "lead": "Everything here takes a block, because a layout macro is a wrapper by "
            "definition. Reach for these before any utility class — that is the whole point of "
            "the closed vocabulary.",
        },
        "zh": {
            "title": "版面與頁面結構",
            "lead": "這一組全部吃區塊，因為版面 macro 的本質就是包裝。任何 utility class 之前先用它們——"
            "這正是封閉詞彙表存在的理由。",
        },
        "files": [
            {
                "name": "ui/layout.html",
                "macros": [
                    _m(
                        "stack(gap=4, align=none)",
                        block="children",
                        en="Vertical rhythm. The default gap for a page's bands.",
                        zh="垂直節奏。頁面各段落之間的預設間距。",
                    ),
                    _m(
                        'row(gap=3, align="center", justify=none, wrap=true)',
                        block="children",
                        en="Horizontal, and it wraps by default so a narrow screen never clips.",
                        zh="水平排列，預設會換行，窄螢幕不會被裁掉。",
                    ),
                    _m(
                        "grid(cols=3, gap=4)",
                        block="children",
                        en="cols is 2, 3 or 4. The breakpoints belong to the macro; a caller that "
                        "picks its own is how a layout vocabulary turns back into utility classes.",
                        zh="cols 只有 2、3、4。斷點屬於 macro；呼叫端自己挑斷點，"
                        "就是版面詞彙表退回 utility class 的起點。",
                    ),
                    _m(
                        'split(aside="md", gap=6)',
                        block="slots",
                        en="Called as {% call(slot) split() %}, and the block is rendered twice — "
                        'once with slot="main", once with slot="aside".',
                        zh="用 {% call(slot) split() %} 呼叫，區塊會被渲染兩次——"
                        'slot="main" 一次，slot="aside" 一次。',
                    ),
                    _m(
                        'centered(width="sm", gap=6)',
                        block="children",
                        en="The width cap the rest of this file cannot express. width is xs, sm, "
                        "md, lg, xl or prose — a sign-in card, a settings form, a page of prose. "
                        "It centres horizontally only.",
                        zh="這個檔案其他 macro 給不了的寬度上限。width 只有 xs、sm、md、lg、xl、"
                        "prose——登入卡片、設定表單、純文字頁面。只做水平置中。",
                    ),
                    _m(
                        "page_header(title, description=none)",
                        block="actions",
                        optional=True,
                        en="Called without a block it is just the title and the description. The "
                        "block is the actions slot, so buttons stay level with the title at every "
                        "width.",
                        zh="不給區塊時就只有標題與說明。區塊是動作插槽，"
                        "所以按鈕在任何寬度下都與標題齊平。",
                    ),
                    _m(
                        "section(title=none, description=none, gap=4)",
                        block="children",
                        en="One level below page_header. Use it when a page has more than one "
                        "topic on it.",
                        zh="比 page_header 低一階。頁面上不只一個主題時才需要它。",
                    ),
                    _m(
                        "divider()",
                        en="A hairline on the border token, so it survives both colour schemes. "
                        "Prefer a section heading where the split has a name.",
                        zh="用 border token 畫的細線，明暗兩套配色都成立。"
                        "如果這個分界有名字，用 section 標題更好。",
                    ),
                ],
            },
            {
                "name": "ui/sidebar.html",
                "macros": [
                    _m(
                        'sidebar(id="sidebar", label="Main", side="left", open=true,\n'
                        "        header=none, footer=none)",
                        block="groups",
                        en="Fill the shell's sidebar block with this, or its nav block with "
                        "nav_links — not both.",
                        zh="外殼的 sidebar 區塊填它，或者 nav 區塊填 nav_links——兩者擇一。",
                    ),
                    _m("sidebar_group(title=none)", block="sidebar_link()"),
                    _m(
                        "sidebar_link(request, route, label, icon_name=none)",
                        en="route is a route name, not a URL. The active state is is_active's, "
                        "so a link cannot disagree with the page it is on.",
                        zh="route 是路由名稱，不是網址。作用中狀態由 is_active 決定，"
                        "連結不可能跟所在頁面對不上。",
                    ),
                    _m("sidebar_submenu(label, icon_name=none, open=false)", block="sidebar_link()"),
                    _m(
                        'sidebar_trigger(target="sidebar", label="Toggle navigation")',
                        en="The shell already renders one in the header when a sidebar is present.",
                        zh="有 sidebar 時，外殼已經在標頭放了一顆。",
                    ),
                ],
            },
        ],
    },
    {
        "id": "data",
        "en": {
            "title": "Data display",
            "lead": "What a row, a figure or a list of things looks like. Build the list in "
            "Python — a template that zips two lists is doing the router's job.",
        },
        "zh": {
            "title": "資料呈現",
            "lead": "一列資料、一個數字、一份清單長什麼樣子。清單在 Python 裡組好——"
            "在模板裡 zip 兩個 list，是模板在做 router 的工作。",
        },
        "files": [
            {
                "name": "ui/data.html",
                "macros": [
                    _m(
                        'badge(label, variant="")',
                        en="variant is a role: success, warning, destructive, info, secondary, "
                        "outline.",
                        zh="variant 是角色：success、warning、destructive、info、secondary、outline。",
                    ),
                    _m(
                        'card(title=none, description=none, size="", actions=none, padded=true)',
                        block="body",
                        en="padded=false hands the body to the card's own edge — what a table or a "
                        "code block needs.",
                        zh="padded=false 讓內容貼到卡片邊緣——表格或程式碼區塊需要的就是這個。",
                    ),
                    _m(
                        "stat(label, value, hint=none, icon_name=none, tone=none)",
                        en="One figure. Several of them are metric_group.",
                        zh="單一數字。要放好幾個就用 metric_group。",
                    ),
                    _m(
                        "metric_group(items, cols=3)",
                        en="items is a list of (label, value) pairs.",
                        zh="items 是 (label, value) 的序對清單。",
                    ),
                    _m("progress(value, label=none)", en="value is 0–100.", zh="value 是 0–100。"),
                    _m(
                        'empty_state(title, description=none, icon_name="sparkle")',
                        en="table renders this for you when rows is empty — pass empty_title and "
                        "empty_description instead of writing the branch.",
                        zh="rows 是空的時候 table 會替你渲染它——傳 empty_title 與 empty_description，"
                        "不要自己寫那個分支。",
                    ),
                    _m('bullet_list(tone="muted")', block="list_item()"),
                    _m("list_item()", block="text"),
                    _m("item_list()", block="item()"),
                    _m(
                        "item(title, description=none, icon_name=none, actions=none,\n"
                        "     href=none, clamp=true)",
                        en="clamp=false lets a description run past two lines — what a definition "
                        "needs and a feed does not.",
                        zh="clamp=false 讓說明超過兩行——定義列表需要，動態列表不需要。",
                    ),
                    _m(
                        "avatar(name, src=none, size=\"\", initials=none, badge_tone=none,\n"
                        "       badge_icon=none)",
                        en="Initials are derived from name unless you override them.",
                        zh="沒有另外指定時，縮寫由 name 推導。",
                    ),
                    _m("avatar_group(overflow=none, label=none)", block="avatar()"),
                    _m(
                        "code_block(source, label=none, wrap=false)",
                        en="Carries the scroll region and its focusability, so a keyboard can reach "
                        "a listing that overflows.",
                        zh="它自己帶捲動區與可聚焦性，溢出的程式碼用鍵盤也到得了。",
                    ),
                    _m(
                        "caption(text=none)",
                        block="text",
                        optional=True,
                        en="A muted line that stands on its own. card, section and page_header "
                        "each render a description already, but those are bound to a heading.",
                        zh="自己站著的一行淡色說明。card、section、page_header 都能畫說明文字，"
                        "但那些都綁在標題底下。",
                    ),
                    _m("link(label, href)"),
                    _m("kbd(keys)", en="A key or a chord.", zh="一個按鍵，或一組組合鍵。"),
                ],
            },
            {
                "name": "ui/table.html",
                "macros": [
                    _m(
                        'table(columns, rows=none, empty_title="Nothing here",\n'
                        '      empty_description=none, empty_icon="list", target=none,\n'
                        '      swap="outerHTML", push_url=true, select_name="selected",\n'
                        '      select_label="Select all rows")',
                        block="rows",
                        en="columns is a list of dicts — label, and optionally align, width, "
                        "sort, sort_url or select. Passing rows lets the macro own the empty "
                        "case; pass rows=none to always render the body yourself. A column with "
                        "a sort_url becomes a sortable header, and target turns those links into "
                        "htmx swaps.",
                        zh="columns 是 dict 的清單——label，可選 align、width、sort、sort_url 或 select。"
                        "傳了 rows，空資料的情況就歸 macro 管；傳 rows=none 則永遠自己渲染 body。"
                        "有 sort_url 的欄位會變成可排序表頭，給了 target 那些連結就同時是 htmx swap。",
                    ),
                    _m(
                        "cell(value=none, tone=none, numeric=false, align=none)",
                        block="content",
                        optional=True,
                        en="Pass value for text, or omit it and use a block for markup. tone is a "
                        "closed lookup, so no colour can be passed through.",
                        zh="文字用 value，標記則省略 value 改用區塊。tone 是封閉查表，顏色傳不進來。",
                    ),
                    _m(
                        "row_actions()",
                        block="buttons",
                        en="The trailing cell, right-aligned and tight.",
                        zh="最後一格，靠右且緊湊。",
                    ),
                    _m(
                        'select_cell(value, name="selected", checked=false, label=none)',
                        en="The row half of a {\"select\": true} column. An ordinary checkbox with "
                        "an ordinary name, so the selection posts as selected=3&selected=7. Give "
                        "it a label: an id is not one.",
                        zh="{\"select\": true} 欄位在資料列這一半。就是一個普通的 checkbox 加普通的 name，"
                        "所以選取結果照 selected=3&selected=7 送出。要給 label——id 不是 label。",
                    ),
                    _m(
                        'select_count(name="selected", label="{n} selected",\n'
                        '             zero="None selected")',
                        en="The live readout of how many rows are picked. Both strings travel in "
                        "the markup, so a translated page translates them. Pass zero=none and it "
                        "hides while nothing is selected.",
                        zh="即時顯示選了幾列。兩個字串都寫在標記裡，所以翻譯頁面能翻譯它們。"
                        "傳 zero=none 則在沒有選取時自己隱藏。",
                    ),
                    _m(
                        "select_scripts()",
                        en="Loads js/select.js, which ticks the column from the header box, shows "
                        "the partial state and tints the picked rows. Per page, never the shell.",
                        zh="載入 js/select.js：從表頭的核取方塊勾選整欄、顯示部分選取狀態、"
                        "把選到的列上色。逐頁載入，不進 shell。",
                    ),
                    _m(
                        'page_size(url, per_page, options=(10, 25, 50, 100),\n'
                        '          param="per_page", keep=none, target=none,\n'
                        '          label="Rows per page", apply_label="Apply")',
                        en="A GET form, because a select on its own cannot act on a change. url must "
                        "carry no query string — a native submit throws it away — so filters travel "
                        "in keep as hidden fields. Never the page number. With a target the select "
                        "applies itself and the submit button is only rendered without scripting.",
                        zh="一個 GET form，因為單獨一個 select 沒有辦法對變更做出反應。"
                        "url 不能帶 query string——原生送出會把它整段丟掉——所以篩選要放在 keep，"
                        "以 hidden 欄位傳遞，但絕不放頁碼。給了 target，select 自己就會套用，"
                        "送出鈕只在沒有腳本時才渲染。",
                    ),
                    _m(
                        'pagination(page, pages, url, param="page", total=none,\n'
                        '           per_page=none, target=none, swap="outerHTML",\n'
                        '           push_url=true, window=1, label="Pagination")',
                        en="url is the list's address without a page parameter; the macro appends "
                        "one. Renders nothing when there is one page or fewer. Give total and "
                        "per_page together for the \"76–100 of 210\" line.",
                        zh="url 是清單的網址，不帶頁碼參數，頁碼由 macro 接上去。只有一頁或更少時不渲染。"
                        "total 與 per_page 要一起給，才會出現「76–100 of 210」那一行。",
                    ),
                ],
            },
        ],
    },
    {
        "id": "form",
        "en": {
            "title": "Forms",
            "lead": "Every field takes name, label, hint, error and id. Pass error and the field "
            "draws the message, the red ring and the aria-describedby wiring together.",
        },
        "zh": {
            "title": "表單",
            "lead": "每個欄位都吃 name、label、hint、error、id。傳了 error，"
            "欄位會一次畫出訊息、紅框，以及 aria-describedby 的接線。",
        },
        "files": [
            {
                "name": "ui/form.html",
                "macros": [
                    _m(
                        'form(action=none, method="post", target=none, swap="outerHTML",\n'
                        '     reset_on_success=false, card=true, encoding="urlencoded")',
                        block="fields",
                        en="target and swap are the htmx pair. encoding=\"json\" posts JSON, and "
                        "then the page needs form_scripts().",
                        zh='target 與 swap 是 htmx 那一組。encoding="json" 會送出 JSON，'
                        "這時頁面需要 form_scripts()。",
                    ),
                    _m(
                        "form_scripts()",
                        en="Per page, not in the shell — this is what encoding=\"json\" needs.",
                        zh='放在頁面裡，不在外殼——encoding="json" 需要的就是它。',
                    ),
                    _m(
                        'field_row(template="two", gap=3)',
                        block="fields",
                        en="Two or three fields on one line, collapsing to one column when narrow.",
                        zh="一行放兩到三個欄位，窄螢幕收成一欄。",
                    ),
                    _m(
                        "fieldset(legend=none, hint=none)",
                        block="fields",
                        en="A named group inside a form, with the legend the group needs.",
                        zh="表單裡一個具名的群組，附上該群組需要的 legend。",
                    ),
                    _m(
                        'text_field(name, label=none, value="", placeholder="", type="text",\n'
                        "           required=false, hint=none, error=none, id=none)"
                    ),
                    _m(
                        'textarea_field(name, label=none, value="", placeholder="", rows=none,\n'
                        "               required=false, hint=none, error=none, id=none)"
                    ),
                    _m(
                        "select_field(name, label=none, options=(), selected=none, id=none,\n"
                        "             blank=none, hint=none, error=none)",
                        en="options is a list of (value, label) pairs.",
                        zh="options 是 (value, label) 的序對清單。",
                    ),
                    _m(
                        'checkbox_field(name, label=none, checked=false, value="on",\n'
                        "               hint=none, error=none, id=none)"
                    ),
                    _m(
                        'switch_field(name, label=none, checked=false, value="on",\n'
                        "             hint=none, error=none, id=none)"
                    ),
                    _m(
                        "radio_group(name, label=none, options=(), selected=none,\n"
                        "            hint=none, error=none, id=none)"
                    ),
                    _m(
                        "range_field(name, label=none, value=50, min=0, max=100, step=1,\n"
                        "            hint=none, error=none, id=none, output=false)",
                        en="output=true shows the live value beside the track, from the control "
                        "itself rather than from a second source.",
                        zh="output=true 會在滑軌旁顯示即時數值，數值來自控制項本身，不是另一個來源。",
                    ),
                    _m(
                        'input_group_field(name, label=none, value="", placeholder="",\n'
                        '                  type="text", start=none, end=none, required=false,\n'
                        "                  hint=none, error=none, id=none, revealable=false,\n"
                        '                  reveal_show="Show", reveal_hide="Hide")',
                        en="start and end are the affixes — a currency symbol, a unit, a button. "
                        "revealable=true adds the Show/Hide toggle a password field wants, and "
                        "then the page needs reveal_scripts().",
                        zh="start 與 end 是前後綴——貨幣符號、單位，或一顆按鈕。"
                        "revealable=true 會加上密碼欄位需要的顯示／隱藏切換，"
                        "這時頁面需要 reveal_scripts()。",
                    ),
                    _m(
                        "reveal_scripts()",
                        en="Per page, not in the shell — this is what revealable=true needs. The "
                        "listener is on document, so the button still works in a panel a 422 "
                        "swapped in.",
                        zh="放在頁面裡，不在外殼——revealable=true 需要的就是它。"
                        "監聽器掛在 document 上，所以 422 換進來的面板裡那顆按鈕一樣能用。",
                    ),
                ],
            },
        ],
    },
    {
        "id": "nav",
        "en": {
            "title": "Navigation",
            "lead": "Route names are the currency. Nothing here takes a URL, so a moved route "
            "cannot leave a dead link behind.",
        },
        "zh": {
            "title": "導覽",
            "lead": "這裡流通的是路由名稱。沒有一支吃網址，所以搬動路由不會留下死連結。",
        },
        "files": [
            {
                "name": "ui/nav.html",
                "macros": [
                    _m(
                        'brand(label, href="/", icon_name=none, icon_src=none)',
                        en="icon_name for a Lucide glyph, icon_src for your own mark.",
                        zh="Lucide 圖示用 icon_name，自己的識別圖用 icon_src。",
                    ),
                    _m(
                        "nav_links(request, links)",
                        en="links is a list of (route, label) pairs. The header alternative to a "
                        "sidebar.",
                        zh="links 是 (route, label) 的序對清單。標頭版的 sidebar 替代方案。",
                    ),
                    _m(
                        "theme_toggle()",
                        en="The shell renders one already; call it only when you have replaced "
                        "header_actions.",
                        zh="外殼已經放了一顆；只有在你換掉 header_actions 時才需要自己呼叫。",
                    ),
                    _m(
                        'breadcrumb(trail, separator="chevron", label="Breadcrumb")',
                        en="trail is a list of (label, href) pairs, and href=none marks the current "
                        "page — the last entry, which is not a link.",
                        zh="trail 是 (label, href) 的序對清單，href=none 標示目前這一頁——"
                        "也就是最後一項，它不是連結。",
                    ),
                ],
            },
            {
                "name": "ui/tabs.html",
                "macros": [
                    _m(
                        'tabs(items, label="Tabs", selected=none, orientation="horizontal")',
                        block="tab_panel()",
                        en="items is a list of {id, label}. selected names the tab that starts "
                        "open, so the server decides it rather than a script after paint.",
                        zh="items 是 {id, label} 的清單。selected 指名一開始就打開的分頁，"
                        "由伺服器決定，而不是繪製後由腳本決定。",
                    ),
                    _m(
                        "tab_panel(id, lazy=none, on=none, include=none)",
                        block="body",
                        en="id has to match the tab's. That pairing is the whole aria contract "
                        "Basecoat's keyboard behaviour reads.",
                        zh="id 必須跟分頁的一致。這組配對就是 Basecoat 鍵盤行為所讀的整份 aria 契約。",
                    ),
                    _m(
                        'tab_panel("detail", lazy=url_for(request, "detail"),\n'
                        '          on=["task-selected"], include="[name=task_id]")',
                        block="the placeholder",
                        en="lazy is a URL: the panel fetches its own body when its tab is shown, "
                        "and the block is what stands in until it arrives. on lists the "
                        "broadcasts it follows while it is visible, include the selector for "
                        "what it sends. Not revealed — a panel hidden by display:none reports "
                        "an all-zero rect, which passes htmx's visibility test, so a revealed "
                        "panel fetches at page load.",
                        zh="lazy 是一個 URL：分頁被選到時，這個面板才去抓自己的內容，"
                        "區塊裡放的是在那之前的暫代內容。on 列出它顯示中要跟著更新的廣播，"
                        "include 是它要送出什麼的選擇器。不能用 revealed——"
                        "被 display:none 藏起來的面板回報的是全為零的矩形，"
                        "剛好通過 htmx 的可見性判斷，所以 revealed 會在頁面載入時就抓。",
                    ),
                ],
            },
        ],
    },
    {
        "id": "overlay",
        "en": {
            "title": "Overlays and disclosure",
            "lead": "Anything that opens. Basecoat owns the open/close behaviour and the shell "
            "already loads it, so these macros carry the aria contract and nothing else.",
        },
        "zh": {
            "title": "浮層與展開",
            "lead": "會打開的東西都在這裡。開闔行為是 Basecoat 的，外殼已經載好，"
            "所以這些 macro 只負責帶那份 aria 契約。",
        },
        "files": [
            {
                "name": "ui/overlay.html",
                "macros": [
                    _m(
                        'popover(id, label, variant="outline", size="", side="bottom",\n'
                        '        align="center", width="lg", icon_name=none)',
                        block="body",
                        en="Free markup in a floating panel. A menu of choices is dropdown_menu.",
                        zh="浮動面板裡放任意標記。若是一串選項，用 dropdown_menu。",
                    ),
                    _m(
                        'dropdown_menu(id, label, variant="outline", size="", side="bottom",\n'
                        '              align="start", width="default", icon_name=none)',
                        block="menu_item()",
                    ),
                    _m(
                        "menu_item(label, shortcut=none, variant=\"\", disabled=false,\n"
                        "          checked=none, radio=false, href=none)",
                        en="checked and radio give the item the matching aria role.",
                        zh="checked 與 radio 會給這一項對應的 aria 角色。",
                    ),
                    _m("menu_group(heading=none, id=none)", block="menu_item()"),
                    _m("menu_separator()"),
                    _m(
                        "select_menu(name, options=(), selected=none, id=none,\n"
                        '            placeholder="Select…", width="lg", label=none,\n'
                        "            multiple=false, close_on_select=false,\n"
                        "            visible_label=none, hint=none, error=none)",
                        en="A styled select that still posts a field. multiple=true needs "
                        "multiselect_scripts() on the page. label is an aria-label and draws "
                        "nothing; visible_label makes it a field, with the wrapper, the label "
                        "and the message line every other field has.",
                        zh="外觀受控、但仍然會送出欄位的 select。multiple=true 需要頁面上有 "
                        "multiselect_scripts()。label 是 aria-label，畫不出東西；visible_label "
                        "會讓它變成一個 field，帶上其他欄位都有的外框、標籤與訊息行。",
                    ),
                    _m(
                        "combobox(name, options=(), selected=none, id=none,\n"
                        '         placeholder=\"Select…\", empty="No results found.",\n'
                        "         label=none, multiple=false, close_on_select=false,\n"
                        "         visible_label=none, hint=none, error=none)",
                        en="select_menu with a filter box. Same multiple=true rule, same "
                        "visible_label.",
                        zh="加了篩選框的 select_menu。multiple=true 的規則相同，visible_label 也相同。",
                    ),
                    _m(
                        "multiselect_scripts()",
                        en="Per page. Without it, multiple=true posts one JSON string instead of "
                        "repeated fields.",
                        zh="放在頁面裡。少了它，multiple=true 會送出一個 JSON 字串，而不是重複的欄位。",
                    ),
                    _m(
                        'drawer(id, title=none, description=none, side="bottom",\n'
                        "       footer=none, dismissible=true)",
                        block="body",
                    ),
                    _m('drawer_trigger(label, target, variant="outline", size="", icon_name=none)'),
                    _m(
                        'command(id, placeholder="Type a command or search…",\n'
                        '        empty="No results found.", label="Command menu",\n'
                        "        dialog=false, bordered=true)",
                        block="command_group()",
                        en="dialog=true makes it the overlay palette rather than an inline list.",
                        zh="dialog=true 讓它變成浮層命令列，而不是內嵌清單。",
                    ),
                    _m("command_group(heading=none, id=none)", block="command_item()"),
                    _m(
                        "command_item(label, keywords=none, icon_name=none, shortcut=none,\n"
                        "             disabled=false, filter=none, href=none)",
                        en="keywords is what the filter box matches on beyond the label.",
                        zh="除了 label 之外，篩選框還會比對 keywords。",
                    ),
                ],
            },
            {
                "name": "ui/disclosure.html",
                "macros": [
                    _m(
                        "collapsible(summary, open=false, icon_name=none)",
                        block="panel",
                        en="One section that opens. It is a <details>, so it works with scripting "
                        "off.",
                        zh="一個會展開的段落。底層是 <details>，關掉腳本也能用。",
                    ),
                    _m(
                        "accordion(multiple=false, label=none)",
                        block="collapsible()",
                        en="multiple=false closes the others when one opens.",
                        zh="multiple=false 時，打開一個就會關掉其他的。",
                    ),
                    _m(
                        'tooltip(text, side="top", align="center")',
                        block="trigger",
                        en="A CSS ::after, so there is no second element and no script. The text is "
                        "not in the accessibility tree — a tooltip is a hint, never the only label, "
                        "and it cannot contain markup.",
                        zh="用 CSS ::after 做的，沒有第二個元素、沒有腳本。文字不在無障礙樹裡——"
                        "tooltip 是提示，不能當成唯一的標籤，而且裡面不能有標記。",
                    ),
                ],
            },
        ],
    },
    {
        "id": "feedback",
        "en": {
            "title": "Feedback",
            "lead": "What the interface says back. The variant decides the colour and, for an "
            "alert, whether a screen reader interrupts.",
        },
        "zh": {
            "title": "回饋",
            "lead": "介面回話的方式。variant 決定顏色，對 alert 來說還決定螢幕閱讀器要不要打斷。",
        },
        "files": [
            {
                "name": "ui/feedback.html",
                "macros": [
                    _m(
                        'spinner(size="default", tone="muted", label=none, indicator=false)',
                        en="indicator=true makes it an htmx indicator: hidden until the request it "
                        "belongs to is in flight.",
                        zh="indicator=true 讓它成為 htmx 的 indicator：對應的請求在途中才會顯示。",
                    ),
                    _m(
                        'alert(title, body=none, variant="", icon_name=none)',
                        block="actions",
                        optional=True,
                        en="variant=\"destructive\" gets role=\"alert\", which interrupts a screen "
                        "reader. Everything else gets role=\"status\", which waits for a pause.",
                        zh='variant="destructive" 會拿到 role="alert"，會打斷螢幕閱讀器；'
                        '其他都是 role="status"，會等到一個停頓。',
                    ),
                    _m(
                        'skeleton(shape="text", width="full", lines=1, label=none)',
                        en="shape is text, heading, control, avatar or block.",
                        zh="shape 有 text、heading、control、avatar、block。",
                    ),
                    _m(
                        'dialog(id, title=none, description=none, size="default",\n'
                        "       footer=none, dismissible=true)",
                        block="body",
                        en="A native <dialog>. The footer is a slot rather than a block, because "
                        "the body already is one.",
                        zh="原生 <dialog>。footer 是插槽而不是區塊，因為區塊已經給了內容。",
                    ),
                    _m(
                        'toaster(align="end")',
                        block="toast()",
                        optional=True,
                        en="One per page, in the shell's toasts block. Server-sent toasts arrive "
                        "through HX-Trigger.",
                        zh="每頁一個，放在外殼的 toasts 區塊。伺服器送出的 toast 走 HX-Trigger。",
                    ),
                    _m(
                        'toast(title, description=none, category="info", duration=none,\n'
                        "      action_label=none, action_href=none)"
                    ),
                ],
            },
        ],
    },
]

#: `ui/shell.html` is blocks, not macros, so it gets its own two-column table
#: rather than rows above. Listed in the order a page fills them, which is not
#: the order they appear in the file.
SHELL_BLOCKS = [
    {
        "name": "site_title",
        "en": "The product name, after the page title in <title>.",
        "zh": "產品名稱，接在 <title> 裡的頁面標題之後。",
    },
    {"name": "title", "en": "This page's title.", "zh": "這一頁的標題。"},
    {"name": "lang", "en": "The <html lang> value.", "zh": "<html lang> 的值。"},
    {
        "name": "brand",
        "en": "The mark in the header. Usually one brand() call.",
        "zh": "標頭上的識別。通常是一次 brand() 呼叫。",
    },
    {
        "name": "nav",
        "en": "Header navigation. Fill this OR sidebar, never both.",
        "zh": "標頭導覽。這個跟 sidebar 只能填一個。",
    },
    {
        "name": "sidebar",
        "en": "The rail. Fill this OR nav, never both.",
        "zh": "側邊欄。這個跟 nav 只能填一個。",
    },
    {
        "name": "header",
        "en": "The whole header bar, when the pieces above are not enough.",
        "zh": "整條標頭；上面那幾個插槽不夠用時才動它。",
    },
    {
        "name": "header_actions",
        "en": "The right-hand end of the header. Defaults to theme_toggle().",
        "zh": "標頭右端。預設是 theme_toggle()。",
    },
    {
        "name": "sidebar_trigger",
        "en": "The button that opens the rail on a narrow screen.",
        "zh": "窄螢幕上打開側邊欄的按鈕。",
    },
    {"name": "content", "en": "The page itself.", "zh": "頁面本體。"},
    {"name": "footer", "en": "Footer text.", "zh": "頁尾文字。"},
    {"name": "footer_wrapper", "en": "The footer element around it.", "zh": "包住頁尾的那個元素。"},
    {
        "name": "stylesheets",
        "en": "Your own stylesheet — token overrides and element typography.",
        "zh": "你自己的樣式表——token 覆寫與元素層級的排版。",
    },
    {"name": "head", "en": "Anything else in <head>: meta tags, og: tags.", "zh": "<head> 裡的其他東西：meta、og:。"},
    {
        "name": "toasts",
        "en": "Where toaster() goes. The shell renders one by default.",
        "zh": "toaster() 的位置。外殼預設會渲染一個。",
    },
    {
        "name": "scripts",
        "en": "Your scripts, at the end of <body>. Use defer — htmx and Basecoat are deferred too, "
        "and a plain script here would run before either.",
        "zh": "你的腳本，放在 <body> 結尾。要用 defer——htmx 與 Basecoat 也是 deferred，"
        "這裡放普通腳本會比它們先執行。",
    },
]

#: Available in every template without an import, because `build_environment`
#: puts them in the Environment's globals.
GLOBALS = [
    {
        "name": "url_for(request, name, **params)",
        "en": "A route name to a URL. Names, not paths, so a moved route updates every link.",
        "zh": "由路由名稱換到網址。用名稱不用路徑，搬動路由時每個連結都會跟著更新。",
    },
    {
        "name": "is_active(request, name)",
        "en": "True when the request is for that route. What sidebar_link marks with.",
        "zh": "這次請求指向該路由時為真。sidebar_link 用它標示作用中狀態。",
    },
    {
        "name": "fjkit_static(path)",
        "en": "A URL under the mounted static tree, stamped with ?v=<mtime> so a browser cannot "
        "serve a stale stylesheet against current markup.",
        "zh": "掛載後靜態目錄下的網址，帶上 ?v=<mtime>，"
        "瀏覽器就不會拿舊的樣式表去配新的標記。",
    },
    {
        "name": "fjkit_version",
        "en": "The versions in the footer: fjkit, fastapi, jinja2, basecoat, htmx.",
        "zh": "頁尾那幾個版本號：fjkit、fastapi、jinja2、basecoat、htmx。",
    },
    {
        "name": "fjkit_icon_path(name)",
        "en": "The raw SVG path data for a Lucide name. icon() is what a template calls.",
        "zh": "某個 Lucide 名稱的原始 SVG path 資料。模板要呼叫的是 icon()。",
    },
]

#: The htmx attributes worth having next to the macro index, because they are
#: passed to these macros — `hx_post="/tasks"` on a form, a button or a row.
#: Same row shape as a macro: what you write, then one line on what it does.
#: The full reference is upstream, and the page links to it.
HTMX = [
    {
        "id": "request",
        "en": {"title": "Which request", "lead": "The verb and the URL."},
        "zh": {"title": "送什麼請求", "lead": "動詞與網址。"},
        "rows": [
            {
                "call": 'hx-get="/tasks"      hx-post="/tasks"\n'
                'hx-put="/tasks/5"    hx-patch="/tasks/5"\n'
                'hx-delete="/tasks/5"',
                "en": "Fires the request. The response is HTML, not JSON — that is the whole "
                "difference from fetch().",
                "zh": "送出請求。回應是 HTML 不是 JSON——這就是它跟 fetch() 的全部差別。",
            },
        ],
    },
    {
        "id": "target",
        "en": {"title": "Where the answer goes", "lead": "Which element is replaced, and how."},
        "zh": {"title": "回應放到哪裡", "lead": "哪個元素被換掉，以及怎麼換。"},
        "rows": [
            {
                "call": 'hx-target="#board"        a CSS selector\n'
                'hx-target="closest tr"    the nearest ancestor\n'
                'hx-target="this"          the element itself\n'
                'hx-target="next .row"     the one after it',
                "en": "Defaults to the element that fired the request.",
                "zh": "沒寫的話，預設就是觸發請求的那個元素。",
            },
            {
                "call": 'hx-swap="outerHTML"    replace the target\n'
                'hx-swap="innerHTML"    replace what is inside it\n'
                'hx-swap="beforeend"    append   (afterbegin prepends)\n'
                'hx-swap="afterend"     insert after  (beforebegin: before)\n'
                'hx-swap="delete"       remove it   (none: change nothing)',
                "en": "Modifiers ride on the same string: swap:200ms, settle:100ms, scroll:top.",
                "zh": "修飾詞接在同一個字串上：swap:200ms、settle:100ms、scroll:top。",
            },
        ],
    },
    {
        "id": "trigger",
        "en": {"title": "When it fires", "lead": "One attribute, and each form is a different job."},
        "zh": {"title": "什麼時候觸發", "lead": "同一個屬性，每種寫法是一種不同的用途。"},
        "rows": [
            {
                "call": 'hx-trigger="click"    hx-trigger="submit"\nhx-trigger="change"',
                "en": "The defaults — a button clicks, a form submits, an input changes. Write "
                "them out only when you are adding a modifier.",
                "zh": "預設值——按鈕是 click、表單是 submit、輸入欄位是 change。"
                "只有要加修飾詞時才需要寫出來。",
            },
            {
                "call": 'hx-trigger="keyup changed delay:400ms"',
                "en": "Search as you type. changed skips the request when the value did not move; "
                "delay debounces the keystrokes.",
                "zh": "邊打邊查。changed 讓值沒變時不送請求；delay 把連續按鍵防抖。",
            },
            {
                "call": 'hx-trigger="revealed"',
                "en": "Lazy load: fires when the element scrolls into view. It tests that with "
                "getBoundingClientRect, so it is wrong for anything inside an overflow "
                "container or hidden by display:none — a hidden element reports an all-zero "
                "rect and counts as visible.",
                "zh": "延遲載入：元素捲進畫面時才觸發。它是用 getBoundingClientRect 判斷的，"
                "所以放在 overflow 容器裡、或被 display:none 藏起來的元素都不適用——"
                "隱藏元素回報的是全為零的矩形，會被判定為可見。",
            },
            {
                "call": 'hx-trigger="intersect once"\nhx-trigger="intersect threshold:0.5"',
                "en": "Lazy load through an IntersectionObserver, which reports a hidden "
                "element as not intersecting. This is the one that works in a tab panel or "
                "a scroll container. Without once it fires every time the element becomes "
                "visible again; root: and threshold: take the observer's own options.",
                "zh": "改用 IntersectionObserver 做延遲載入，隱藏的元素會被正確判定為未交會。"
                "分頁面板或捲動容器裡要用這個。不加 once 的話，每次重新可見都會觸發；"
                "root: 與 threshold: 對應 observer 自己的選項。",
            },
            {
                "call": 'hx-trigger="load"',
                "en": "Fires once, as soon as the element is inserted.",
                "zh": "元素一被插入就觸發一次。",
            },
            {
                "call": 'hx-trigger="every 2s"',
                "en": "Polling. Stop it by returning markup without the attribute.",
                "zh": "輪詢。回傳不帶這個屬性的標記就會停下來。",
            },
            {
                "call": 'hx-trigger="click from:body"',
                "en": "Listens somewhere else — a keyboard shortcut, a click outside a menu.",
                "zh": "監聽別的地方——鍵盤快捷鍵，或選單外的點擊。",
            },
        ],
    },
    {
        "id": "extras",
        "en": {"title": "What else goes with it", "lead": "Extra data, confirmation, history."},
        "zh": {"title": "還會一起送出的東西", "lead": "額外資料、確認、瀏覽紀錄。"},
        "rows": [
            {
                "call": "hx-vals='{\"id\": 3}'",
                "en": "Values sent with the request, on top of the form fields.",
                "zh": "除了表單欄位以外，一起送出的值。",
            },
            {
                "call": 'hx-include="#filters"',
                "en": "Other fields to send — a filter bar that sits outside the form.",
                "zh": "要一起送的其他欄位——例如放在表單外的篩選列。",
            },
            {
                "call": 'hx-confirm="Delete this task?"',
                "en": "A native confirm before the request fires.",
                "zh": "送出請求前先跳一個原生確認視窗。",
            },
            {
                "call": 'hx-indicator="#spinner"',
                "en": "That element gets the htmx-request class while the request is in flight. "
                "spinner(indicator=true) is already shaped for it.",
                "zh": "請求在途中時，那個元素會拿到 htmx-request class。"
                "spinner(indicator=true) 已經是為它準備好的形狀。",
            },
            {
                "call": 'hx-push-url="true"',
                "en": "Puts the URL in the address bar, so Back works.",
                "zh": "把網址推進網址列，上一頁才會正常運作。",
            },
            {
                "call": 'hx-swap-oob="true"',
                "en": "Written in a response, not on the trigger: swaps a second element by id, "
                "somewhere else on the page.",
                "zh": "寫在回應裡，不是寫在觸發端：依 id 把頁面上另一個元素也換掉。",
            },
        ],
    },
    {
        "id": "headers",
        "en": {
            "title": "Headers the route reads and writes",
            "lead": "The half of htmx that lives in Python rather than in a template.",
        },
        "zh": {
            "title": "路由讀寫的標頭",
            "lead": "htmx 的另外一半，住在 Python 裡而不是模板裡。",
        },
        "rows": [
            {
                "call": "HX-Request: true                 (request)",
                "en": "On every htmx request. How one route answers a navigation with a page and "
                "a swap with a fragment.",
                "zh": "每個 htmx 請求都會帶。同一個路由靠它決定：導覽回整頁，局部更新回 fragment。",
            },
            {
                "call": 'HX-Trigger: {"toast": {…}}       (response)',
                "en": "Fires a client event. This is how a toast raised in a route reaches the "
                "toaster in the shell.",
                "zh": "觸發一個前端事件。在路由裡發出的 toast 就是這樣送到外殼裡的 toaster。",
            },
            {
                "call": "HX-Redirect: /tasks              (response)\nHX-Refresh: true                 (response)",
                "en": "Full-page navigation, asked for by a fragment response.",
                "zh": "由 fragment 回應要求的整頁導覽。",
            },
            {
                "call": "HX-Retarget: #errors             (response)",
                "en": "Changes the target from the server — an error that belongs somewhere other "
                "than where the success would have gone.",
                "zh": "由伺服器改寫 target——錯誤訊息該去的地方，跟成功時不一樣。",
            },
        ],
    },
]


#: The two listings on the page. They live here rather than in the templates
#: because a Jinja sample is full of `{%` and `#}`, and a template that quotes
#: one inline asks the lexer to tell a string apart from a tag. Python does not
#: have that problem. The comments inside them are prose, so they are written
#: twice.
SAMPLES = {
    "shapes": {
        "en": """\
{% from "ui/data.html" import badge, card %}

{# printed — this macro takes no block #}
{{ badge("Doing", variant="info") }}

{# a block — the card renders it as its body #}
{% call card("Tasks", "Everything open right now.") %}
  <p>Anything that belongs inside the card.</p>
{% endcall %}""",
        "zh": """\
{% from "ui/data.html" import badge, card %}

{# 直接印出——這支 macro 不吃區塊 #}
{{ badge("Doing", variant="info") }}

{# 區塊——card 會把它當成內容渲染 #}
{% call card("Tasks", "目前所有進行中的事項。") %}
  <p>任何該放進卡片裡的東西。</p>
{% endcall %}""",
    },
    "shell": {
        "en": """\
{% extends "ui/shell.html" %}

{% block site_title %}Acme{% endblock %}
{% block sidebar %}{# your rail #}{% endblock %}
{% block content %}{# the page #}{% endblock %}""",
        "zh": """\
{% extends "ui/shell.html" %}

{% block site_title %}Acme{% endblock %}
{% block sidebar %}{# 你的側邊欄 #}{% endblock %}
{% block content %}{# 頁面本體 #}{% endblock %}""",
    },
}


def _slot(block: str, optional: bool, code: str) -> str:
    """Phrase the badge on a macro's row, or return empty for a macro that takes
    no block.

    Empty rather than a dash: absence is the common case, and a column of dashes
    is noise. A badge means the macro is called with a block, and says what goes
    in it.

    Two shapes, neither a notation to decode: a translated role out of `SLOTS`,
    and a literal `macro()` name when the block is a run of calls to that macro.
    """
    if not block:
        return ""
    label = SLOTS[block][code] if block in SLOTS else block + CALLS[code]
    return PREFIX[code] + label + (OPTIONAL[code] if optional else "")


def for_lang(code: str) -> dict:
    """Flatten the index into everything the Cheatsheet page prints, in one
    language.

    The page template loops and prints. It chooses no language, looks up no slot
    and assembles no phrase: that is data reshaping, and a template doing it is
    the one place the English and Chinese pages could start describing different
    macros.
    """
    return {
        #: The middle of the page's rail. The fixed bands around it — the
        #: legend, the shell, the globals, htmx — are headings the page writes
        #: for itself, so they stay in the template beside the prose they head.
        "rail": [{"id": group["id"], "title": group[code]["title"]} for group in GROUPS],
        "groups": [
            {
                "id": group["id"],
                "title": group[code]["title"],
                "lead": group[code]["lead"],
                "files": [
                    {
                        "name": file["name"],
                        "macros": [
                            {
                                "call": macro["call"],
                                "block": _slot(macro["block"], macro["optional"], code),
                                "note": macro[code],
                            }
                            for macro in file["macros"]
                        ],
                    }
                    for file in group["files"]
                ],
            }
            for group in GROUPS
        ],
        "samples": {key: sample[code] for key, sample in SAMPLES.items()},
        "shell_blocks": [{"name": b["name"], "note": b[code]} for b in SHELL_BLOCKS],
        "globals": [{"name": g["name"], "note": g[code]} for g in GLOBALS],
        "htmx": [
            {
                "id": section["id"],
                "title": section[code]["title"],
                "lead": section[code]["lead"],
                "rows": [{"call": row["call"], "note": row[code]} for row in section["rows"]],
            }
            for section in HTMX
        ],
    }
