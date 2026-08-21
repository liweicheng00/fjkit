# BACKLOG — 階段一

進度追蹤。階段二會轉成 GitHub Issues。

**目前範圍：0.1 骨架 → 0.2 表單基礎（已完成，見文末）**

---

## 0.1 骨架

### 基礎建設

- [x] uv workspace：`packages/fjkit` 以相對路徑被本 repo 依賴
- [x] 套件骨架 `packages/fjkit/src/fjkit/`
- [x] `docs/architecture.md` — 五張架構圖進版控（mermaid）
- [x] `fjkit.css` 建置管線（`fjkit build-css`，產物進 `static/dist/`，不進版控）
- [x] `fjkit check` — 封閉詞彙表檢查（白名單自動從 basecoat CSS 推導，非手維護）

### 核心

- [x] `templating.py` — `Templates`、`ChoiceLoader`（app 優先）
- [x] `mounting.py` — `mount_ui(app)`
- [x] `config.py` — 純 dataclass，不用 pydantic-settings
- [x] `icons.py` — 結構完成，路徑資料在 Python 不在 Jinja
- [x] Lucide 全套 vendoring — 1,767 個 icon，lazy-load JSON（首次 1.6 ms，之後 0.26 µs/次）

### 模板

- [x] `ui/attrs.html` — 搬移
- [x] `ui/icon.html` — 搬移
- [x] `ui/shell.html` — 從 `base.html` 抽出通用殼
- [x] `ui/nav.html` — `brand`／`nav_links`／`theme_toggle`
- [x] `ui/layout.html` — `stack`／`row`／`grid`／`split`／`page_header`／`section`／`divider`
- [x] `ui/button.html` — 搬移 + `button_group`
- [x] `ui/data.html` — 搬移 + `metric_group`／`bullet_list`／`link`／`kbd`／card actions slot
- [x] `ui/form.html` — 搬移 + `form`／`field_row`（欄位已預留 `error` 參數給 0.3）
- [x] `ui/table.html` — `table`／`cell`／`row_actions`
- [x] `ui/feedback.html` — `spinner`、`dialog`（兩者皆 **0.6 提前落地**，理由見下方）
- [x] `ui/sidebar.html` — `sidebar`／`sidebar_group`／`sidebar_link`／`sidebar_submenu`／`sidebar_trigger`（**0.5 提前落地**，理由見下方）

### 詞彙表缺口（從既有模板盤出來的）

現有模板裡每一段原生 utility class，都要有對應的元件。這張表是驗收清單：

| 原生寫法 | 出處 | 對應元件 |
|---|---|---|
| `flex flex-wrap items-end justify-between gap-4` + h1 + p | tasks/page, dashboard/page, report | `page_header(title, description)` |
| `space-y-4` | _board, _stats, dashboard | `stack(gap)` |
| `flex flex-wrap gap-1.5` | _board, _stats, dashboard | `row(gap, wrap, align, justify)` |
| `grid gap-4 sm:grid-cols-2 lg:grid-cols-4` | dashboard | `grid(cols, gap)` |
| `grid gap-6 lg:grid-cols-[1fr_19rem]` | _board, dashboard | `split()` — 主欄 + 側欄雙 slot |
| `table-container border-t` + `table` + `th w-px` | _board, dashboard, report | `table(columns)` |
| `card > header.flex items-center justify-between` | _board, dashboard | `card` 加 actions slot |
| `dl.grid grid-cols-3` + `bg-muted/60 rounded-lg` + dt/dd | _stats | `metric_group(items)` |
| `ul.text-muted-foreground space-y-2 text-sm` | dashboard | `bullet_list(items)` |
| `a.text-foreground underline underline-offset-4` | dashboard | `link(label, href)` |
| `form.card` + `section.grid sm:grid-cols-[...]` | _board | `form()` + `field_row()` |
| `td.tabular-nums` / `th.w-16` | report | `table` 的欄位規格（align／width／tone） |

**Basecoat 元件 class（`btn`、`card`、`badge`、`table`、`input`、`kbd`…）不算違規**——違規的是 Tailwind utility class。這個區分是 `fjkit check` 的核心。

### 驗收

- [x] `examples/board` 完全不寫原生 utility class 就能重寫出來
- [x] `fjkit check` 在其上通過（7 個模板，0 違規；同一支檢查器在舊 `app/templates` 上抓到 258 個違規）
- [x] 所有路由渲染正常，htmx 屬性／target／表單欄位與舊版一致

### 0.1 剩餘

- [x] 套件測試 `packages/fjkit/tests/` — 52 個，含元件契約、詞彙表、loader 覆寫、icons
- [x] `ruff` 加進 dev 依賴，全部通過
- [x] CSS 預算改以 gzip 管制（已獲核可）
- [ ] 手動驗證：深淺色、鍵盤 tab 順序、窄螢幕（需要人眼）

---

## 記錄

| 日期 | 事項 | CSS raw | CSS 壓縮後 | 備註 |
|---|---|---|---|---|
| 2026-08-16 | 階段一啟動，workspace 建立 | — | — | 基準：舊 `app.css` 228,187 bytes |
| 2026-08-16 | 0.1 骨架 + 元件 + demo 重寫 | 230,199 (224.8 KB) | 23,796 gzip / 18,739 brotli | 預算已改以 gzip 管制，23.2 / 28 KB |
| 2026-08-17 | `ui/feedback.html` 的 `spinner` + `jobs` demo | 230,620 (225.2 KB) | 23,934 gzip | **+421 raw / +138 gzip**，23.4 / 28 KB。增量是 `animate-spin`／`@keyframes spin`／`sr-only`／`inline-flex` 與 reduced-motion 區塊 |
| 2026-08-18 | `ui/feedback.html` 的 `dialog` + jobs 詳情面板 | 230,838 (225.4 KB) | 23,988 gzip | **+218 raw / +54 gzip**，23.4 / 28 KB。只有兩條 `sm:max-w-*` 與一條 `overflow-y-auto`——`.dialog` 的樣式本來就在 basecoat 裡，正好是第 7 節「棘輪已經扣完」那個推論的驗證 |
| 2026-08-18 | `ui/sidebar.html` + demo 改用側欄外殼 | 231,586 (226.2 KB) | 24,090 gzip | **+748 raw / +102 gzip**，23.5 / 28 KB。全部是 `--sidebar-*` 那 16 條 token；`.sidebar` 的樣式本來就在 basecoat 裡，模板沒帶進任何新 utility |
| 2026-08-19 | 刪掉 `templates/ui/basecoat/` 的 9 個上游 Jinja macro | 233,863 (228.4 KB) | 24,410 gzip | **−186 raw / −39 gzip**，23.8 / 28 KB。同一份原始碼帶著那些檔案編是 234,049 / 24,449——它們沒被任何地方 import，卻落在 `@source "../../templates"` 的掃描範圍內，替永遠不會渲染的標記留了 utility。同列的絕對值比上一列高，是因為 tabs 元件那批工作沒進表 |
| 2026-08-21 | 0.2 表單基礎：`textarea_field`／`checkbox_field`／`switch_field`／`radio_group`／`fieldset` | 234,335 (228.8 KB) | 24,487 gzip | **+472 raw / +77 gzip**，23.9 / 28 KB。五支欄位的樣式本來就在 basecoat 的 `checkbox`／`radio`／`switch`／`textarea`／`field` 裡，模板只是開始寫出對應的標記；增量全在 `data-orientation` 那幾條 `:has()` 與 `[role=radiogroup]` 的 grid 上 |

### 載入指示提前（2026-08-17，使用者指定）

`spinner` 在路線圖上屬於 **0.6 回饋層**，這次提前做（路線圖順序的調整，由使用者
直接指定，非我自行決定）。理由與代價：

- htmx 讓「請求在飛」變成第一週就會遇到的狀態。沒有元件，app 只能自己寫 `<svg>`——
  那同時是顏色字面值和封閉詞彙表外的動畫，正好是 `fjkit check` 要擋的東西。
- `packages/fjkit/docs/workbench/page.template.html:477` 原本就寫著「fjkit ships no
  indicator CSS yet (roadmap 0.6)」，自己手刻了 `.t-spin`／`.t-indicator`。這次落地
  之後那段註解已經不成立。
- **沒有動到 `htmx-indicator` 的 CSS**：htmx 自己會注入 show/hide 規則
  （`includeIndicatorStyles` 預設為真），所以 fjkit 一行 CSS 都不必補。
- 0.6 其餘的 `alert`／`toast`／`dialog`／`skeleton` 沒有提前，仍在 0.6。

**未做，需要人決定**：workbench（`page.template.html` 的 `MACROS` 與
`build_data.py` 的 `misc`）還沒加 spinner 條目，因為那兩支檔案目前有未 commit 的
編輯中內容（新的 Lesson 08 patterns）。元件完成定義的「文件頁」這一項因此尚未打勾；
`packages/fjkit/docs/components.md` 與 `htmx.md` 已經寫好。

### `dialog` 提前（2026-08-18，使用者指定）

同樣是 **0.6 回饋層** 提前落地（路線圖順序的調整，由使用者直接指定）。設計上的取捨：

- **零 JavaScript，用 Popover API。** `popovertarget` 開、
  `popovertargetaction="hide"` 關，都是純 HTML 屬性；top layer、backdrop、Esc、
  點外面關閉、焦點回到觸發元素全部由瀏覽器負責。fjkit 一行 JS 都沒加，也就不必動到
  「引入自己寫的 JavaScript 要先問人」那條界線。
- **代價是「不是 modal」。** popover 不會把背景 inert，Tab 與螢幕閱讀器仍然到得了
  後面的頁面，所以標的是 `role="dialog"` 而**不寫** `aria-modal`——寫了就是對螢幕
  閱讀器說謊。真正的 modal 需要 `showModal()`，那是要不要出貨 JS 的決定，留給人類。
  「確定要刪嗎」這種一定不能被繞過的情境，繼續用 `hx-confirm`（那個是瀏覽器自己的
  modal）。
- **CSS 幾乎沒動**：`.dialog` 的樣式 basecoat 早就出貨了，只補兩個 `data-size`
  寬度（延伸 basecoat 既有的屬性 API，不新增 class）與 body 的 `overflow-y-auto`。
- **`<div popover>` 而不是 `<dialog popover>`**：沒有任何東西會呼叫 `showModal()`，
  用真的 `<dialog>` 只是把兩套開關狀態混在一起。basecoat 的 `.dialog` 是 class
  選擇器，`:popover-open` 那條規則上游本來就寫了。

實作時在瀏覽器裡抓到一個不會有任何錯誤訊息的 bug，已修並補了回歸測試：
**htmx 的 `hx-swap` 會從祖先繼承**。Details 按鈕長在會每秒替換自己的卡片裡，而那張
卡片帶著 `hx-swap="outerHTML"`；繼承下來就會把 dialog 的 `<section id="…-body">`
整個換掉、連 id 一起帶走——第一次打開正常，之後每次都填不進東西。觸發元素巢狀在
另一個 htmx 元素裡時，`hx-swap` 一定要自己寫明。

**未做，同一個理由**：workbench 也還沒加 `dialog` 條目。

### `sidebar` 提前（2026-08-18，使用者指定）

**0.5 應用外殼** 的第一件，提前落地（路線圖順序的調整，由使用者直接指定）。

- **成本只有模板。** `.sidebar` 的 CSS basecoat 早就出貨（CSS 預算那個「棘輪已經扣完」的
  推論第三次被驗證），JS 也在 vendored 的 `all.min.js` 裡。所以這次新增的不是元件，
  是 fjkit 形狀的門：路由名而不是 URL、icon 用名字、封閉列舉、簽名裡沒有 class 字串。
- **shell 用「block 是不是空的」切換版型。** Jinja 問不到一個 block 有沒有被填，
  所以 `ui/shell.html` 先把 `{% block sidebar %}` 收進變數再判斷。代價是側欄的標記
  會先進 buffer（幾百 bytes）；換到的是 app 只要填那個 block 就好，不必再記得多設
  一個旗標——會被忘記的旗標等於沒有。
- **相鄰性是 shell 的責任。** basecoat 把讓開的 margin 給 `.sidebar + *`，所以內容
  wrapper 必須是 aside 的**下一個兄弟**。中間插任何東西，margin 就落在錯的元素上，
  頁面滑到側欄底下——沒有錯誤訊息。同理那個版型不能用 `mx-auto max-w-6xl`：`mx-auto`
  是 utility，basecoat 的 margin 是 components layer 的 `@apply`，utility 會贏。
  兩件事都由 shell 寫死，並各有一條測試守著。
- **group 用 `aria-label` 而不是 `aria-labelledby`。** 後者要每個 group 生一個 id，
  而同一個側欄可能在一頁裡出現兩次（htmx 換掉一份），重複的 id 會讓 `aria-labelledby`
  指到**錯的**標題，比指不到還糟。
- **`--sidebar-*` 改指向既有的中性色**（`var(--card)`／`var(--border)`／`var(--accent)`…）。
  basecoat 把它們定義成純灰，貼在帶著品牌色調的頁面旁邊看得出來，深色模式尤其明顯。
  改掉之後 A3 仍然成立：一顆旋鈕連側欄一起換。`:root` 與 `.dark` 各寫一份——basecoat
  自己的 `.dark` 會把 `:root` 的定義蓋掉。
- **唯一的 JS 是 trigger 的 `onclick`**，呼叫 basecoat 自己掛在元素上的 `toggle()`，
  跟 `theme_toggle` 同一個形狀。沒有新增任何 fjkit 自己的邏輯，但這條靠近「不自己寫 JavaScript」那條界線，
  記在這裡讓人類看得到。

**demo 的 parity**：`ids` 是 exact 欄位（id 就是 htmx target，靜靜多一個或改名正是
swap 落錯地方的起點），所以側欄那個 `sidebar` id 是逐條寫進 `ALLOWED_CONTRACT_DRIFT`
的，不是開一條規則放行。文字與連結一個都沒少——導覽只是從 header 搬到側欄。

**未做**：workbench 的條目（跟 `dialog` 同一個理由）。

### demo 的 style picker（2026-08-19，使用者指定）

八個風格包全部進 wheel 之後，要比較它們得改 `FjkitConfig(style=...)` 再重啟。demo
的 header 因此多了一顆下拉，**這是 demo 的東西，不是 kit 的**：

- **伺服器端一個位元組都沒變。** `FjkitConfig.style` 仍然是每個 process 一個包，
  shell 仍然 link `fjkit-vega.css`。換掉的是瀏覽器裡那個 `<link>` 的 href，所以
  config.py 那句「style 不是 per-request 的值」仍然成立——同一頁從來不會有兩份
  stylesheet。
- **手寫 JS——需要人類授權的那一類，由使用者直接指定。** 15 行，全在 `examples/board` 的
  `base.html`，套件裡一行都沒加。放在 `head` 而不是 body 尾巴：跟 shell 的深色
  flash-guard 同一個理由，晚一步套用就是看得見的幾何閃動。
- **包名對 URL 的對照表由 Python 建**（`main.py` 的 `STYLE_SHEETS`），JS 只做查表。
  查不到就不換——`localStorage` 裡的髒值因此變成「維持原樣」而不是「唯一那份
  stylesheet 404、整頁失去樣式」。已在瀏覽器裡驗過這條路徑。
- **不是 `select_field()`。** 那支 macro 建的是表單欄位（label、hint、`.field` 會把
  控制項撐滿寬度），而這顆下拉不送出任何東西。裸 `select.select` 上游本來就給了
  `w-fit` 與 chevron，`data-size="sm"` 也是既有的屬性 API。
- **CSS 沒有重建的必要**：build 掃的是 `packages/fjkit` 的模板，不是 demo 的，而
  `.select` 的樣式 basecoat 早就出貨。預算數字不動。
- **parity 沒有新增豁免**：下拉沒有 `name` 也沒有 `id`，所以 `fields`／`ids` 兩個
  exact 欄位不受影響，`ALLOWED_CONTRACT_DRIFT` 一行都沒加。守著它的是
  `tests/test_styles.py`：八個選項都要有人服務、預選的那個要等於 shell 真的 link
  的那個、htmx 的 partial 不能夾帶第二顆。

### demo 的 charts 頁 / Plotly（2026-08-20，使用者指定）

問的是「可以整合 Plotly.js 嗎」。答案分兩層，這一筆記的是第二層怎麼做的。

- **不進 wheel，進 app。** 品質預算把使用者端 JS 封在 htmx + basecoat；
  `plotly.js-basic-dist-min@3.7.0` 是 1,119,926 bytes，完整包 4,851,164——差兩個
  數量級，不是預算裡放得下的東西。所以它 vendored 在 `examples/board/app/static/`，
  由 `scripts/vendor_plotly.py` 釘版本，跟 kit vendored htmx 是同一套規矩：committed、
  離線跑得起來、瀏覽器載什麼在 diff 裡看得到。只有 charts 頁 `{% block scripts %}`
  載它，其他頁一個位元組都不付。
- **送出去的就是 Plotly 的 figure，但裡面不含顏色。** `figure: PlotlyFigure`／
  `roles: list[ChartRole]` 兩個欄位並排：前者是 `plotly.py` 產的 `data` + `layout`，
  後者說每個 series 是什麼意思。瀏覽器在畫的時候才把 role 解析成當下的 token
  （`static/js/charts.js`）。因此深色模式是重畫而不是第二份 figure，htmx 端點對一個
  URL 只有一個答案。分工一句話講完：**Python 決定形狀，JavaScript 決定顏色**。
- **`dict[str, Any]` 和封閉 spec 之間選了中間點。** `PlotlyTrace` 把這個 app 真的會讀
  的欄位型別化（`type` 是 `Literal["bar","scatter","pie"]`），其餘走 `extra="allow"`
  的尾巴——OpenAPI 誠實地報 `additionalProperties: true`，而不是聳肩。
  代價寫在 schemas.py 的 docstring 裡：**尾巴擋不住顏色**，`#1F77B4` 是完全合法的
  `str`。所以 `test_no_figure_on_the_page_contains_a_colour` 從「有比較好」升級成必要
  條件——它掃的是**算完的 JSON**，不管位元組從哪個欄位來。另外補了結構性的一條
  （`marker` 裡不得有 `color`／`colors`），因為 regex 抓不到 `"red"` 這種具名色。
- **`figure_of()` 會把 `template` 拔掉。** `plotly.py` 就算 `template=None` 也會寫一個
  進去，而**預設的 template 是 7,621 bytes、裡面有 111 個色值字面值**（實測），全是
  這頁不畫的 trace 的 colorscale。拔掉之後三張圖的 payload 是 290／460／408 bytes。
- **整數刻度改由 Python 決定。** Plotly 會把一個計數標成「1.5」。哪些刻度合法是關於
  資料的事實不是畫法，所以由手上有資料的那邊算一次（`_integer_axis`），而不是讓畫的
  那邊各自再推一次——那正是兩個渲染器會漂移的地方。
- **量過才發現的一件事：`fillStyle` 來回不會把 oklch 轉成 rgb。** 原本用的是經典招式
  ——把值指給 canvas 的 `fillStyle` 再讀回來，靠瀏覽器正規化成 `#rrggbb`。它只對
  legacy 格式成立；CSS Color 4 的顏色函式會**原樣保留**，`oklch(0.72 0.15 275)` 進、
  `oklch(0.72 0.15 275)` 出。Plotly 用的是 tinycolor2，不認識 oklch，於是**不報錯**，
  直接改用自己的預設調色盤畫。三張圖都畫得好好的，只是顏色全是 Plotly 的
  `rgb(31,119,180)`／`rgb(255,127,14)`／`rgb(44,160,44)`。
  改成畫一個 1×1 像素再 `getImageData` 讀回 sRGB 位元組——那條路對任何瀏覽器解析得了
  的記法都成立，順便就是正確的色域裁切（Plotly 吐的 SVG 本來就是 sRGB）。
  **這個 bug 沒有任何測試會抓到，也沒有截圖抓得到**，除非你知道 fjkit 的 primary
  應該長什麼樣。是逐元素比對 headless Chrome 的 DOM 才看出來的。
- **第二件量出來的事：Plotly 的圓餅 `textfont` 預設 #444，不繼承 `layout.font`。**
  切片上的數字因此在深色模式下是深灰壓在飽和色上。沒有補一套 per-role foreground
  token（basecoat 根本沒有 `--destructive-foreground`），而是把標籤移到切片外——放在
  卡片上，那裡只有一個前景色，而它已經解析好了。
- **先做了自訂的封閉 spec，再換成 Plotly 的 figure。** 第一版是自己的
  `Spec`／`Trace`／`TraceKind`，`charts.js` 裡有一張 spec→Plotly 的對照表。換掉的理由
  是：一旦把真的會用到的欄位型別化，那份 spec 就收斂成「換了名字的 Plotly」——
  `kind` 對 `type`、`x`/`y` 一模一樣——差別只剩尾巴開不開。開尾巴才拿得到整個
  函式庫，而尾巴唯一的風險（顏色）本來就是測試在守，不是型別在守。
  自訂 spec 真正的價值在「將來會有第二個渲染器（伺服器端 SVG）」那天才兌現，
  那天還沒到。
- **role 整套移除，六張圖全部用 Plotly 預設調色盤（2026-08-21，使用者指定）。**
  `ChartRole`、`Chart.roles`、`data-roles`、`charts.js` 的 `paint()` 全部刪掉。
  我先只把新的三張改成預設色並保留狀態色（理由是 A3：「綠色代表完成」要撐過改品牌），
  使用者明確指示那三張也一起改，照辦。
  **保留下來的是外框**：軸文字、格線、圓餅切片間隙與標籤仍然從 token 解析。那些是
  卡片的屬性不是序列的屬性，而 Plotly 對它們的預設是 `#444` 文字配 `#eee` 格線——
  為白底畫的圖，放在可能是深色的頁面上。所以主題切換仍然重畫，重畫的是外框。
  `palette()` 那段 1×1 canvas 轉 oklch 的程式碼因此還在，只是從六個 role 縮成三個
  外框色。
  **代價**：資料色不隨主題變，深淺兩色模式的圖表顏色一模一樣。
  **沒有改變的**：figure 裡仍然一個顏色都沒有，掃色值那兩條測試原封不動繼續有效。
- **文案裡指名顏色的那一句壞了。** `workload` 的說明本來寫「a tall bar of grey is a
  queue」——role 拿掉之後灰色就不存在了，句子變成假的。改成不指名顏色的講法。
  這是「調色盤不是自己的」最便宜的一種代價，也是唯一沒有任何測試抓得到的一種：
  只有把頁面看過一遍才會發現。
- （已作廢的中間版本）**`roles` 曾經改成可選，六張圖分兩種。**
  有語意的三張（狀態、堆疊、趨勢）給 role，顏色從 token 解析，跟著主題走；沒語意的
  三張（owner 佔比、intake、最舊未完成）不給，Plotly 用自己的調色盤。判準寫在
  `Chart.roles` 的註解裡：**四個 owner 就是四個 owner，沒有哪個 role 屬於「kai」，
  硬指派一個等於讓圖表宣稱資料沒說的事**。代價也寫下來了——那三張不跟著深色模式變。
  狀態色沒有一起拿掉是因為 A3：「綠色代表完成」要能撐過改品牌，那是刻意保護的。
  **仍然照樣不變的**：figure 裡一個顏色都沒有，兩種圖都是。切片間隙與標籤文字也照樣
  跟著 token——它們是卡片的屬性不是序列的屬性。
- **頁面上那句說明有兩處是錯的，已改。** 「The figures name a role」——改成 B 之後
  figure 裡沒有 role 了；「and the style picker」——**八個風格包在 `styles/*.css` 裡
  一個顏色 token 都沒定義**（查證過），它們只差幾何，所以換包不可能改變圖表讀到的顏色。
  `charts.js` 的註解寫的正是這件事，頁面上卻寫了相反的話。兩句都留了註解說明為什麼
  不要再寫一次。
- **加一張水平長條圖，逼出了型別的一個錯誤假設。** `x: list[str]`／`y: list[float]`
  看起來很對，直到第一張 `orientation="h"`——Plotly 的 `x`／`y` 是**軸**，不是「類別」
  和「數值」，水平長條把數字放 `x`、標籤放 `y`。兩邊都放寬成 `list[str | float]`。
  這是整個模組在講的那件事的縮小版：**別人 schema 的型別化子集是一個猜測，尾巴是
  猜錯時不會致命的原因**。`orientation` 和 `hovertemplate` 本身就是走尾巴的，
  `test_the_typed_subset_survives_a_horizontal_bar` 守著這條路真的通。
- **刪掉一條自己發明的測試。** 本來寫了「每個 `ChartRole` 都要有圖用到」，套用「封閉列舉的每個值都渲染一次」。
  那條規矩是給元件的封閉參數用的，套到 app 的領域列舉上會**為了湊滿列舉而逼出圖表**，
  方向反了。role 的 token 缺漏本來就有 `test_every_role_the_server_can_send_has_a_token`
  在守。
- **驗證是在真的瀏覽器裡跑的**，用 CDP 驅動 headless Chrome：三張圖都畫出來、翻
  `.dark` 之後線色從 `rgb(138,155,255)` 變成 `rgb(78,86,211)`（就是兩個主題的
  `--primary`）、htmx swap 之後三張都重新初始化且 x 軸換成 priority、`hx-push-url`
  有更新網址。swap 出去的那半邊（`Plotly.purge`）掛在 `htmx:beforeCleanupElement`
  上——圖表放在 partial 裡最常忘的就是這一半。
- **`test_conventions.py` 那條 `app/static` 不得存在改了。** 它的 docstring 講的是
  stylesheet 與建置步驟，斷言卻是整個目錄。改成斷言真正的不變量：`app/` 底下沒有
  任何 `.css`、repo 裡沒有 `package.json`、沒有 `node_modules`。另外加一條——
  `static/vendor/` 底下的每個檔案都要有腳本說得出它從哪來。
- **CSS 預算與 parity 都沒動。** build 掃的是 `packages/fjkit` 的模板不是 demo 的，
  而且模板一個新 class 都沒寫（`fjkit check` 18 個模板 0 違規）。parity 的三個 probe
  是 `/`、`/tasks`、`/tasks/report`，側欄多一條連結只增加 href 與字詞（增加是允許的），
  那三頁沒有新的 id，`ALLOWED_CONTRACT_DRIFT` 一行都沒加。

### CSS 體積：實測與問題

拆解量測（把各個 `@source` 拿掉分別重建）：

| 組成 | raw |
|---|---|
| 只 import basecoat，不掃任何模板 | 222,050 |
| 加掃 fjkit 模板 | 230,119（+8 KB） |
| 加掃 basecoat JS | 230,199（+80 bytes） |

**結論：224.8 KB 裡有 217 KB 是 basecoat 本身，跟我們寫了多少元件無關。**

原因：`basecoat.css` → `basecoat-vega.css` → `base/base.css` + 全部 38 個元件 +
`styles/vega.css`（677 條 `@apply`）。`@layer components` 是 author CSS，Tailwind
不做 tree-shaking，所以 38 個元件的樣式一律出貨。

沒有便宜的裁剪路徑：`styles/vega.css` 是單一檔案涵蓋所有元件，要拆就得手改
vendored 檔案——那是明文禁止的。

兩個重要推論：

1. **原訂的 100 KB raw 上限從一開始就不可能達成**，那是我在量測前寫的數字。
2. **「只增不減的單向棘輪」這個擔憂大致是錯的**——棘輪已經扣完了。之後補
   `tabs`、`dialog`、`accordion` 等元件，CSS 幾乎不會變大，因為它們的樣式已經在裡面了。
   還會成長的只有我自己模板用到的 utility，實測整批模板才 8 KB。

**參考點**：Bootstrap 5 minified 約 232 KB raw / 30 KB gzip。我們 224.8 KB raw /
23.2 KB gzip / 18.3 KB brotli——線上傳輸量比 Bootstrap 小。

**已核可的處置**（2026-08-16）：預算改以 **gzip** 為管制數字（stdlib 就能量、可重現、
不需額外依賴），brotli 當參考值。品質預算已更新為 gzip ≤ 28 KB、raw ≤ 260 KB（防暴衝用）。
`fjkit build-css` 每次建置都會印出兩個數字並在超標時回傳非零。

---

## 渲染效能：實測與待決

用相同路由比較舊 `app/` 與 `examples/board`（median of 60）：

| 路由 | 舊 | 新（初版） | 新（guard 後） |
|---|---|---|---|
| `/` | 1.43 ms | 1.77 ms (+23%) | 1.76 ms (+23%) |
| `/tasks` | 2.13 ms | 2.30 ms (+29%) | 2.35 ms (+10%) |
| `/tasks/board` | 1.61 ms | 2.43 ms (+51%) | 2.00 ms (+24%) |
| `/tasks/report?rows=2000` | 46.5 ms | 71.3 ms (+49%) | 51.2 ms (+10%) |

### 已修：`attrs(kwargs)` 未加保護

微基準（2000 列 × 2 個 cell）：

| 寫法 | ms | 相對 inline |
|---|---|---|
| inline `<td>` | 2.56 | 1.00x |
| macro + `attrs()` 無保護 | 18.49 | 7.2x |
| macro + `attrs()` 加 `{% if kwargs %}` | 10.25 | **4.0x** |
| macro + attrs 改成 Python global | 14.36 | 5.6x |

**空的 kwargs 仍要付一次完整的 Jinja macro 呼叫，幾乎讓外層 macro 的成本翻倍。**
「跳過呼叫」比「讓呼叫變便宜」有效：Python global 版本反而輸給加保護的 Jinja 版本，
因為常見情況是 kwargs 為空，保護直接省掉全部工作。已套用到全部 6 個模板。

### 剩下的 23%：元件系統的固有成本

profile 顯示儀表板一次渲染做 **126 次 macro 呼叫**（舊版 inline 約 20 次），
每次約 2.5 µs ≈ 0.31 ms——正好等於量到的差值。這不是 bug，是把排版變成元件的代價。

絕對值是每頁 0.3–0.4 ms，在任何一次 DB 查詢面前可以忽略。

**待決（放寬品質預算需人類決定）**：預算寫「單頁渲染回歸不得慢超過 10%」。
這條規則原意應該是「fjkit 不得一版比一版慢」，而不是「fjkit 必須追平手寫 inline markup」
——後者在元件化的前提下不可能成立。建議：

1. 10% 的門檻改為**版本對版本**的回歸檢查（以本次數字為基準線）。
2. 另外記錄「元件系統相對 inline 的一次性成本」為已知量，不當作回歸。
3. 熱迴圈的成本用 0.4 的 **data-driven table**（`table(columns, rows, fields)` 由 macro
   自己跑迴圈、inline 產生 `<td>`）來回收——現在這個設計有實測支撐，不再是臆測。

---

## 路由風格：`@render` 裝飾器（2026-08-17）

`templates.page()` 寫在 handler 內，等於在「還應該只談資料」的地方把路由綁死成 HTML，
而且每條路由都要多帶 `request`、`templates` 兩個只為了原封不動傳回去的參數。
改成模板名掛在裝飾器上，handler 只回傳 response model：

```python
@router.get("/tasks", name="tasks_page")
@render("tasks/page.html", partial="tasks/_board.html")
def tasks_page(service: ServiceDep, status: Status | None = None) -> BoardResponse:
    return board(service, status)
```

**回傳型別註解是唯一的契約。** FastAPI 本來就讀它推導 `response_model`，`@render`
把同一個 model 攤進模板 context——OpenAPI 與模板由一份宣告餵，不可能各說各話。
頁面上看得到的展示值（badge variant、百分比）改用 `@computed_field`，這樣它同時
存在於 JSON，而不是只活在 Jinja 裡。

**兩種表現形式，兩層旗標。** `FjkitConfig(render_mode=...)` 是 app 預設，
`@render(..., mode=...)` 蓋掉單條路由。`"json"` 時回傳值原封不動交回 FastAPI 走
`response_model`。旗標在 request 時解析而非 import 時，否則答案會取決於 import 順序。

**預設是 `"auto"`（2026-08-19，使用者指定）。** 問的是「這個請求有沒有 HTML 可以拿」
而不是「誰在問」：有 `partial=`、或模板不是 `_*.html`，就是頁面，任何人來都渲染；
純 fragment 的路由則只回應 htmx，其他人拿 `response_model` 的 JSON。所以 swap 端點
自動成為 app 的 API，而 demo 一條 `mode=` 都不用寫——正是這個規則的驗收條件。

反過來的規則（「有 htmx header 才給 HTML」）不能當預設：頁面最重要的那個請求——
打網址、重新整理、書籤、上一頁、爬蟲——身上沒有任何 htmx header，會直接拿到 JSON。
判斷 fragment 用的是 `_*.html` 命名，那條慣例 `test_conventions.py` 本來就在守。

三個連帶結果：**JSON 變成對外契約**（`JobDetailResponse.timeline` 那三句英文散文
現在是 API 輸出，要擋就寫 `mode="html"`）；**boost 走 HTML**（`_is_htmx` 不排除
`hx-boosted`，跟 `_is_htmx_swap` 是兩個問題）；**回應帶 `Vary: HX-Request`**——
一個 URL 兩種回應而沒有這個 header，快取會把 fragment 餵給一次整頁導覽。

測試那邊多了一個 `htmx` fixture，parity 的 probe 也補上 header：只有 htmx 打得到的
端點，用不帶 header 的請求去驗證等於在模擬一個不存在的客戶端。舊 app 完全不讀 htmx
header，所以 baseline 一個字都不用重抓，`EXACT` 那七個欄位仍然逐一比對。

**`partial=` 讓 A6 由套件保證。** htmx request 拿 partial，一般 request 拿整頁，
handler 分不出差別。`hx-boosted` 刻意排除——boost 是 htmx 在做一般導覽，塞 fragment
會讓瀏覽器停在沒有 shell 的文件上。

實作上三個非顯而易見的點，都各有一條測試守著：

1. **wrapper 的同步性必須跟著 handler。** `def` 包成 `async def` 會把每次渲染搬到
   event loop 上，正好違反 CLAUDE.md 那條 threadpool 規則——而且不會有任何錯誤。
2. **註解要自己解析。** FastAPI 用 `endpoint.__globals__` eval 字串註解，而 wrapper 的
   globals 是 fjkit 的，app 的名字在那裡不存在。改用 `get_type_hints` + 裝飾當下那層
   frame 的 locals（函式內定義的 model 才找得到）。
3. **`status_code=` 與 handler 設的 header 要自己併。** FastAPI 只把它們併進「自己組出來的」
   回應；這裡回應是裝飾器組的，不併就會靜靜消失。優先序：handler → route → 200。

**非目標的敘述已改寫（已由人類核可）**：原文「不輸出 JSON API 給前端框架用」與
一份有文件的雙協定契約直接衝突。改成：不為了餵前端框架而設計 API，但同一條路由的
JSON 表現形式是一等公民，描述的是**這個頁面被交到手上的資料**，由回傳型別註解定義。
判準因此很明確：頁面不需要的欄位不會為了 JSON 而加進 response model。

**尚未處理**：`status_filters` / `priority_options` 仍是 `(value, label)` tuple，
因為那是 `ui/form.html` 的 `select_field` 吃的形狀，OpenAPI 上會呈現成兩元素陣列。
改成 `Option` 物件會動到已發佈的 macro 簽名（那需要人類核可），而且 tuple 字面值
（`options=[("a", "A")]`）在模板與測試裡直接可寫，換成物件就得多一個 Jinja global
才能保住同樣的寫法——收益（兩個欄位的 JSON 形狀）小於代價，等真的有客戶端在讀
這份 JSON 時再決定。

---

## 文件站改成三頁，由 fjkit 自己的 Environment 渲染

原本的 `docs/index.html` 是一頁十一課、484 KB 的單一檔案，由
`page.template.html` 加三個 `str.replace()` 標記組出來。那套組裝法撐不到第二頁：
一有共用外殼就需要 `{% extends %}`，一有重複的 stage／code-tab 就需要 macro。

**三頁，各有明確的讀者問題：**

| 輸出 | 頁 | 回答的問題 |
|---|---|---|
| `docs/index.html` | Learn | 這些東西怎麼組在一起？htmx 到底送了什麼？ |
| `docs/components.html` | Components | 這個 macro 吃什麼參數，長什麼樣？ |
| `docs/example.html` | Example | 真的寫起來，一支 app 長什麼樣？ |

（後續：`index.html` 已改成 Introduction 首頁，Learn 移到 `learn.html`，見下方
〈文件站加上 Introduction 首頁〉。）

**渲染器就是 fjkit 自己。** `build_environment(FjkitConfig(template_dir=...))`
——同一個 loader、同一套 autoescape、同一組 globals。文件站因此是套件的下游：
kit 壞了，文件就 build 不出來。頁面模板放在
`packages/fjkit/docs/workbench/templates/`，本身就是一組 fjkit 模板，並且照 kit
要求 app 做的事情做：重複出現的東西（lesson、files、defs、stage_bar）是 macro，
不是複製。刻意**不** extends `ui/shell.html`——文件外殼是 `t-` 前綴、永遠不會伸進
preview 裡的 CSS，讓文件繼承被示範的那層 shell 會讓兩者分不開。

**Example 頁的每一行程式碼都是從 `examples/board` 讀出來的。** build 時讀檔，
路徑寫死在 `build.py` 的 `DEMO_SOURCES`：檔案改名 build 就失敗，而不是靜靜地
發佈過期的程式碼。檔案樹同樣有 `verify_tree()` 對磁碟核對。highlight 在瀏覽器端
跑（讀 `textContent`），所以關掉 JS 也讀得到原始碼，而且只有一份 highlighter。

**資產改成共用檔案，不再內嵌。** 三頁各自內嵌同一份 300 KB 樣式表，等於在 git
裡放三份、每次換頁重下一次。改成 `docs/assets/`：`fjkit.css` 與 `htmx.min.js`
原封不動複製，加上頁面外殼的 `docs.css` 與各頁腳本。對讀者仍然是零建置的靜態
HTML，Pages 直接從分支發佈。

**刪掉的東西**：`page.template.html`（拆成 `templates/` + `assets/`）、
`fjkit-workbench.html`（body fragment，沒有任何東西引用它，三頁之後這個概念也不
成立了）。

**待人類決定**：`CLAUDE.md` 與 `README.md` 的倉庫地圖仍寫著「index.html（the
published workbench）」。手寫檔案要先問過。
→ 已由使用者指示更新，見下方〈文件站加上 Introduction 首頁〉。

---

## 文件站改成「真的用 fjkit 蓋」

上一輪只把**渲染器**換成 fjkit 的 Environment，頁面外殼仍是手寫的 `t-` 前綴 CSS。
這一輪把外殼也換掉：`templates/base.html` extends `ui/shell.html`，導覽是
`sidebar` + `sidebar_link`，內容由 `page_header`／`section`／`card`／`table`／
`grid`／`stack` 組出來——跟 `examples/board` 呼叫的是同一批 macro。

**驗收是 `fjkit check` 跑在文件站自己的模板上，而且過。**
`packages/fjkit/tests/test_docs_site.py` 把它變成測試。`docs.css`（603 行手寫
外殼）刪掉，換成 `assets/brand.css`。

**兩個 config 旋鈕就把 app 變成靜態站，不必改 shell 一行：**

- `static_url="assets"` — `fjkit_static('dist/fjkit.css')` 解析成頁面旁邊的路徑，
  靜態樹照 `mount_ui()` 服務的形狀複製過去。
- `globals={"url_for": ..., "is_active": ...}` — 套件版的會呼叫 `request.url_for`，
  build 時沒有 request。替代品簽名一樣，讀 `request.route`（context 傳進去的普通
  物件）。route **名字**仍然是貨幣，所以 `sidebar_link`、`brand` 原封不動可用。
  route 名字可以帶 fragment（`learn#wiring`），頁內導覽因此不必第二套機制。

**白撿到的東西**：Basecoat 的 JS（shell 本來就載）自己接管了 `.tabs` 的選取與
方向鍵、`input[type=range]` 的填充軌、sidebar 的收合。文件站因此**刪掉了自己的
tab 控制器**——三處 tab 都不再綁 click listener。

### 這一輪真正的產出：七個「說不出來」的洞

文件站比後台難，因為它會伸手要後台不需要的形狀。凡是詞彙表講不出來的，都集中在
`assets/brand.css` 的 PART 2，每一塊都標了「缺的 macro 是什麼」。**PART 2 的長度
就是「封閉詞彙表到底夠不夠用」的誠實答案。**

| # | 缺的東西 | 為什麼會撞到 |
|---|---|---|
| 1 | `code_block` | 沒有任何方式渲染原始碼。文件站要、log 頁要、API reference 也要 |
| 2 | `tabs` macro **與外觀** | Basecoat 的 `.tabs` 只給結構（flex 方向），**完全沒有皮**。行為免費，外觀要自己畫 |
| 3 | 圖表外框 | SVG 本來就不該由元件庫畫，但外框與 `data-lit` 打光沒地方放 |
| 4 | `tile`／placeholder | layout playground 要有東西塞進 stack／grid，`empty_state` 太重 |
| 5 | `icon_grid` | 「一格一個具名東西」的畫廊，`grid()` 給欄位，格子本身沒元件 |
| 6 | 垂直的 `nav_links` | 頁面**內部**的選項清單（pattern picker）沒有 macro |
| 7 | 腳本可呼叫的 `field_row` | playground 的控制項在瀏覽器裡生成，模板 macro 搆不到 |

第 7 項最值得注意，因為它暴露了 `fjkit check` 的**盲點**：checker 只讀模板。控制項
由 JS 生成時，把 `grid gap-3 sm:grid-cols-3` 抄進 `.js` 檔就能繞過整個閘門。這次
沒有那樣做（改用 `[data-field-row]` 屬性 + brand.css，並標成 GAP 7），但機制上
擋不住任何人這樣做。

另外兩個既有元件的缺口，順手記著：`item`／`item-group` 有 CSS 沒有 macro（定義
清單與 log 列表直接寫 class，`fjkit check` 允許，因為它們**是**詞彙表的一部分）；
`field_row` 沒有 `"four"` 版型。

### `fjkit check` 的一個真 bug

顏色字面值的規則掃**每一行**，不只 `class="..."`。所以文件不能寫出它正在警告你
不要用的 utility——`<code>text-white</code>` 這句話本身會讓 check 失敗。目前是繞過
去（改寫成「an absolute white」），但正解是顏色規則跳過註解與文字節點，或提供
pragma。`examples/board` 撞不到只是因為 app 模板不會討論顏色。


---

## 把文件站的自訂 component 補進 library

上一輪列出七個「詞彙表講不出來」的洞。使用者直接指示把它們補進套件，所以做了——
「路線圖順序調整超過一版要先問」的授權路徑跟 spinner 那次一樣：**由使用者
直接指定，非我自行決定**。

牽動的路線圖版本：`tabs` 是 0.7，程式碼區塊與 `item`／清單是 0.9，文件站本身是 0.11。

### 補進去的

| 新增 | 檔案 | 路線圖 | 為什麼過收錄標準 |
|---|---|---|---|
| `tabs(items, label, selected, orientation)` ／ `tab_panel(id)` | `ui/tabs.html` | 0.7 | Basecoat 的 `.tabs` **只給結構、完全沒有皮**。行為（選取、方向鍵）是 vendored JS 免費附的，外觀每個 app 都得自己畫一次 |
| `code_block(source, label, wrap)` | `ui/data.html` | 0.9 | 不是「把 `<pre>` 包一層」——捲動容器沒有 `tabindex="0"` 就完全無法用鍵盤捲動，這是它避開拒絕標準第三條的原因 |
| `item_list()` ／ `item(title, description, …, clamp)` | `ui/data.html` | 0.9 | Basecoat 有 `.item` CSS 沒有 macro，而 `.item > section`／`> figure`／`> aside` 的契約正是 app 不該自己重新推導的東西 |
| `button_group(orientation="vertical")` | `ui/button.html` | — | Basecoat 早就吃 `data-orientation="vertical"`，只是沒開出來 |
| `button_group(**attrs)` | `ui/button.html` | — | **它是唯一一個不吃 pass-through 屬性的元件**，連掛個 id 都不行 |
| `field_row("four")` | `ui/form.html` | — | 版型查表少一個 key |

`.item[data-clamp="false"]`、`.tabs` 的皮、`.code-block` 進 `fjkit.css` 的
`@layer components`。**CSS 預算：23.2 → 23.8 KB gzip（上限 28 KB）**，符合第 7 節
「之後補 tabs／dialog／accordion，CSS 幾乎不動」的預測。

`packages/fjkit/tests/test_components.py` 各補了合約測試——特別是 aria 配對，因為那組
屬性寫錯的話 tab 會安靜地停止切換，不會有任何錯誤訊息。

### 沒補的，以及理由

| 洞 | 為什麼留著 |
|---|---|
| 語法高亮 | `code_block` 刻意不認得任何語言。「哪些 token 是關鍵字」不該由 kit 回答 |
| 圖表外框 | SVG 本來就不該由元件庫畫 |
| `tile` placeholder、`icon_grid` | 過不了收錄標準第二條：後台第一週不會需要 |
| **腳本搆得到的 `field_row`** | 不是 macro 能解的，見下 |

### 剩下的那個洞比較嚴重

`brand.css` PART 2 從 7 個縮到 4 個，292 行縮到 220 行。剩下的第 4 個是**閘門的洞**，
不只是缺元件：

playground 的控制項在瀏覽器裡生成，模板 macro 搆不到。把 `field_row` 的 utility class
抄進 `.js` 檔就能繞過 `fjkit check`——**因為它只讀模板，從來不讀腳本**。這次用
`[data-field-row]` 屬性 + brand.css 標成 GAP 4 沒有那樣做，但機制上擋不住任何人。

兩條出路，都不是新 macro：控制項改成伺服器端渲染、瀏覽器只負責 bind；或者讓
`fjkit check` 也讀 `.js`。

---

## 文件站加上 Introduction 首頁（三頁變四頁）

三頁都在「教」，沒有一頁回答**「這是什麼、適不適合我」**。而 GitHub Pages 送出的
第一個檔案是 `index.html`——原本是 Learn，第一課直接從 wiring 講起。一個沒聽過
fjkit 的人，落地的第一頁就是課程第一課。

**新的第一頁：`templates/introduction.html` → `docs/index.html`，Learn 移到
`docs/learn.html`。** 五段，全部指向別頁而不是自己解釋完：

| 段 | 內容 |
|---|---|
| What it is | 一句話定位、release-time Tailwind 的限制，加兩個從 `examples/board` 讀出來的檔案（`main.py`、`tasks/page.html`） |
| Who it is for | 該花多少力氣（第一頁、後台頁、換品牌、升級）對上四個非目標 |
| Five decisions | 決定／買到什麼／**靠什麼守住** 的表格——第三欄才是重點 |
| What is in the box | 套件裡有什麼、你會碰到的整個 API 面、Python 3.13 + 兩個 runtime 相依 |
| Where to go next | 站上三頁、repo 四份文件，加上跑 demo 的兩行指令 |

**`build.py` 的 `PAGES` 是唯一的資料來源**，所以側欄、`url_for`、`<head>` 的
metadata 全部跟著改，模板一行都不用動。`test_docs_site.py` 的 `PAGES` 補第四頁。

**順手拿掉的**：四頁 `page_header` 裡的跨頁按鈕（Components／Example →）。側欄已經
列了全部四頁，那組按鈕是第二套導覽，而且每頁都得手動維護「下一頁是誰」。由使用者
指示移除。

**破壞性變更**：Learn 的網址與它所有的 `#anchor` 從 `index.html` 移到
`learn.html`。站是 pre-release，沒有對外連結需要保。

**一併刪掉**：`packages/fjkit/docs/introduction.md`——同樣的內容先寫成 markdown 的
那份試作。站上的 Introduction 頁取代它，兩份會漂移。

`CLAUDE.md` 與 `README.md` 的倉庫地圖同時更新（上一條的待決事項），現在寫的是
四頁的實況。

---

## 兩個邊框重疊（由使用者回報）

文件站上有兩處邊框互相疊在一起。兩個都不是排版沒調好，是各自有一個具體的
成因，所以分開記。

### 1. tab 列的幽靈捲軸——`fjkit.css` 對 Basecoat 的假設是錯的

`ui/tabs.html` 與 `fjkit.css` 都寫著「Basecoat 的 `.tabs` 只給結構、完全沒有皮」。
**對 `components/tabs.css` 而言是對的，對 style pack 而言是錯的。** 我們 vendored 的是
`basecoat.css → basecoat-vega.css → styles/vega.css`，而 vega **確實**有一整套 tabs 皮，
還附一個 `data-variant="line"` 的底線變體。fjkit 於是在它上面又畫了第二套底線皮，
兩套從此互相打架：

| | vega pack | fjkit 覆寫 | 實際渲染 |
|---|---|---|---|
| 高度 | `h-9`（36px） | — | 固定 36px |
| padding | `p-[3px]` | — | 3px |
| 背景／圓角 | `bg-muted` `rounded-lg` | — | 藥丸底 |
| 寬度／對齊 | `w-fit` `justify-center` | `w-full` `justify-start` | fjkit 勝 |
| 底線 | 無 | `border-b` | 藥丸底**加**底線 |
| 選取樣式 | 白色浮起藥丸 | `bg-muted` + primary inset | **vega 勝**（見下） |
| overflow | visible | `overflow-x-auto` | 見下 |

兩個後果：

- **選取樣式那條 fjkit 根本沒生效。** vega 的選擇器是
  `…[role='tablist']:not([data-variant='line']) > [role='tab'][aria-selected='true']`，
  多一個 `:not()` 就多一級 specificity，把 fjkit 的同名規則壓掉。primary 底線從來
  沒出現過，出現的是 vega 的白藥丸。
- **幽靈垂直捲軸。** tab 按鈕被 fjkit 設成 `px-3.5 py-2`（38px 高），卻裝在 vega 的
  36px 固定高、扣掉 padding 只剩 30px 的內容盒裡。而 CSS 規定 `overflow-x` 一旦
  不是 `visible`，`overflow-y: visible` 就會**計算成 `auto`**——所以那 8px 溢出長出一條
  垂直捲軸，捲軸的 thumb 正好壓在 card 的右邊框上。這就是看到的「邊框重疊」。
  四頁共 8 個 tab 列，每一個都是。

**修法**：不改 macro，只在 `fjkit.css` 把 vega 的幾何全部關掉
（`h-auto rounded-none bg-transparent p-0`）、用 `after:hidden` 拿掉 pack 那條
`bottom-[-5px]` 的底線偽元素（它本身就是 5px 的溢出來源），並把選取規則加一個
純粹用來配 specificity 的孿生選擇器。tab 列高度改由內容決定（39px），溢出歸零，
捲軸消失，而且 fjkit 原本就寫在註解裡的底線外觀**第一次真的畫出來了**。

CSS 預算：23.8 → 23.9 KB gzip（上限 28 KB）。

**留給以後的**：真正乾淨的作法是直接用 vega 的 `data-variant="line"`，因為那就是
fjkit 想要的底線 tab。沒有這次做，是因為 vega 的 line 變體仍保留 `h-9 p-[3px]`，
而它的底線偽元素釘在 `bottom-[-5px]`——要嘛留著溢出，要嘛 `overflow` 把底線裁掉。
選一個之前得先決定 tab 列到底要不要橫向捲動。

### 2. `#checker-output` 的 25 個 alert 互相貼死

Learn 頁的 `fjkit check` 示範把每個違規渲染成一個 `alert`，塞進一個沒有間距的
`<div>`。25 個 1px 邊框首尾相接，每個交界都變成 2px 的粗線，兩顆圓角還撞在一起。

**修法**：容器改成 `stack(gap=2, id="checker-output", aria_live="polite")`。
`stack` 本來就吃 `**kwargs` 走 `attrs()`，所以 id 與 aria 屬性照掛，JS 那邊
一行都不用動——它注入的還是 `innerHTML`，只是父層現在是 flex column 有 gap。

值得記一筆的是：這個洞正是 GAP 4 講的那件事的另一面。腳本生成的標記沒有任何
閘門看得到，`fjkit check` 讀模板不讀 `.js`，所以「忘了給間距」這種事只能靠眼睛
或靠瀏覽器量。這次是用一支量測腳本掃四頁的 border 座標抓出來的，不是用看的。

## 八個 Basecoat 風格包全部 build 進 wheel（2026-08-19）

`theming.md` 原本把「要 ship 幾個 skin」列為待決，理由是**會動到 CSS 預算**。
量完之後那個理由不成立：第 7 節的預算是**每頁**預算，而一頁只會載一個包。

八個包各自 build，全部在預算內：

| pack | raw | gzip |
|---|---|---|
| vega（預設） | 234,047 | 23.9 KB |
| nova | 238,673 | 23.9 KB |
| maia | 233,142 | 23.9 KB |
| lyra | 234,257 | 23.6 KB |
| mira | 234,778 | 23.9 KB |
| luma | 236,768 | 24.1 KB |
| sera | 220,228 | 23.5 KB |
| rhea | 237,048 | 24.1 KB |

vega 的位元組跟改動前的 `dist/fjkit.css` 一模一樣，所以這次不是換皮，是多七個選項。
另外七個在 wheel 裡是 167 KB（deflate），只付一次安裝成本，瀏覽器一個位元組都不會多下載。
**這就是為什麼選風格是 config 值而不是重裝**：`FjkitConfig(style="nova")`，重開即可。

做法：
- `src/fjkit.css` 的風格包 import 加上 `/* fjkit:style-pack */` 標記，`build-css`
  只改那一行，其餘完全共用。改壞標記會**明確報錯**，不會默默 build 出八個一樣的檔案。
- 產物改名為 `dist/fjkit-<pack>.css`，`dist/fjkit.css` 不再存在。
- shell 依 `fjkit_style` 組出 link，`mount_ui` 檢查的是**設定的那個包**。
- `test_style_packs.py` 釘住關鍵前提：八個包 emit 的 class 集合**完全相同**——
  這就是換包不用改任何 template 的原因，一旦不成立，`fjkit check` 跟全部 template 都會受影響。

### `uv add "fjkit[nova]"`——安裝時選包（同日做掉）

extras 只能拉進**別的 distribution**，改不了自己所屬 wheel 裡的位元組，所以
extra 本身選不了任何東西。做法是八個 marker 套件 `packages/fjkit-style-<pack>/`：
一個 entry point，不帶 CSS（stylesheet 本來就都在 fjkit 的 wheel 裡），也不反過來
依賴 fjkit（那會成環）。`FjkitConfig.style` 預設改成 `"auto"`，去 discover 這個
entry point——只讀 `.name`，不 import 模組。

| 做了什麼 | shell link 哪一個 |
|---|---|
| 什麼都沒做 | `fjkit-vega.css` |
| `uv add "fjkit[nova]"` | `fjkit-nova.css` |
| 兩者都有，且 `style="sera"` | `fjkit-sera.css`——**寫在 code 裡的贏** |
| 裝了兩個 marker | 啟動就報錯，點名兩個，**不猜** |

裝兩個不自己挑掉一個：挑了就等於讓頁面長相取決於 metadata 掃描順序，那種 bug 連
bisect 都抓不到。

**marker 被排除在 workspace members 之外**（`exclude = ["packages/fjkit-style-*"]`）。
workspace 會把所有成員都裝上，八個一起裝正好撞上上面那條歧義規則——`uv sync` 之後
整個 repo 開不起來。它們是「要發佈的東西」，不是開發環境的一部分。

已用一個 scratch 專案實測過完整路徑：`uv add "fjkit[nova]"` → 不寫任何 config →
shell 送出 `/_fjkit/dist/fjkit-nova.css` → 200，238,673 bytes，跟 nova 的產物一致。

**要你點頭的**：這一步占掉八個 PyPI 名字 `fjkit-style-{vega,nova,maia,lyra,mira,luma,sera,rhea}`，
屬於第 11 節第 5 條（命名／PyPI 專案名）。第二階段真的要發佈前確認一次。

---

## 文件站砍掉 Example 頁，章節標題改成指名道姓（2026-08-19）

**Example 整頁移除。** 它的內容是 `examples/board` 的原始碼——`main.py`、tasks 的
router／service／schemas、三種 template、兩支測試——在 build 時讀進來排版一次。
那些檔案在 repo 裡就是原檔，讀者 clone 之後看到的是同一份而且是可執行的；文件站
複述一次，得到的是一份會過期、需要 `DEMO_SOURCES` 與 `TREE` 兩張清單守著才不會說謊
的副本。刪掉之後這兩張清單也跟著沒了：`verify_tree()`、`_parts.html` 的 `tree_table`、
`test_the_tree_matches_the_demo`，以及 `DEMO_SOURCES` 裡除 Introduction 引用的兩個
檔案以外的十五筆。

原本指向 Example 的連結改指 repo 路徑（`examples/board/`、
`examples/board/app/templates/tasks/`）——同一份東西，但指的是原檔而不是副本。
文件站剩三頁，`PAGES` 一改，側欄與 `url_for` 全部跟著改，模板不用動；這正是
Introduction 那次加頁時建立的性質，反過來用一次。

**章節標題改成指名道姓的。** 原本的標題是命題（「The signature is the contract」、
「One partial, two doors」、「The rule that fails a build」），讀起來像章節大意，
但側欄「On this page」是拿它當索引用的——想找 `hx-swap` 的人掃過八個命題，一個都
對不上。改成直接寫出裡面講的東西：

| 頁 | 原標題 | 現標題 |
|---|---|---|
| Learn | Four files, three calls | Wiring: config, mount, templates |
| Learn | What crosses the wire | The htmx request and response |
| Learn | Where the answer lands | hx-target and hx-swap |
| Learn | When it fires | hx-trigger: typing, scrolling, polling |
| Learn | One partial, two doors | Partials: one file, page and swap |
| Learn | The nine you will write | Nine htmx patterns, and their handlers |
| Learn | One knob, and its limits | Rebranding: brand and status tokens |
| Learn | The rule that fails a build | fjkit check: the closed vocabulary |
| Components | The signature is the contract | Every macro: the call and the HTML |
| Components | Layout is a component | Layout: stack, row, grid, split |
| Components | The furniture of a page | page_header, section, divider |
| Components | Showing the data | empty_state, metric_group, lists |
| Components | Icons are a macro call | icon(): any Lucide name, inlined |
| Components | The whole vocabulary | Every macro in ui/, by file |
| Introduction | What it is / Five decisions / What is in the box | What fjkit is / Five decisions, and what holds them / What ships in the wheel |

命題沒有丟掉——`lesson()` 的第四個參數（thesis）本來就是放這種句子的位置，每一節的
那一行都還在原處。動的只是索引欄該顯示什麼。

---

## 文件站出中文版：三頁 × 兩語言，共用同一套骨架（2026-08-19）

英文留在原位（`docs/*.html`），中文放在 `docs/zh/`。**能共用的全部共用**：`base.html`、
`_parts.html`、請求流程圖、以及 `assets/` 底下每一支 js 與 css 都只有一份，兩邊都指到它。
分岔只有兩處：`templates/zh/` 的三頁散文，以及 `build.py` 裡的 `STRINGS`（側欄標題、
頁尾那句話、流程圖上的字）。

流程圖是刻意不複製的那一個。它是一張手寫座標的 SVG，複製一份去翻譯等於維護兩套座標，
而第二套一定是先過期的那套——所以圖裡每個字改成從 `t.diagram` 來，圖形本身只有一份。

| 東西 | 份數 |
|---|---|
| 頁面模板 | 2（`templates/`、`templates/zh/`） |
| `base.html`／`_parts.html`／`_diagram.html` | 1 |
| `assets/*.js`、`brand.css`、`data.js` | 1 |
| chrome 文字（rail、footer、圖標籤） | `build.py` 的 `STRINGS`，一個語言一組 |

### GitHub Pages 上真的會動嗎——這是這次唯一難的地方

Pages 服務的是 **project 子路徑**（`https://…/fjkit/`，不是網域根）。從本機把 `docs/`
當根目錄開一個 server，絕對路徑 `/assets/fjkit.css` 會好好的；上了 Pages 就 404。
中文頁又比英文頁深一層，所以「相對」對兩邊不是同一個字串。

做法：每個語言各建一個 `build_environment()`，只差在 `static_url`——英文 `assets`，
中文 `../assets`。shell 的 CSS／htmx／Basecoat 連結本來就走 `fjkit_static`，站台自己的
`brand.css`、`data.js`、`common.js`、`learn.js`、`components.js` 與 mock server 這次也
一律改走 `fjkit_static`，所以「往上爬幾層」只寫在 config 裡一次。頁面之間的連結由
`url_for` 算：同語言是純檔名，英→中加 `zh/`，中→英加 `../`。

驗過的（不是用看的）：

- `python3 -m http.server` 開在一個只有 `fjkit -> docs` 這個 symlink 的目錄，模擬
  `https://user.github.io/fjkit/`。六頁全部 200，**頁面上每一個 href/src 抓出來逐一 GET，
  全部 200**——含 `../assets/dist/fjkit-vega.css`、htmx、Basecoat、logo。
- 實際用瀏覽器開 `/fjkit/zh/learn.html`：樣式套上、logo 出來、learn.js 把 wiring 分頁填好、
  語言鏈結指到 `../learn.html`、`<html lang="zh-Hant">`。
- `test_docs_site.py` 多一條 `test_every_asset_link_is_relative_to_its_page`，直接掃 build
  出來的六個檔案：沒有任何連結以 `/` 開頭，而且每一個都指得到真的檔案。這條就是「Pages 上
  會不會壞」的迴歸測試。

htmx 的示範仍然用絕對路徑 `/demo/board`，這在 Pages 上沒問題：`mock-server.js` 在
`XMLHttpRequest.open()` 就攔下來了，那些請求根本不會出門。

### 還沒做完的一半

`learn.js` 與 `components.js` 裡的 caption 仍然是英文——九種模式的說明、swap 組合的註解、
每個 macro 的那句話，大約 2,000 字。它們是字串常數散在程式裡，要中文化得先抽成
`copy-en.js`／`copy-zh.js` 之類的表再由腳本取用。`data.json` 裡渲染好的預覽（"Add task"、
板子上的那幾列）同理，那要 `build_data.py` 也跑兩次。兩件都是機械性的工，但都會動到
現在共用的那一份檔案，所以另外一筆做。

---

## 0.2 表單基礎（2026-08-21）

路線圖 0.2 補完。`ui/form.html` 從兩支欄位變成七支：

- [x] `textarea_field` — 不預設 `rows`，靠 basecoat 的 `field-sizing-content` 自己長高
- [x] `checkbox_field` — 框在前、字在後，`.field[data-orientation="horizontal"]`
- [x] `switch_field` — 同一個 `<input type="checkbox">`，只多一個 `role="switch"`。
      對路由來說兩者無法分辨，所以換外觀不會動到 handler
- [x] `radio_group` — 真的 `<fieldset>`／`<legend>`，不是 div 配 label。吃的
      `options` 跟 `select_field` 同一個形狀，所以兩者互換是改一個字
- [x] `fieldset` — 一張表單裡不只一個主題時才用

一條貫穿的契約：七支欄位都吃 `label`／`hint`／`error`／`id`，都只發**一個** `<p>`，
`error` 取代 `hint` 而不疊加，控制項用 `aria-describedby` 指到它。`_message()` 是
那個 `<p>` 的唯一定義，原有的 `text_field`／`select_field` 也改成呼叫它。0.3 落地時
要做的就只是把 `ValidationError` 填進 `error=`。

### 順手修掉的一個真 bug：`form()` 沒有 `target` 時仍然發 `hx-post`

macro 自己的註解寫著「a form with a target is an htmx form; one without is an
ordinary POST」，但程式碼只要有 `action` 就發 `hx-post`，從來不發 `action=`／
`method=`。沒有 target 的 `hx-post` 會把回應塞進表單自己（htmx 的預設 target 就是
觸發元素），沒有人會是這個意思。

沒被發現是因為 **demo 裡每一張表單都有 target**——三張都是 htmx swap，所以那半條
路從來沒被走過。這次補的 `/tasks/{id}/edit` 就是走它的那一頁：同一個 macro、同一批
欄位，不帶 `target`，關掉 JavaScript 照樣能用。

### demo 端

新的 `/tasks/{id}/edit` 頁（`tasks/edit.html`，`test_edit.py` 8 條）。它是這五支欄位的
驗收場，也是 demo 第一張非 htmx 的表單：POST 完 303 導回板子，重新整理不會重送。
`Task` 多了 `notes`／`blocked`／`watching` 三個欄位，寫入走 `TaskUpdate` 這個封閉清單，
所以 `status`／`id`／`created_at` 是**結構上**改不到，而不是靠表單剛好沒送。

板子每一列多一支鉛筆，是 `<a>` 不是 swap——所以 `test_parity.py` 的 `hx_attrs`／
`ids` 那幾欄一個字都沒動。

### 文件站

Components 頁的 form 選單從兩個狀態變五個：htmx 表單、錯誤、textarea + checkbox、
radios vs select、fieldset 裡的 switch。每一個的 Jinja 片段跟預覽都是同一份
`build_data.py` 產的，所以頁面教不出 kit 沒有的簽名。
