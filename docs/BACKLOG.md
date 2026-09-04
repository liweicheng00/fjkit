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

- [x] `examples/fjkit-demo` 完全不寫原生 utility class 就能重寫出來
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
| 2026-08-22 | `fjkit.apidocs` API 主控台（模板隨外掛放在 `apidocs/templates/`，`fjkit.css` 因此多一條 `@source`） | 234,817 (229.3 KB) | 24,622 gzip | **+482 raw / +135 gzip**，24.0 / 28 KB。全部是主控台模板自己帶進來的 utility——側欄那欄固定寬的 `w-18`、登入列的 `sm:w-64`、facts 的 `items-baseline`／`gap-x-5`；`.card`／`.badge`／`.field` 的樣式本來就在 basecoat 裡 |
| 2026-08-23 | `fjkit eject` 的版本戳 + `fjkit check` 的過時回報（`cli/ejected.py`） | 234,817 (229.3 KB) | 24,622 gzip | **±0**，24.0 / 28 KB。純 Python，沒有模板變動 |
| 2026-08-23 | 補齊 Basecoat 缺口第一批：`alert`／`skeleton`／`breadcrumb`／`avatar`／`avatar_group`／`range_field`／`collapsible`／`accordion`／`tooltip` | 236,697 (231.1 KB) | 24,980 gzip | **+1,880 raw / +358 gzip**，24.4 / 28 KB。九個元件的樣式 basecoat 全都早就出貨了；增量是模板自己帶進來的 utility——`skeleton` 那五個 `w-*` 分數與 `aspect-video`／`size-10`、`collapsible` 的 `group-open:rotate-180`、`avatar` 的 `bg-success`／`bg-warning`／`bg-info` |
| 2026-08-23 | 補齊第二批（overlay 層）：`popover`／`dropdown_menu`／`menu_item`／`menu_group`／`menu_separator`／`select_menu`／`combobox`／`drawer`／`drawer_trigger`／`command`／`command_group`／`command_item`／`input_group_field` | 236,601 (231.1 KB) | 25,006 gzip | **−96 raw / +26 gzip**，24.4 / 28 KB。十三個 macro 只花 26 bytes：`.popover`／`.dropdown-menu`／`.select`／`.combobox`／`.command`／`.drawer`／`.input-group` 的樣式全在 basecoat 裡，模板只帶進 `_PANEL_WIDTHS` 那五個 `w-*` 與 `truncate`。raw 下降是因為這批取代了幾個一次性 utility |
| 2026-08-23 | 圖表變成外掛：`fjkit.charts.ChartsPlugin`（demo 的 charts 頁改為註冊它） | 236,601 (231.1 KB) | 25,006 gzip | **±0**，24.4 / 28 KB。`charts/macros.html` 一個 utility 都沒帶——圖表的外框是 `card`，圖本身是一個沒有 class 的盒子 |
| 2026-08-23 | `form(encoding="json")` + vendored `htmx-ext-json-enc`（demo 的 jobs 表單改送 JSON） | 236,920 (231.4 KB) | 25,031 gzip | **±0**，24.4 / 28 KB。實測方式寫下來：把 `ui/form.html` 與 jobs 頁換回 HEAD 版重建，數字一個 byte 都沒差——這次加的是屬性不是 class。絕對值比上一列高 319 raw / 25 gzip，那是 0.3 的錯誤頁與 shell 監聽器帶進來的，不是這次的 |
| 2026-09-01 | `.dialog > * > section` 補 `scrollbar-gutter: stable`；`data.html` 的 `caption`；`select_menu`／`combobox` 的 `visible_label`／`hint`／`error` | 236,944 (231.4 KB) | 25,044 gzip | **+24 raw / +13 gzip**，24.5 / 28 KB。24 bytes 全部是那一條 `scrollbar-gutter`——它不是 utility，是寫在 `@layer` 裡的原生宣告，所以逐字進了每一個包。三處模板變動一個 utility 都沒帶：`.field`／`.label`／`text-muted-foreground`／`text-destructive` 早就因為 `ui/form.html` 在編出來的檔案裡了 |
| 2026-09-01 | dialog 捲軸修正第二版：section 改為 `-mx-6 px-6` 自帶行內 padding | 237,024 (231.5 KB) | 25,053 gzip | **+80 raw / +9 gzip**，24.5 / 28 KB。`margin-inline` 與 `padding-inline` 各一條，寫進同一條規則 |

### 表單送 JSON（2026-08-23，使用者指定）

問的是「現在常用的 API 都會開發 json，好像需要納入 fjkit」。這是兩條路，提了之後由你選：

- **A. 伺服器端雙吃** —— 一個 `FormOrJson` 依 `Content-Type` 決定怎麼讀 body，兩種編碼
  驗證同一個 model。純 Python，`form()` 不用動。**你選擇不做**，決策記在這裡。
- **B. 客戶端送 JSON** —— vendor htmx 的 `json-enc`，`form()` 多一個 `encoding` 參數。
  **做的是這個。**

落地的東西：`HTMX_JSON_ENC_VERSION = "2.0.3"`（自己的 npm 套件，htmx 2 把 extension 全
搬出核心倉庫）、`static/vendor/htmx/json-enc.js`（1,012 bytes，不 minify：為了省 300
bytes 加一個建置步驟，與這個專案的前提相反）、`form(encoding="json")`、
`form_scripts()`，以及 demo 的 jobs 表單。

**為什麼是 `form_scripts()` 而不是塞進 shell。** §7 管的是「每頁**預設**下載什麼」，答案
必須維持「htmx + basecoat」。所以走 `chart_scripts()` 對 Plotly 那條逐頁 opt-in 的路：
有 JSON 表單的那一頁自己寫 `{% block scripts %}{{ form_scripts() }}{% endblock %}`，其他
頁一個 byte 都不多載。預算沒有放寬，第 11 節第 8 條沒有觸發。

**為什麼 demo 選 jobs 而不是 tasks 板。** jobs 的 start 表單本來就 `target="#job-list"`，
沒有 htmx 就不能用，改成 JSON 不會失去原本存在的能力。tasks 的建立表單與 edit 頁
示範「沒有 JS 也能送出」，動它會拆掉 demo 要證明的事。

**實測記錄，免得以後重新爭論這題：**

- pydantic 的 lax mode **本來就吃表單送來的字串**：`"3"` → `int`、`"on"`／`"true"`／`"1"`
  → `True`。所以 form 與 model 的落差不在驗證，只在 FastAPI「看到 model 就只肯讀 JSON」
  那一步。
- 一般表單 POST 到 model route，得到的是 `loc: ["body"]`、`type: "model_attributes_type"`
  ——**沒有欄位名**，所以落進 `general`：使用者看到一句開發者才懂的英文 toast，而且沒有
  任何欄位變紅。這正是 A 那條路要解的東西。
- json-enc 做兩件事：送 `Content-Type: application/json`，並 `JSON.stringify` 一個扁平物件。
  值全是字串，重複的 key 變陣列，**不支援巢狀，也不能送檔案**。所以 `name="items.0.title"`
  會原樣變成 key，巢狀 model 前面要擺一個扁的 DTO。

**同一批修掉的錯誤層 JSON 缺口**（在 B 之前就先補了，否則 JSON 表單被退回時會清空）：

- `errors.py::_submitted()` 依 `Content-Type` 選 parser。`request.form()` 對 JSON body
  **不會拋錯**，它回一個空的 `FormData`，與「表單什麼都沒填」無法區分。結果是 JSON 表單被
  退回時，紅字正確出現，而每個輸入框都被清空。
- `forms.py::json_values()` 把 body 攤平成與 `loc` 相同的鍵名（`items.0.title`）。
  `true` → `"on"`（打勾的 box 送的就是這個）；`false`／`null` 直接不放，因為 `str(False)` 是
  `"False"`，在模板裡是 truthy，會把使用者剛取消的勾又打回去。
- `forms.py::_UNPARSABLE`：讀不出來的 body 歸到 `general`。判斷依據是 pydantic 的
  `type == "json_invalid"` 而不是 loc 形狀，因為 `("body", 0)` 也是「body 是 list，第一個
  元素有問題」的合法回報，兩者形狀相同。修之前 toast 會寫「2: JSON decode error」，
  那個 2 是位元組偏移量 +1。

**沒做、留著：**

- 元件站的 components 頁沒有 `encoding` 的樣本。那頁由 `data.json` + `assets/components.js`
  驅動，加一個樣本要動 JS，而 `encoding` 在畫面上看不出差別。macro 的簽名註解是
  CLAUDE.md 指定的簽名權威，暫時夠用。
- A（`FormOrJson`）沒做。成本約 40 行加測試，唯一的實質代價是 `Depends` 型的 body
  不會出現在 `/openapi.json`，也就不會出現在 `/api-docs` 主控台，得用 `openapi_extra` 從
  model schema 補回去。

### 圖表變成外掛（2026-08-23，使用者指定）

問的是「把 Plotly 的實作變成外掛，讓使用者有圖表能力」。做完之後 demo 的 charts 頁
少了三個檔案，多了一行 `ChartsPlugin(static_dir=APP_DIR / "static")`。

- **1.1 MB 沒有進 wheel，這是整個設計的重點。** 第 7 節那條「使用者端 JS 僅 htmx +
  basecoat」是對**每一個**安裝的承諾，包含永遠不畫圖的那些。把 Plotly 塞進套件，等於
  為了服務一部分人而對所有人毀約。所以外掛出貨的是 Python、macro 和 3 KB 的 `charts.js`，
  Plotly 由 `uv run fjkit vendor-plotly --into app/static` 下載進**使用者的 repo** 並
  commit——跟 kit 自己 vendored htmx／Basecoat 同一套規矩，一樣沒有 npm、沒有 bundler、
  執行期不連外。實測 wheel 裡 `plotly` 只出現在 `cli/vendor_plotly.py` 這個檔名裡。
- **少了那份 vendored 檔案時是降級，不是壞掉。** 沒有 Plotly 時 `chart_scripts()` 不輸出
  那一行 `<script>`，圖表退回 `<figcaption>`（那本來就是無 JS 時的內容），
  而 `mount` 在啟動時用 `setup.warn()` 講明白。理由是這個失敗的症狀沒有線索：
  頁面會渲染、版面會對，然後是三個空盒子。
- **外掛不能碰 shell，這次驗證了那條限制。** `fjkit.plugins` 明文禁止外掛注入
  shell 標記；如果可以，這個外掛就會把 1.1 MB 放到登入頁上。改成由畫圖那一頁自己在
  `{% block scripts %}` 呼叫 `chart_scripts()`，per-page 的 opt-in 就守住了。
- **`/_fjkit-charts` 而不是 `/_fjkit/charts`。** 第一版寫成後者，測試直接 404：
  Starlette 比對的是第一個前綴吻合的 mount，`/_fjkit` 是 kit 自己的 static，於是
  `/_fjkit/charts/...` 被它吞掉並拿去它的目錄裡找。
- **`static_url()` 從私有變成公開。** 外掛要的是同一套 `?v=<mtime>` 戳記；自己再寫一份，
  就是對「StaticFiles 不送 Cache-Control」給出第二個答案。多了一個 `root` 參數，
  預設仍是 kit 的 static 目錄。
- **`figures.py` import pydantic，撞到 kit 的兩個依賴守門測試。** 這是 §11.2 要人決定的
  那種事，所以做法是把 `fjkit/charts/` 明確列進 `exempt` 並寫下理由，不是把 pydantic 加進
  `declared`。理由：`Chart`／`PlotlyFigure` 存在的意義就是被 app 放進自己的
  `response_model`；pydantic 是 fastapi 的硬依賴，安裝成本為零；不畫圖的 app 永遠不會
  import 到這個子套件。**若不接受，正確的改法是把 `figure` 退成 `dict` 並失去 OpenAPI
  精度，而不是放寬那份名單。**
- **`assert_no_colour_in()` 跟著搬進套件。** 原本是 demo 的一個測試，現在是外掛給 app
  的一行工具。它掃的是**算出來的 JSON**，因為顏色只可能從 `extra="allow"` 那條尾巴進來。
  `var(--primary)` 也在模式裡：`plotly.py` 會接受、驗證、序列化它，然後瀏覽器端靜靜丟掉。

### 圖表外掛住哪裡：定案 `fjkit.charts`，留在 wheel 內（2026-08-23 覆核）

同一天出現過兩個答案：(a) `fjkit.charts` 在 wheel 內（已落地，`822891b`），
(b) 獨立發行版 `packages/fjkit-charts/`。(b) 是在 (a) 還不存在時提的，使用者同意 (b) 時
也只看得到 (b)，所以這次重新量過前提再決定。**結論是 (a)。**

量到的六件事，都可以重跑：

- `uv build --package fjkit` 拆開 wheel：125 個項目裡沒有任何 Plotly bundle。檔名含
  `plotly` 的只有 `fjkit/cli/vendor_plotly.py`；內容含 `plotly` 的只有它與
  `charts/plugin.py`，兩處都是那個釘死版本的 URL 常數。charts 整包在 wheel 裡是
  **32,108 bytes raw / 13,979 bytes 壓縮後**，佔 402,395 bytes 的 3.5%。
- `fjkit/charts/` 的 module scope 第三方 import **只有 `pydantic`**，而且只在
  `figures.py`；`plugin.py` 只 import stdlib 與 fjkit 自己。
- `importlib.metadata.requires("fastapi")` 回傳的第一條就是 `pydantic>=2.9.0`，**沒有
  extra 條件**（實測 fastapi 0.141.1）——安裝成本確認為零。不註冊外掛的 app 跑完
  `mount_fjkit` 之後 `sys.modules` 裡沒有 `fjkit.charts`，也沒有 `fjkit.charts.figures`。
- CSS：把 `fjkit.css` 那行 `@source "../../charts/templates";` 拿掉重建，`fjkit-vega.css`
  與留著時 **byte-identical**（236,920 raw / 25,031 gzip 兩次都一樣）。`fjkit check` 的
  詞彙表來源是 Basecoat 的 `components/`／`base/` 加 `static/src/fjkit.css`——charts 的
  模板不在那份名單裡，而且它本來就一個 class 都不發明。
- 降級路徑實跑成立：沒有 vendored bundle 時 `mount_fjkit` 吐一個 `PluginWarning`（訊息
  含缺的檔案路徑與該跑的指令），`chart_scripts()` 只剩 `charts.js` 那一行，
  `<figcaption>` 的句子仍在。放進 bundle 之後警告消失、兩行 script 都帶 `?v=`。
- `uv run fjkit vendor-plotly --into <tmp>` 是真的能跑的指令，下載 **1,119,926 bytes**，
  與 demo 裡 commit 的那份同大小。

**當初支持 (b) 的三條理由，兩條實測是錯的、一條打平：**

1. 「1.1 MB 會進每個 fjkit wheel」——**錯**，一個位元組都沒進。
2. 「`plotly` 會變成第三個 runtime 依賴」——**錯**，多的是 `pydantic`，而且它已經在
   每一個 fastapi 安裝裡了；`plotly` 從頭到尾不是 fjkit 的依賴（`figure_of()` 只要
   一個有 `to_plotly_json()` 的東西）。
3. 「詞彙表會多一個來源」——**打平**：CSS 增量是 byte-identical 的 0，詞彙表推導根本
   不讀 charts 的模板。`@source` 那一行是為了「將來 charts 的 macro 真的用到 utility
   時不會漏編」而留的保險，今天的實際貢獻是零。

**留在 wheel 內的三個正面理由：**

1. **一致性。** `fjkit.apidocs`、`fjkit.auth`、`fjkit.charts` 是同一種東西：wheel 內、
   要註冊才生效的外掛。把其中一個拆出去，得先說得出它跟另外兩個哪裡不同；說不出來。
2. **1.0 之前的版本矩陣。** charts 的 macro 從 `ui/attrs.html` 與 `ui/data.html` 的
   `card` import，plugin 吃 `AppSetup`／`EnvSetup`／`static_url`。這些簽名在 1.0 凍結前
   還會動。同一顆 wheel 表示改簽名那一筆 commit 當天就被 kit 自己的測試抓到；拆出去表示
   要維護一張 fjkit × fjkit-charts 的相容表，而這個 repo 已經有九個要發的發行物。
3. **不畫圖的 app 付的代價。** 13,979 bytes 的下載，與同一顆 wheel 裡的
   `lucide.json`（366 KB）和八份 Basecoat 樣式（各約 42 KB）不是同一個數量級。

**順手修掉的兩句不精確說法**（都是這次覆核才發現的）：

- `charts.js` 是 **9,123 bytes raw / 3,899 gzip**，不是「3 KB」——上一則紀錄與 commit
  訊息寫的 3 KB 是 gzip 後的數字。重點是它**確實是一份住在 wheel 裡的使用者端 JS**：
  §7 那條上限的正確讀法是「**每一頁預設**載入的只有 htmx + basecoat」，外掛的資產只有
  在頁面自己呼叫 `chart_scripts()` 時才出現。這一點在 (b) 之下完全一樣，因為
  `charts.js` 不管住在哪顆 wheel 都要被那一頁載。
- 「`chart_scripts()` 不吐 script」精確的說法是「**不吐 Plotly 那一行 script**」：
  `charts.js` 仍然載入，並在 console 講明白 Plotly 不在——那正是要的行為。

**守門測試補強了兩處**：`fjkit/charts/` 的豁免改成比對**相對路徑**而不是目錄名（否則
任何將來叫 `charts` 的目錄都會白白繼承豁免），並新增
`test_the_charts_exemption_covers_pydantic_and_nothing_else`——豁免只對 `pydantic` 成立，
多一個第三方 import 就紅燈。

**還掛著等人簽字的只剩一件**：`figures.py` 的 `pydantic`（CHARTER §11 第 2 條）。留在
wheel 內這個決定**不改變那個問題的內容**：(b) 是唯一能讓 pydantic 從 fjkit 自己的依賴
清單上消失的做法（它會變成 fjkit-charts 的依賴），但那是把問題換一顆 wheel 放，不是
回答它。否決時的修法仍然是把 `figure` 退成 plain dict、犧牲 OpenAPI 精度。

### 載入指示提前（2026-08-17，使用者指定）

`spinner` 在路線圖上屬於 **0.6 回饋層**，這次提前做（路線圖順序的調整，由使用者
直接指定，非我自行決定）。理由與代價：

- htmx 讓「請求在飛」變成第一週就會遇到的狀態。沒有元件，app 只能自己寫 `<svg>`，
  那同時是顏色字面值與封閉詞彙表外的動畫，正是 `fjkit check` 要擋的東西。
- `packages/fjkit/docs/workbench/page.template.html:477` 原本寫著「fjkit ships no
  indicator CSS yet (roadmap 0.6)」，並自己手刻了 `.t-spin`／`.t-indicator`。這次落地
  之後那段註解不再成立。
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
  點外面關閉、焦點回到觸發元素全部由瀏覽器負責。fjkit 一行 JS 都沒加，因此不必動到
  「引入自己寫的 JavaScript 要先問人」那條界線。
- **代價是「不是 modal」。** popover 不會把背景 inert，Tab 與螢幕閱讀器仍然到得了
  後面的頁面，所以標的是 `role="dialog"` 而**不寫** `aria-modal`：寫了就是對螢幕
  閱讀器說謊。真正的 modal 需要 `showModal()`，那是要不要出貨 JS 的決定，留給人類。
  「確定要刪嗎」這種不能被繞過的情境，繼續用 `hx-confirm`（那是瀏覽器自己的
  modal）。
- **CSS 幾乎沒動**：`.dialog` 的樣式 basecoat 早就出貨了，只補兩個 `data-size`
  寬度（延伸 basecoat 既有的屬性 API，不新增 class）與 body 的 `overflow-y-auto`。
- **`<div popover>` 而不是 `<dialog popover>`**：沒有任何東西會呼叫 `showModal()`，
  用真的 `<dialog>` 只是把兩套開關狀態混在一起。basecoat 的 `.dialog` 是 class
  選擇器，`:popover-open` 那條規則上游本來就寫了。

實作時在瀏覽器裡抓到一個沒有錯誤訊息的 bug，已修並補了回歸測試：
**htmx 的 `hx-swap` 會從祖先繼承**。Details 按鈕長在會每秒替換自己的卡片裡，而那張
卡片帶著 `hx-swap="outerHTML"`。繼承下來就會把 dialog 的 `<section id="…-body">`
整個換掉、連 id 一起帶走：第一次打開正常，之後每次都填不進東西。觸發元素巢狀在
另一個 htmx 元素裡時，`hx-swap` 一定要自己寫明。

**未做，同一個理由**：workbench 也還沒加 `dialog` 條目。

### `sidebar` 提前（2026-08-18，使用者指定）

**0.5 應用外殼** 的第一件，提前落地（路線圖順序的調整，由使用者直接指定）。

- **成本只有模板。** `.sidebar` 的 CSS basecoat 早就出貨（CSS 預算那個「棘輪已經扣完」的
  推論第三次被驗證），JS 也在 vendored 的 `all.min.js` 裡。所以這次新增的不是元件，
  是 fjkit 形狀的門：路由名而不是 URL、icon 用名字、封閉列舉、簽名裡沒有 class 字串。
- **shell 用「block 是不是空的」切換版型。** Jinja 問不到一個 block 有沒有被填，
  所以 `ui/shell.html` 先把 `{% block sidebar %}` 收進變數再判斷。代價是側欄的標記
  會先進 buffer（幾百 bytes）。換到的是 app 只要填那個 block，不必再多設一個旗標，
  而會被忘記的旗標等於沒有。
- **相鄰性是 shell 的責任。** basecoat 把讓開的 margin 給 `.sidebar + *`，所以內容
  wrapper 必須是 aside 的**下一個兄弟**。中間插任何東西，margin 就落在錯的元素上，
  頁面滑到側欄底下，而且沒有錯誤訊息。同理那個版型不能用 `mx-auto max-w-6xl`：`mx-auto`
  是 utility，basecoat 的 margin 是 components layer 的 `@apply`，utility 會贏。
  兩件事都由 shell 寫死，並各有一條測試守著。
- **group 用 `aria-label` 而不是 `aria-labelledby`。** 後者要每個 group 生一個 id，
  而同一個側欄可能在一頁裡出現兩次（htmx 換掉一份），重複的 id 會讓 `aria-labelledby`
  指到**錯的**標題，比指不到還糟。
- **`--sidebar-*` 改指向既有的中性色**（`var(--card)`／`var(--border)`／`var(--accent)`…）。
  basecoat 把它們定義成純灰，貼在帶著品牌色調的頁面旁邊看得出來，深色模式尤其明顯。
  改掉之後 A3 仍然成立：一個設定值連側欄一起換。`:root` 與 `.dark` 各寫一份，因為
  basecoat 自己的 `.dark` 會蓋掉 `:root` 的定義。
- **唯一的 JS 是 trigger 的 `onclick`**，呼叫 basecoat 自己掛在元素上的 `toggle()`，
  跟 `theme_toggle` 同一個形狀。沒有新增 fjkit 自己的邏輯，但這條靠近「不自己寫
  JavaScript」那條界線，記在這裡讓人類看得到。

**demo 的 parity**：`ids` 是 exact 欄位（id 就是 htmx target，靜靜多一個或改名正是
swap 落錯地方的起點），所以側欄那個 `sidebar` id 逐條寫進 `ALLOWED_CONTRACT_DRIFT`，
不是開一條規則放行。文字與連結一個都沒少，導覽只是從 header 搬到側欄。

**未做**：workbench 的條目（跟 `dialog` 同一個理由）。

### demo 的 style picker（2026-08-19，使用者指定）

八個風格包全部進 wheel 之後，要比較它們得改 `FjkitConfig(style=...)` 再重啟。demo
的 header 因此多了一顆下拉，**這是 demo 的東西，不是 kit 的**：

- **伺服器端一個位元組都沒變。** `FjkitConfig.style` 仍然是每個 process 一個包，
  shell 仍然 link `fjkit-vega.css`。換掉的是瀏覽器裡那個 `<link>` 的 href，所以
  config.py 那句「style 不是 per-request 的值」仍然成立：同一頁不會有兩份
  stylesheet。
- **手寫 JS，屬於需要人類授權的那一類，由使用者直接指定。** 15 行，全在
  `examples/fjkit-demo` 的 `base.html`，套件裡一行都沒加。放在 `head` 而不是 body
  尾巴，理由與 shell 的深色 flash-guard 相同：晚一步套用就是看得見的幾何閃動。
- **包名對 URL 的對照表由 Python 建**（`main.py` 的 `STYLE_SHEETS`），JS 只做查表。
  查不到就不換，所以 `localStorage` 裡的髒值造成的是「維持原樣」，而不是「唯一那份
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
  `plotly.js-basic-dist-min@3.7.0` 是 1,119,926 bytes，完整包 4,851,164，差兩個
  數量級，預算放不下。所以它 vendored 在 `examples/fjkit-demo/app/static/`，
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
  的尾巴，所以 OpenAPI 報的是 `additionalProperties: true`。
  代價寫在 schemas.py 的 docstring 裡：**尾巴擋不住顏色**，`#1F77B4` 是合法的
  `str`。所以 `test_no_figure_on_the_page_contains_a_colour` 從「有比較好」升級成必要
  條件，它掃的是**算完的 JSON**，不管位元組從哪個欄位來。另外補了結構性的一條
  （`marker` 裡不得有 `color`／`colors`），因為 regex 抓不到 `"red"` 這種具名色。
- **`figure_of()` 會把 `template` 拔掉。** `plotly.py` 就算 `template=None` 也會寫一個
  進去，而**預設的 template 是 7,621 bytes、裡面有 111 個色值字面值**（實測），全是
  這頁不畫的 trace 的 colorscale。拔掉之後三張圖的 payload 是 290／460／408 bytes。
- **整數刻度改由 Python 決定。** Plotly 會把一個計數標成「1.5」。哪些刻度合法是關於
  資料的事實不是畫法，所以由手上有資料的那邊算一次（`_integer_axis`），而不是讓畫的
  那邊各自再推一次——那正是兩個渲染器會漂移的地方。
- **量過才發現的一件事：`fillStyle` 來回不會把 oklch 轉成 rgb。** 原本的做法是把值
  指給 canvas 的 `fillStyle` 再讀回來，靠瀏覽器正規化成 `#rrggbb`。它只對
  legacy 格式成立；CSS Color 4 的顏色函式會**原樣保留**，`oklch(0.72 0.15 275)` 進、
  `oklch(0.72 0.15 275)` 出。Plotly 用的是 tinycolor2，不認識 oklch，於是**不報錯**，
  直接改用自己的預設調色盤畫。三張圖都畫得出來，只是顏色全是 Plotly 的
  `rgb(31,119,180)`／`rgb(255,127,14)`／`rgb(44,160,44)`。
  改成畫一個 1×1 像素再 `getImageData` 讀回 sRGB 位元組：這條路對任何瀏覽器解析得了
  的記法都成立，順便做了正確的色域裁切（Plotly 吐的 SVG 本來就是 sRGB）。
  **這個 bug 沒有任何測試會抓到，也沒有截圖抓得到**，除非你知道 fjkit 的 primary
  應該長什麼樣。是逐元素比對 headless Chrome 的 DOM 才看出來的。
- **第二件量出來的事：Plotly 的圓餅 `textfont` 預設 #444，不繼承 `layout.font`。**
  切片上的數字因此在深色模式下是深灰壓在飽和色上。沒有補一套 per-role foreground
  token（basecoat 根本沒有 `--destructive-foreground`），而是把標籤移到切片外——放在
  卡片上，那裡只有一個前景色，而它已經解析好了。
- **先做了自訂的封閉 spec，再換成 Plotly 的 figure。** 第一版是自己的
  `Spec`／`Trace`／`TraceKind`，`charts.js` 裡有一張 spec→Plotly 的對照表。換掉的理由
  是：一旦把真的會用到的欄位型別化，那份 spec 就收斂成換了名字的 Plotly（`kind` 對
  `type`、`x`/`y` 相同），差別只剩尾巴開不開。開尾巴才拿得到整個
  函式庫，而尾巴唯一的風險（顏色）本來就由測試守著，不是型別守著。
  自訂 spec 的價值要到「有第二個渲染器（伺服器端 SVG）」那天才兌現，那天還沒到。
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
  queue」；role 拿掉之後灰色不存在，句子變成假的。改成不指名顏色的講法。
  這是「調色盤不是自己的」最便宜的一種代價，也是沒有任何測試抓得到的一種：
  只有把頁面看過一遍才會發現。
- （已作廢的中間版本）**`roles` 曾經改成可選，六張圖分兩種。**
  有語意的三張（狀態、堆疊、趨勢）給 role，顏色從 token 解析，跟著主題走；沒語意的
  三張（owner 佔比、intake、最舊未完成）不給，Plotly 用自己的調色盤。判準寫在
  `Chart.roles` 的註解裡：**四個 owner 就是四個 owner，沒有哪個 role 屬於「kai」，
  硬指派一個等於讓圖表宣稱資料沒說的事**。代價也寫下來了：那三張不跟著深色模式變。
  狀態色沒有一起拿掉是因為 A3，「綠色代表完成」要能撐過改品牌，那是刻意保護的。
  **不變的部分**：figure 裡一個顏色都沒有，兩種圖都是。切片間隙與標籤文字也跟著
  token，因為它們是卡片的屬性不是序列的屬性。
- **頁面上那句說明有兩處是錯的，已改。** 「The figures name a role」——改成 B 之後
  figure 裡沒有 role 了；「and the style picker」——**八個風格包在 `styles/*.css` 裡
  一個顏色 token 都沒定義**（查證過），它們只差幾何，所以換包不可能改變圖表讀到的顏色。
  `charts.js` 的註解寫的正是這件事，頁面上卻寫了相反的話。兩句都留了註解說明為什麼
  不要再寫一次。
- **加一張水平長條圖，逼出了型別的一個錯誤假設。** `x: list[str]`／`y: list[float]`
  在第一張 `orientation="h"` 出現前都成立。Plotly 的 `x`／`y` 是**軸**，不是「類別」
  和「數值」，水平長條把數字放 `x`、標籤放 `y`。兩邊都放寬成 `list[str | float]`。
  這是整個模組在講的那件事的縮小版：**別人 schema 的型別化子集是一個猜測，尾巴是
  猜錯時不會致命的原因**。`orientation` 和 `hovertemplate` 本身就走尾巴，
  `test_the_typed_subset_survives_a_horizontal_bar` 守著這條路通得了。
- **刪掉一條自己發明的測試。** 本來寫了「每個 `ChartRole` 都要有圖用到」，套用的是
  「封閉列舉的每個值都渲染一次」。那條規矩給元件的封閉參數用，套到 app 的領域列舉上
  會**為了湊滿列舉而逼出圖表**，方向反了。role 的 token 缺漏本來就有
  `test_every_role_the_server_can_send_has_a_token` 在守。
- **驗證是在真的瀏覽器裡跑的**，用 CDP 驅動 headless Chrome：三張圖都畫出來、翻
  `.dark` 之後線色從 `rgb(138,155,255)` 變成 `rgb(78,86,211)`（就是兩個主題的
  `--primary`）、htmx swap 之後三張都重新初始化且 x 軸換成 priority、`hx-push-url`
  有更新網址。swap 出去的那半邊（`Plotly.purge`）掛在 `htmx:beforeCleanupElement`
  上——圖表放在 partial 裡最常忘的就是這一半。
- **`test_conventions.py` 那條 `app/static` 不得存在改了。** 它的 docstring 講的是
  stylesheet 與建置步驟，斷言卻是整個目錄。改成斷言真正的不變量：`app/` 底下沒有
  任何 `.css`、repo 裡沒有 `package.json`、沒有 `node_modules`。另外加一條：
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

兩個推論：

1. **原訂的 100 KB raw 上限從一開始就達不到**，那是我在量測前寫的數字。
2. **「只增不減的單向棘輪」這個擔憂大致是錯的**：棘輪已經扣完了。之後補
   `tabs`、`dialog`、`accordion` 等元件，CSS 幾乎不會變大，因為它們的樣式已經在裡面。
   還會成長的只有自己模板用到的 utility，實測整批模板才 8 KB。

**參考點**：Bootstrap 5 minified 約 232 KB raw / 30 KB gzip。我們 224.8 KB raw /
23.2 KB gzip / 18.3 KB brotli——線上傳輸量比 Bootstrap 小。

**已核可的處置**（2026-08-16）：預算改以 **gzip** 為管制數字（stdlib 就能量、可重現、
不需額外依賴），brotli 當參考值。品質預算已更新為 gzip ≤ 28 KB、raw ≤ 260 KB（防暴衝用）。
`fjkit build-css` 每次建置都會印出兩個數字並在超標時回傳非零。

---

## 渲染效能：實測與待決

用相同路由比較舊 `app/` 與 `examples/fjkit-demo`（median of 60）：

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
「跳過呼叫」比「讓呼叫變便宜」有效：Python global 版本輸給加保護的 Jinja 版本，
因為常見情況是 kwargs 為空，保護直接省掉全部工作。已套用到全部 6 個模板。

### 剩下的 23%：元件系統的固有成本

profile 顯示儀表板一次渲染做 **126 次 macro 呼叫**（舊版 inline 約 20 次），
每次約 2.5 µs ≈ 0.31 ms，等於量到的差值。這不是 bug，是把排版變成元件的代價。

絕對值是每頁 0.3–0.4 ms，在一次 DB 查詢面前可以忽略。

**待決（放寬品質預算需人類決定）**：預算寫「單頁渲染回歸不得慢超過 10%」。
這條規則的原意應該是「fjkit 不得一版比一版慢」，而不是「fjkit 必須追平手寫 inline markup」；
後者在元件化的前提下不可能成立。建議：

1. 10% 的門檻改為**版本對版本**的回歸檢查（以本次數字為基準線）。
2. 另外記錄「元件系統相對 inline 的一次性成本」為已知量，不當作回歸。
3. 熱迴圈的成本用 0.4 的 **data-driven table**（`table(columns, rows, fields)` 由 macro
   自己跑迴圈、inline 產生 `<td>`）來回收——現在這個設計有實測支撐，不再是臆測。

---

## 路由風格：`@render` 裝飾器（2026-08-17）

`templates.page()` 寫在 handler 內，在還只該談資料的地方把路由綁死成 HTML，
而且每條路由都要多帶 `request`、`templates` 兩個只為了原封不動傳回去的參數。
改成模板名掛在裝飾器上，handler 只回傳 response model：

```python
@router.get("/tasks", name="tasks_page")
@render("tasks/page.html", partial="tasks/_board.html")
def tasks_page(service: ServiceDep, status: Status | None = None) -> BoardResponse:
    return board(service, status)
```

**回傳型別註解是唯一的契約。** FastAPI 本來就讀它推導 `response_model`，`@render`
把同一個 model 攤進模板 context。OpenAPI 與模板吃同一份宣告，不可能各說各話。
頁面上看得到的展示值（badge variant、百分比）改用 `@computed_field`，因此它同時
存在於 JSON，而不是只活在 Jinja 裡。

**兩種表現形式，兩層旗標。** `FjkitConfig(render_mode=...)` 是 app 預設，
`@render(..., mode=...)` 蓋掉單條路由。`"json"` 時回傳值原封不動交回 FastAPI 走
`response_model`。旗標在 request 時解析而非 import 時，否則答案會取決於 import 順序。

**預設是 `"auto"`（2026-08-19，使用者指定）。** 判準是「這個請求有沒有 HTML 可以拿」
而不是「誰在問」：有 `partial=`、或模板不是 `_*.html`，就是頁面，任何人來都渲染；
純 fragment 的路由只回應 htmx，其他人拿 `response_model` 的 JSON。所以 swap 端點
自動成為 app 的 API，而 demo 一條 `mode=` 都不用寫，那正是這個規則的驗收條件。

反過來的規則（「有 htmx header 才給 HTML」）不能當預設：頁面最重要的那個請求——
打網址、重新整理、書籤、上一頁、爬蟲——身上沒有任何 htmx header，會直接拿到 JSON。
判斷 fragment 用的是 `_*.html` 命名，那條慣例 `test_conventions.py` 本來就在守。

三個連帶結果：**JSON 變成對外契約**（`JobDetailResponse.timeline` 那三句英文散文
現在是 API 輸出，要擋就寫 `mode="html"`）；**boost 走 HTML**（`_is_htmx` 不排除
`hx-boosted`，跟 `_is_htmx_swap` 是兩個問題）；**回應帶 `Vary: HX-Request`**，因為
一個 URL 兩種回應而沒有這個 header，快取會把 fragment 餵給一次整頁導覽。

測試那邊多了一個 `htmx` fixture，parity 的 probe 也補上 header：只有 htmx 打得到的
端點，用不帶 header 的請求去驗證等於在模擬一個不存在的客戶端。舊 app 不讀 htmx
header，所以 baseline 不用重抓，`EXACT` 那七個欄位仍然逐一比對。

**`partial=` 讓 A6 由套件保證。** htmx request 拿 partial，一般 request 拿整頁，
handler 分不出差別。`hx-boosted` 刻意排除——boost 是 htmx 在做一般導覽，塞 fragment
會讓瀏覽器停在沒有 shell 的文件上。

實作上三個非顯而易見的點，都各有一條測試守著：

1. **wrapper 的同步性必須跟著 handler。** `def` 包成 `async def` 會把每次渲染搬到
   event loop 上，違反 CLAUDE.md 那條 threadpool 規則，而且不會有任何錯誤。
2. **註解要自己解析。** FastAPI 用 `endpoint.__globals__` eval 字串註解，而 wrapper 的
   globals 是 fjkit 的，app 的名字在那裡不存在。改用 `get_type_hints` + 裝飾當下那層
   frame 的 locals（函式內定義的 model 才找得到）。
3. **`status_code=` 與 handler 設的 header 要自己併。** FastAPI 只把它們併進自己組出來的
   回應；這裡回應由裝飾器組，不併就會靜靜消失。優先序：handler → route → 200。

**非目標的敘述已改寫（已由人類核可）**：原文「不輸出 JSON API 給前端框架用」與
一份有文件的雙協定契約衝突。改成：不為了餵前端框架而設計 API，但同一條路由的
JSON 表現形式是一等公民，描述的是**這個頁面被交到手上的資料**，由回傳型別註解定義。
判準因此明確：頁面不需要的欄位不會為了 JSON 而加進 response model。

**尚未處理**：`status_filters` / `priority_options` 仍是 `(value, label)` tuple，
因為那是 `ui/form.html` 的 `select_field` 吃的形狀，OpenAPI 上會呈現成兩元素陣列。
改成 `Option` 物件會動到已發佈的 macro 簽名（那需要人類核可），而且 tuple 字面值
（`options=[("a", "A")]`）在模板與測試裡直接可寫，換成物件就得多一個 Jinja global
才能保住同樣的寫法。收益（兩個欄位的 JSON 形狀）小於代價，等真的有客戶端在讀
這份 JSON 時再決定。

---

## 文件站改成三頁，由 fjkit 自己的 Environment 渲染

原本的 `docs/index.html` 是一頁十一課、484 KB 的單一檔案，由
`page.template.html` 加三個 `str.replace()` 標記組出來。那套組裝法撐不到第二頁：
共用外殼需要 `{% extends %}`，重複的 stage／code-tab 需要 macro。

**三頁，各有明確的讀者問題：**

| 輸出 | 頁 | 回答的問題 |
|---|---|---|
| `docs/index.html` | Learn | 這些東西怎麼組在一起？htmx 到底送了什麼？ |
| `docs/components.html` | Components | 這個 macro 吃什麼參數，長什麼樣？ |
| `docs/example.html` | Example | 真的寫起來，一支 app 長什麼樣？ |

（後續：`index.html` 已改成 Introduction 首頁，Learn 移到 `learn.html`，見下方
〈文件站加上 Introduction 首頁〉。）

**渲染器就是 fjkit 自己。** `build_environment(FjkitConfig(template_dir=...))`：
同一個 loader、同一套 autoescape、同一組 globals。文件站因此是套件的下游，
kit 壞了文件就 build 不出來。頁面模板放在
`packages/fjkit/docs/workbench/templates/`，本身就是一組 fjkit 模板，並且照 kit
要求 app 做的事情做：重複出現的東西（lesson、files、defs、stage_bar）是 macro，
不是複製。刻意**不** extends `ui/shell.html`：文件外殼是 `t-` 前綴、不會伸進
preview 的 CSS，讓文件繼承被示範的那層 shell 會使兩者分不開。

**Example 頁的每一行程式碼都是從 `examples/fjkit-demo` 讀出來的。** build 時讀檔，
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
`grid`／`stack` 組出來，跟 `examples/fjkit-demo` 呼叫的是同一批 macro。

**驗收是 `fjkit check` 跑在文件站自己的模板上，而且過。**
`packages/fjkit/tests/test_docs_site.py` 把它變成測試。`docs.css`（603 行手寫
外殼）刪掉，換成 `assets/brand.css`。

**兩個 config 旋鈕就把 app 變成靜態站，不必改 shell 一行：**

- `static_url="assets"` — `fjkit_static('dist/fjkit.css')` 解析成頁面旁邊的路徑，
  靜態樹照 `mount_ui()` 服務的形狀複製過去。
- `globals={"url_for": ..., "is_active": ...}` — 套件版的會呼叫 `request.url_for`，
  build 時沒有 request。替代品簽名相同，讀 `request.route`（context 傳進去的普通
  物件）。route **名字**仍然是通用貨幣，所以 `sidebar_link`、`brand` 原封不動可用。
  route 名字可以帶 fragment（`learn#wiring`），頁內導覽因此不必第二套機制。

**免費拿到的東西**：Basecoat 的 JS（shell 本來就載）接管了 `.tabs` 的選取與
方向鍵、`input[type=range]` 的填充軌、sidebar 的收合。文件站因此**刪掉了自己的
tab 控制器**，三處 tab 都不再綁 click listener。

### 這一輪的產出：七個「說不出來」的洞

文件站比後台難，因為它會要求後台不需要的形狀。凡是詞彙表講不出來的，都集中在
`assets/brand.css` 的 PART 2，每一塊都標了缺的 macro 是什麼。**PART 2 的長度
就是「封閉詞彙表夠不夠用」的答案。**

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
改用 `[data-field-row]` 屬性 + brand.css，並標成 GAP 7，但機制上擋不住任何人
那樣做。

另外兩個既有元件的缺口，順手記著：`item`／`item-group` 有 CSS 沒有 macro（定義
清單與 log 列表直接寫 class，`fjkit check` 允許，因為它們**是**詞彙表的一部分）；
`field_row` 沒有 `"four"` 版型。

### `fjkit check` 的一個真 bug

顏色字面值的規則掃**每一行**，不只 `class="..."`。所以文件寫不出它正在警告你
不要用的 utility：`<code>text-white</code>` 這句話本身會讓 check 失敗。目前是繞過
去（改寫成「an absolute white」），正解是顏色規則跳過註解與文字節點，或提供
pragma。`examples/fjkit-demo` 撞不到，只是因為 app 模板不會討論顏色。


---

## 把文件站的自訂 component 補進 library

上一輪列出七個「詞彙表講不出來」的洞。使用者直接指示把它們補進套件，所以做了。
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

`packages/fjkit/tests/test_components.py` 各補了合約測試，特別是 aria 配對：那組
屬性寫錯時，tab 會安靜地停止切換，不會有任何錯誤訊息。

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
抄進 `.js` 檔就能繞過 `fjkit check`，**因為它只讀模板，不讀腳本**。這次用
`[data-field-row]` 屬性 + brand.css 標成 GAP 4，沒有那樣做，但機制上擋不住任何人。

兩條出路，都不是新 macro：控制項改成伺服器端渲染、瀏覽器只負責 bind；或者讓
`fjkit check` 也讀 `.js`。

---

## 文件站加上 Introduction 首頁（三頁變四頁）

三頁都在教，沒有一頁回答**「這是什麼、適不適合我」**。而 GitHub Pages 送出的
第一個檔案是 `index.html`，原本是 Learn，第一課直接從 wiring 講起。一個沒聽過
fjkit 的人，落地的第一頁就是課程第一課。

**新的第一頁：`templates/introduction.html` → `docs/index.html`，Learn 移到
`docs/learn.html`。** 五段，全部指向別頁而不是自己解釋完：

| 段 | 內容 |
|---|---|
| What it is | 一句話定位、release-time Tailwind 的限制，加兩個從 `examples/fjkit-demo` 讀出來的檔案（`main.py`、`tasks/page.html`） |
| Who it is for | 該花多少力氣（第一頁、後台頁、換品牌、升級）對上四個非目標 |
| Five decisions | 決定／買到什麼／**靠什麼守住** 的表格——第三欄才是重點 |
| What is in the box | 套件裡有什麼、你會碰到的整個 API 面、Python 3.13 + 兩個 runtime 相依 |
| Where to go next | 站上三頁、repo 四份文件，加上跑 demo 的兩行指令 |

**`build.py` 的 `PAGES` 是唯一的資料來源**，所以側欄、`url_for`、`<head>` 的
metadata 全部跟著改，模板一行都不用動。`test_docs_site.py` 的 `PAGES` 補第四頁。

**順手拿掉的**：四頁 `page_header` 裡的跨頁按鈕（Components／Example →）。側欄已經
列了全部四頁，那組按鈕是第二套導覽，而且每頁都要手動維護「下一頁是誰」。由使用者
指示移除。

**破壞性變更**：Learn 的網址與它所有的 `#anchor` 從 `index.html` 移到
`learn.html`。站是 pre-release，沒有對外連結需要保。

**一併刪掉**：`packages/fjkit/docs/introduction.md`——同樣的內容先寫成 markdown 的
那份試作。站上的 Introduction 頁取代它，兩份會漂移。

`CLAUDE.md` 與 `README.md` 的倉庫地圖同時更新（上一條的待決事項），現在寫的是
四頁的實況。

---

## 兩個邊框重疊（由使用者回報）

文件站上有兩處邊框互相疊在一起。兩者不是排版沒調好，各自有一個具體成因，所以分開記。

### 1. tab 列的幽靈捲軸——`fjkit.css` 對 Basecoat 的假設是錯的

`ui/tabs.html` 與 `fjkit.css` 都寫著「Basecoat 的 `.tabs` 只給結構、完全沒有皮」。
**對 `components/tabs.css` 而言是對的，對 style pack 而言是錯的。** vendored 的是
`basecoat.css → basecoat-vega.css → styles/vega.css`，而 vega 有一整套 tabs 皮，
還附一個 `data-variant="line"` 的底線變體。fjkit 在它上面又畫了第二套底線皮，
兩套互相打架：

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
  不是 `visible`，`overflow-y: visible` 就**計算成 `auto`**，所以那 8px 溢出長出一條
  垂直捲軸，捲軸的 thumb 壓在 card 的右邊框上。這就是回報的「邊框重疊」。
  四頁共 8 個 tab 列，每一個都是。

**修法**：不改 macro，只在 `fjkit.css` 把 vega 的幾何全部關掉
（`h-auto rounded-none bg-transparent p-0`）、用 `after:hidden` 拿掉 pack 那條
`bottom-[-5px]` 的底線偽元素（它本身就是 5px 的溢出來源），並把選取規則加一個
只用來配 specificity 的孿生選擇器。tab 列高度改由內容決定（39px），溢出歸零，
捲軸消失，而且 fjkit 寫在註解裡的底線外觀**第一次真的畫出來**。

CSS 預算：23.8 → 23.9 KB gzip（上限 28 KB）。

**留給以後的**：更乾淨的作法是直接用 vega 的 `data-variant="line"`，那就是
fjkit 想要的底線 tab。這次沒做，因為 vega 的 line 變體仍保留 `h-9 p-[3px]`，
而它的底線偽元素釘在 `bottom-[-5px]`：要嘛留著溢出，要嘛 `overflow` 把底線裁掉。
選一個之前，得先決定 tab 列要不要橫向捲動。

### 2. `#checker-output` 的 25 個 alert 互相貼死

Learn 頁的 `fjkit check` 示範把每個違規渲染成一個 `alert`，塞進一個沒有間距的
`<div>`。25 個 1px 邊框首尾相接，每個交界都變成 2px 的粗線，兩顆圓角還撞在一起。

**修法**：容器改成 `stack(gap=2, id="checker-output", aria_live="polite")`。
`stack` 本來就吃 `**kwargs` 走 `attrs()`，所以 id 與 aria 屬性照掛，JS 一行都不用動：
它注入的還是 `innerHTML`，只是父層現在是有 gap 的 flex column。

這個洞是 GAP 4 講的那件事的另一面。腳本生成的標記沒有任何閘門看得到，
`fjkit check` 讀模板不讀 `.js`，所以「忘了給間距」這種事只能靠眼睛或靠瀏覽器量。
這次是用一支量測腳本掃四頁的 border 座標抓出來的，不是用看的。

## 八個 Basecoat 風格包全部 build 進 wheel（2026-08-19）

`theming.md` 原本把「要 ship 幾個 skin」列為待決，理由是**會動到 CSS 預算**。
量完之後那個理由不成立：第 7 節的預算是**每頁**預算，而一頁只載一個包。

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

vega 的位元組與改動前的 `dist/fjkit.css` 相同，所以這次不是換皮，是多七個選項。
另外七個在 wheel 裡是 167 KB（deflate），只付一次安裝成本，瀏覽器不會多下載一個位元組。
**選風格因此是 config 值而不是重裝**：`FjkitConfig(style="nova")`，重開即可。

做法：
- `src/fjkit.css` 的風格包 import 加上 `/* fjkit:style-pack */` 標記，`build-css`
  只改那一行，其餘共用。改壞標記會**明確報錯**，不會默默 build 出八個一樣的檔案。
- 產物改名為 `dist/fjkit-<pack>.css`，`dist/fjkit.css` 不再存在。
- shell 依 `fjkit_style` 組出 link，`mount_ui` 檢查的是**設定的那個包**。
- `test_style_packs.py` 釘住關鍵前提：八個包 emit 的 class 集合**完全相同**。
  這是換包不用改任何 template 的原因；一旦不成立，`fjkit check` 與全部 template 都會受影響。

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

裝了兩個就不自己挑一個：挑了等於讓頁面長相取決於 metadata 掃描順序，那種 bug 連
bisect 都抓不到。

**marker 被排除在 workspace members 之外**（`exclude = ["packages/fjkit-style-*"]`）。
workspace 會把所有成員都裝上，八個一起裝正好撞上上面那條歧義規則，`uv sync` 之後
整個 repo 開不起來。它們是要發佈的東西，不是開發環境的一部分。

已用一個 scratch 專案實測過完整路徑：`uv add "fjkit[nova]"` → 不寫任何 config →
shell 送出 `/_fjkit/dist/fjkit-nova.css` → 200，238,673 bytes，跟 nova 的產物一致。

**要你點頭的**：這一步占掉八個 PyPI 名字 `fjkit-style-{vega,nova,maia,lyra,mira,luma,sera,rhea}`，
屬於第 11 節第 5 條（命名／PyPI 專案名）。第二階段真的要發佈前確認一次。

---

## 文件站砍掉 Example 頁，章節標題改成指名道姓（2026-08-19）

**Example 整頁移除。** 它的內容是 `examples/fjkit-demo` 的原始碼——`main.py`、tasks 的
router／service／schemas、三種 template、兩支測試——在 build 時讀進來排版一次。
那些檔案在 repo 裡就是原檔，讀者 clone 之後看到的是同一份而且可執行。文件站
複述一次，得到的是一份會過期的副本，還要 `DEMO_SOURCES` 與 `TREE` 兩張清單守著
才不會說謊。刪掉之後這兩張清單也跟著沒了：`verify_tree()`、`_parts.html` 的
`tree_table`、`test_the_tree_matches_the_demo`，以及 `DEMO_SOURCES` 裡除 Introduction
引用的兩個檔案以外的十五筆。

原本指向 Example 的連結改指 repo 路徑（`examples/fjkit-demo/`、
`examples/fjkit-demo/app/templates/tasks/`）：同一份東西，但指的是原檔而不是副本。
文件站剩三頁，`PAGES` 一改，側欄與 `url_for` 全部跟著改，模板不用動。這是
Introduction 那次加頁時建立的性質，反過來用一次。

**章節標題改成指名道姓的。** 原本的標題是命題（「The signature is the contract」、
「One partial, two doors」、「The rule that fails a build」），讀起來像章節大意，
但側欄「On this page」拿它當索引：想找 `hx-swap` 的人掃過八個命題，一個都
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

命題沒有丟掉：`lesson()` 的第四個參數（thesis）就是放這種句子的位置，每一節的
那一行都還在原處。動的只是索引欄顯示什麼。

---

## 文件站出中文版：三頁 × 兩語言，共用同一套骨架（2026-08-19）

英文留在原位（`docs/*.html`），中文放在 `docs/zh/`。**能共用的全部共用**：`base.html`、
`_parts.html`、請求流程圖，以及 `assets/` 底下每一支 js 與 css 都只有一份，兩邊都指到它。
分岔只有兩處：`templates/zh/` 的三頁散文，以及 `build.py` 裡的 `STRINGS`（側欄標題、
頁尾那句話、流程圖上的字）。

流程圖刻意不複製。它是一張手寫座標的 SVG，複製一份去翻譯等於維護兩套座標，
而第二套會先過期。所以圖裡每個字改成從 `t.diagram` 來，圖形本身只有一份。

| 東西 | 份數 |
|---|---|
| 頁面模板 | 2（`templates/`、`templates/zh/`） |
| `base.html`／`_parts.html`／`_diagram.html` | 1 |
| `assets/*.js`、`brand.css`、`data.js` | 1 |
| chrome 文字（rail、footer、圖標籤） | `build.py` 的 `STRINGS`，一個語言一組 |

### GitHub Pages 上真的會動嗎——這是這次唯一難的地方

Pages 服務的是 **project 子路徑**（`https://…/fjkit/`，不是網域根）。從本機把 `docs/`
當根目錄開一個 server，絕對路徑 `/assets/fjkit.css` 會通；上了 Pages 就 404。
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

`learn.js` 與 `components.js` 裡的 caption 仍然是英文：九種模式的說明、swap 組合的註解、
每個 macro 的那句話，大約 2,000 字。它們是散在程式裡的字串常數，要中文化得先抽成
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
只要把 `ValidationError` 填進 `error=`。

### 順手修掉的一個真 bug：`form()` 沒有 `target` 時仍然發 `hx-post`

macro 自己的註解寫著「a form with a target is an htmx form; one without is an
ordinary POST」，但程式碼只要有 `action` 就發 `hx-post`，從不發 `action=`／
`method=`。沒有 target 的 `hx-post` 會把回應塞進表單自己（htmx 的預設 target 就是
觸發元素），沒有人要這個結果。

沒被發現是因為 **demo 裡每一張表單都有 target**：三張都是 htmx swap，所以那半條
路沒被走過。這次補的 `/tasks/{id}/edit` 走的就是它：同一個 macro、同一批
欄位，不帶 `target`，關掉 JavaScript 照樣能用。

### demo 端

新的 `/tasks/{id}/edit` 頁（`tasks/edit.html`，`test_edit.py` 8 條）。它是這五支欄位的
驗收場，也是 demo 第一張非 htmx 的表單：POST 完 303 導回板子，重新整理不會重送。
`Task` 多了 `notes`／`blocked`／`watching` 三個欄位，寫入走 `TaskUpdate` 這個封閉清單，
所以 `status`／`id`／`created_at` 在**結構上**改不到，而不是靠表單剛好沒送。

板子每一列多一支鉛筆，是 `<a>` 不是 swap，所以 `test_parity.py` 的 `hx_attrs`／
`ids` 那幾欄一個字都沒動。

### 文件站

Components 頁的 form 選單從兩個狀態變五個：htmx 表單、錯誤、textarea + checkbox、
radios vs select、fieldset 裡的 switch。每一個的 Jinja 片段與預覽都由同一份
`build_data.py` 產出，所以頁面教不出 kit 沒有的簽名。

---

## `fjkit.apidocs` — 取代 Swagger UI 的 API 主控台（2026-08-21）

**痛點很具體：Swagger UI 的 Authorize 對話框只能表達 OpenAPI 文件說得出來的東西**——
apiKey、http scheme、oauth2、openIdConnect，就這四種。`fjkit.auth` 發出去的憑證是一個
簽章過的 HttpOnly cookie，四種都不是。就算文件寫得出來，Swagger 的 Try it out 在
瀏覽器裡跑 `fetch()`，而那個 cookie 不給 JavaScript 讀——那是 `AuthPlugin` 的設計，
不是缺陷。

所以這一版的作法是把兩件事都搬到伺服器：

| | Swagger UI | `fjkit.apidocs` |
|---|---|---|
| 登入 | 貼一個你從別處拿到的 token | `AuthFlow`，一個 Python 物件 |
| 送出請求 | 瀏覽器 `fetch()` | 伺服器行程內重放，帶上呼叫者自己的 cookie |
| token 換發／撤銷／CSRF | 頁面自己想辦法 | 請求走過的 middleware 就做完了 |

`SessionFlow` 直接呼叫 `AuthPlugin.issue`，也就是跑 app 自己的 `TokenSource`；登入完瀏覽器
握著的就是 app 平常那顆 cookie。之後每一次 Try it 都是把那顆 cookie 轉發進去，所以
token 到期換發、session 撤銷、Origin 檢查全都由 `AuthPlugin` 做，這裡一行都沒重寫。
沒有 `AuthPlugin` 的 app 用 `HeaderFlow`：token 存在這個外掛自己的簽章 HttpOnly cookie，
scope 限在文件頁的路徑底下，頁面上顯示遮罩過的值。

### 自動掛載

`FjkitConfig(plugins=(auth, ApiDocsPlugin()))` 是全部的接線：沒有路由要寫、沒有模板要
指定、沒有 static 要掛。外掛在 `mount` 裡 `include_router()` 自己那四條路由，並且從
`setup.config.plugins` 裡把 `AuthPlugin` 找出來自動包成 `SessionFlow`。這是 `AppSetup`
這個接縫第一次被用來加路由（`AuthPlugin` 只用了 middleware 與 exception handler）。

網址預設 `/api-docs`，不是 `/docs`：FastAPI 在 `FastAPI()` 建構時就把 `/docs` 佔掉，
Starlette 比對到第一條就停，所以掛在那裡會是一個永遠不會渲染的頁面。真的掛過去時
`setup.warn()` 在啟動時就說出來，不留給人點半天。

### 三件實作上非做不可的事

1. **重放用 ASGI scope 直接呼叫 `request.app`**，不開 socket。行程內、走完整條
   middleware stack，所以 `AuthPlugin` 的 session 載入與換發照跑。防遞迴用兩道：路徑前綴
   拒絕，加上 scope 裡的深度旗標。
2. **scope 裡的 header 名稱一律小寫。** ASGI 規定如此，而 Starlette 是照字面做的——它把你
   *要問* 的名字轉小寫去跟 raw bytes 比。`Authorization` 大寫 A 會在線上、卻對
   `request.headers["authorization"]` 隱形，而且沒有任何地方會報錯。（這條是寫測試才抓到的。）
3. **`$ref` 旁邊的關鍵字要跟著走。** OpenAPI 3.1 允許 `{"$ref": ".../Priority", "default":
   "normal"}`，FastAPI 對 `priority: Priority = Priority.NORMAL` 就是這樣寫。只解 ref、把
   兄弟鍵丟掉，select 就會渲染成沒有選項被選中——症狀只有「主控台起手就差一步」。

### 表單 body 拆成欄位，不是一個文字框

fjkit 的 app 大半是 `Annotated[str, Form()]`，每一個 htmx 表單都往那裡送。文件裡它是
`application/x-www-form-urlencoded`，schema 是一個有 `properties` 的物件，所以拆回欄位與
query parameter 走同一個 `Param`：enum 變 select、integer 變數字框、default 預填。JSON body
才留文字框。`multipart` 明講不支援，因為文字框裝不下檔案。

### 驗收

`examples/fjkit-demo` 註冊了它，`app/` 底下沒有為它寫任何一行路由或模板。守著的兩件事：

- `packages/fjkit/tests/test_apidocs.py` — 文件解析、掛載、重放、三種 flow，外加一條
  「這幾個模板裡的每一個 class 都真的在建置出來的 stylesheet 裡」。模板跟著外掛的程式碼放在
  `src/fjkit/apidocs/templates/apidocs/`，由 `extend` 掛上 loader；代價是 `fjkit.css` 必須多
  一行 `@source` 指到那裡——少了它會渲染、會看起來壞掉、不會有任何訊息，所以那條測試連
  `@source` 本身也一起釘住。
- `examples/fjkit-demo/tests/test_api_console.py` — `/session/secret` 這條 `Depends` 保護的路由，
  在 Swagger 上拿不到，在這裡登入之後回 200。那一條就是整個外掛的理由。

### 補：主控台拿到的是 model，不是頁面（2026-08-21）

第一版有一個答非所問的行為：`/tasks` 是 page route
（`@render("tasks/page.html", partial=…)`），所以 `render_mode="auto"` 下主控台按
Send 會拿回一整份 HTML 文件。`serves_a_page` 是**路由形狀**的屬性，存在的理由是保護
冷啟動的 navigation，而行程內重放不是 navigation。

修法是給 `@render` 補一個中間層：ASGI scope 的 `SCOPE_RENDER_MODE`。優先序變成
**decorator 的 `mode=` → scope 問的 → app 預設**。

刻意不是 header、不是 query parameter：只有已經在這個 process 裡的東西寫得進 scope，
所以這是「app 問自己要哪一種表現形式」，不是「client 要求被特別對待」。用 header 就等於
開一個開關，讓任何人把整個 app 的頁面變成 JSON。

`mode="html"` 仍然贏。那是 app 作者明講「這條路由沒有資料形式」，主控台不是推翻它的地方。
兩條測試守著：page route 從主控台回 model、同一條路由給瀏覽器仍然回整頁。

### 補：Swagger UI 有的，這裡也要有（2026-08-21）

第一版贏在 Swagger 做不到的那一半：登入是 app 自己的 Python 物件，請求帶著
HttpOnly cookie 在行程內重放。但那只有在**另一半也齊全**時才是換掉 Swagger 的理由。
一個在驗證上贏、在其他每一件事上輸的主控台不是替代品，所以這一輪把缺口補完。

| Swagger UI 有 | 這一輪補上 |
|---|---|
| Schemas 區塊 | `components.schemas` 變成側欄的第二個分支＋`/api-docs/schema/{slug}` 詳細頁 |
| Example Value / Schema 切換 | `payload()` macro，用 0.7 提前落地的 `ui/tabs.html` |
| 每個狀態碼各自的範例 | 每一條 response 一個區塊，不再只印 200 那一個 |
| 回應 header 文件 | `ResponseDoc.headers` |
| 上鎖圖示 | `operation.security` 渲染在 `op_line` |
| filter 搜尋框 | 伺服器端過濾＋`hx-get` 換掉清單（`/api-docs/nav?q=`） |
| servers 下拉 | 只列出、不選：行程內重放的目標永遠是正在回答的這個 app |
| 檔案上傳 | `multipart` 重新編碼後送進 app，curl 片段給 `-F` |
| 多個具名範例 | `openapi_examples=` 的每一個都是一個 tab |
| contact／license／terms／externalDocs／tag description | 首頁的 masthead 與 Groups 卡 |

三件實作上值得記下來的：

1. **OpenAPI 3.1 不寫 `format: binary` 了。** 3.0 是 `format: binary`，3.1 改成
   `contentMediaType`，而 FastAPI 現在吐 3.1。只讀 `format` 的話每一個 `UploadFile`
   都會渲染成文字框——送出去的是檔名字串，錯誤發生在 endpoint 裡面，離原因很遠。
   兩種拼法都要認。
2. **陣列參數是同一個名字重複，不是逗號字串。** `?tag=a&tag=b` 才是 FastAPI 解回
   `list[str]` 的形狀。一個框裝 `a,b` 會原封不動送出去，endpoint 收到一個元素的 list。
   所以 `Param.multi` 為真時，`_compose` 把一個欄位攤成好幾個值。
3. **面板 swap 要把側欄一起帶回去。** 點一條 operation 只換 detail panel，側欄不會重畫，
   所以 highlight 會停在三次點擊之前那一條——冷載入是對的、之後整個 session 都是錯的。
   `_nav.html` 在 swap 時掛 `hx-swap-oob`，並且把 `?q=` 帶在連結上，過濾狀態才不會被
   點擊清掉。

Jinja 上踩到的兩件事：這個 Environment 沒開 `do` extension（所以累積清單要用
`namespace` 重新指派），也沒有 list comprehension。兩處都寫了註解，因為下一個人
會再寫一次。

**「Extra headers 不要那麼顯眼」**：它從一個永遠展開的兩行 textarea 變成一個
`<details>`。上面每一個控制項都是文件要求的，這一個是文件沒要求的逃生口：它該在
頁面上，但不該在閱讀動線上。summary 補了一個 chevron，因為 Basecoat 的 base layer
把原生 marker 拿掉了，一行純文字看不出來可以打開；那是另一種壞法，不比太吵好。

---

## demo 的 Search 頁 — 一次請求換掉五塊，其中一塊自己再 swap（2026-08-22，使用者指定）

**demo 到這一輪為止只示範得出「一個 target」。** 板子上每一顆按鈕都指著 `#board`，
`_board.html` 是一張把所有會變的東西都包進去的 partial。那是對的，因為板子本來就是
一個東西。

搜尋結果不是。一次查詢要動的是：頂端一排計數、中間那張表、表格下面的明細面板、
右側的進度卡、右側的 facet 清單——五塊分散在三個地方，唯一同時包住它們的元素是
`<body>`。換掉 body 等於重新整理。

所以回應把另外四塊當作 **out-of-band** 送回去：htmx 先把回應裡每一個帶
`hx-swap-oob` 的頂層元素抽出來、依 id 各自換掉，剩下的才進 `hx-target`。一趟來回，
五塊更新。

### 兩個模板，同一批 partial

`page.html` 與 `_results.html` include 的是同樣五支 partial，差別只有一個變數：

```jinja
{% with oob = true %}{% include "search/_stats.html" %}{% endwith %}
```

每支 partial 開頭寫 `{% set oob = oob | default(false) %}`，所以它單獨渲染得出來
（`strict_undefined` 是開的，少了這一行，include 進頁面就爆）。**「這塊放在哪裡」由
頁面決定一次，「這是哪一塊」由回應決定**：把 facet 卡從側欄搬到主欄，router、
response model、swap 三者一個字都不用改。

`_matches.html` 是唯一不掛 `hx-swap-oob` 的一支，因為它就是 `hx-target`。掛上去是
一個 bug：htmx 把所有 oob 元素抽走之後，剩給 target 的是空字串。

### 巢狀：回應送回來的那批列，自己會再發一次 swap

每一列的最後一格是一顆 chevron，`hx-get` 指著 `/search/task/{id}`，
`hx-target` 指著 `#search-detail`，而 `#search-detail` 是**同一個回應**用 oob 送回去的
第五塊。**沒有任何一行程式碼去註冊它們**：htmx 對自己換進 DOM 的節點一律做 process，
in-band 與 out-of-band 都算，所以一個 keystroke 前才渲染出來的列，落地那一刻就是活的。

一個刻意的決定：**每次查詢都把明細面板清空**。上一次打開的那筆可能不在新的結果
裡，而一張描述已經不在畫面上的列的卡片比空面板更糟。要保留選取就得讓搜尋路由知道
「現在開著哪一筆」，那是把兩件事綁在一起。所以 `_detail.html` 的 `selected` 在搜尋
回應裡永遠是 `None`，`test_a_new_query_empties_the_panel` 守著這一條。

觸發器是一顆真的 `button`，不是掛 `hx-get` 的 `<tr>`。掛在 `<tr>` 上 htmx 照樣會動，
但那一列鍵盤到不了、螢幕閱讀器也叫不出名字：它會動，不代表它可用。

`task_row` 為此多了一個 `actions` 參數（吃已渲染的 markup，跟 `card(actions=…)` 同一個
形狀）。**搜尋頁因此不需要自己的列**：它交出一顆按鈕，拿回板子那四格原封不動的 cell，
所以 status badge 在兩頁上的顏色與欄位順序不可能漂移。

`Task` 多一個 `created_label` computed field。模板不格式化 datetime，因為那是模板在
決定一個日期是什麼意思，而且 JSON 客戶端得再決定一次。

### 這種 swap 錯了不會叫

oob **依 id 定址**。id 對不上時 htmx 直接把那塊丟掉：不報錯、不進 console，
那一區停在上一次查詢的數字上。所以 `test_search.py` 從兩邊釘死：頁面上每個 id
只准出現一次，回應裡每一個 oob id 都必須在頁面上找得到。

### 沒有 JavaScript 也走得完

輸入框帶 htmx 屬性，外面那張 `form()` 帶的是普通的 `action` + `method="get"`。打字是
四塊 swap，按 Enter 或關掉 JavaScript 就是 `GET /search?q=…` 整頁渲染，兩條路同一個
route（`partial=`）。`hx-push-url` 讓兩者是同一個網址，結果可以貼給別人。

### 服務層

`TaskService` 多了 `search`／`count`／`owner_facets`／`priority_facets`，`stats()` 多吃一個
可選的 `tasks`：搜尋頁要的是同樣四個數字，算在自己的那批 match 上。第二個計數器
遲早會跟第一個不同步，那是「Done」在兩頁上意思不一樣的開始。

facet 的 badge variant 來自 `PRIORITY_VARIANT`，與 task row 讀同一張表，所以
「High」在 facet 裡與在列上不可能是兩個顏色。

`test_search.py` 17 條。`test_parity.py` 沒有動：新路由不在 probe 清單裡，側欄多一個
連結只多一個 href，而 href 只檢查「有沒有少」。

---

## `dist/` 曾經落後 apidocs 兩天（2026-08-22）

`test_every_class_in_the_console_s_templates_exists_in_the_stylesheet` 是紅的，
點名八個 class：`cursor-pointer`、`pt-3`、`w-full`、`gap-x-5`、`gap-y-1`、
`min-w-0`、`shrink-0`、`w-18`。它們都在 API 主控台那一輪（`45ca443`、8/21）加的模板裡，
而本機 `packages/fjkit/src/fjkit/static/dist/` 是 8/19 建的——主控台那幾處的樣式
在本機是掉的。

**不是版控問題。** `dist/` 在 `.gitignore` 裡，`fjkit.css` 的 `@source` 一直
正確指著 `../../apidocs/templates`（同一支測試的第一段就在守這件事），
`docs/assets/dist/fjkit-vega.css`（有進版控的那份）也早就含這八個 class。
原因是本機沒重跑 `fjkit build-css`。重建後 620 條全綠。

### 重建後的體積（八個包）

| 包 | raw | gzip |
|---|---|---|
| vega（預設） | 234,817 | 24,622（24.0 KB）|
| nova | 239,443 | 24,716（24.1 KB）|
| maia | 233,912 | 24,656（24.1 KB）|
| lyra | 235,027 | 24,319（23.7 KB）|
| mira | 235,548 | 24,638（24.1 KB）|
| luma | 237,538 | 24,882（24.3 KB）|
| sera | 220,998 | 24,218（23.7 KB）|
| rhea | 237,818 | 24,887（24.3 KB）|

最大 **24.3 KB gzip**（上限 28），比 8/19 那次量的 24.1 KB 多 0.2 KB——主控台整批
模板的 utility 就值這麼多，跟上面「棘輪已經扣完」的推論一致。

### 順手發現：`?v=` 用的是 mtime，所以 `docs/` 永遠會被判定為 stale

跑 `docs/workbench/build.py` 之後八頁 HTML 全部有 diff，但**內容一個字都沒變**，
變的只有 cache-busting 的 `?v=`：

```
-<script defer src="assets/vendor/htmx/htmx.min.js?v=1787294618">
+<script defer src="assets/vendor/htmx/htmx.min.js?v=1786876367">
```

數字是本機檔案的 mtime。mtime 不進 git，clone 出來是 checkout 的時間，所以
**任何兩台機器建出來的 `docs/` 都不會一樣**：`.githooks/pre-push` 在每一台新機器上
擋一次，然後被 commit 一批純噪音的 diff，下一台再擋一次。

這次沒有 commit 那批 diff（我沒有動到文件站的來源）。修法是把 `?v=` 改成
內容雜湊或版本號，但那是文件站建置的一筆改動，不在這次的範圍，記在這裡。

---

## 雙擊防護，以及文件站補上兩課（2026-08-22，使用者指定）

### `hx-disabled-elt`：demo 每一個會改資料的控制項

一次 swap 是一趟來回，而這中間**沒有任何東西擋得住第二次點擊**。板子上的 Advance
連點兩下就推進兩次，新增表單連按兩下就送兩筆。修法是一個屬性：

```jinja
{{ button("Advance", hx_post=…, hx_target="#board", hx_disabled_elt="this") }}
{% call form(action=…, target="#board", hx_disabled_elt="find button[type=submit]") %}
```

補上的地方：板子的新增表單／Advance／Delete、jobs 的 Start 與 Clear finished、
session 的登入與登出。GET（篩選、搜尋）刻意不加：它們沒有副作用，擋住只會讓頁面變鈍。

**沒有動 `form()` 的簽名。** `attrs()` 那條 kwargs 透傳的路就是為這件事存在的
（`ui/attrs.html` 的註解寫著「adding a new one never requires touching fjkit」）。把
「送出時自動 disable」變成 `form()` 的預設行為，是改一個已發佈 macro 的行為，那要先問。

選擇器寫 `find button[type=submit]` 而不是 `[type='submit']`：CSS 屬性選擇器的值可以是
識別字，不加引號就不會在 HTML attribute 裡變成 `&#39;`。

實測（瀏覽器裡量的，不是照文件抄的）：

```
before: disabled=false marker=false
beforeSend: disabled=true  marker=true      ← data-disabled-by-htmx
afterRequest: disabled=false marker=false
```

`test_htmx.py` 多兩條：板子上每一個帶 `hx-post`／`hx-delete` 的控制項都必須有
`hx-disabled-elt`；每一張用 `find button[type=submit]` 的表單裡都要有一顆 submit。
第二條的理由是選擇器沒中時 htmx 只在 console 警告，表單照樣連點得下去。

**`test_parity.py` 擋了一次，這是它該做的事。** `hx_attrs` 是 EXACT 欄位，八個板子相關的
probe 全部紅了。處理方式照第 0 節那條規則：寫進 `ALLOWED_CONTRACT_DRIFT`，並說明理由。
八個共用一個具名常數 `BOARD_HX_ATTRS`，因為它們渲染的是同一支 partial，這是一筆刻意的
改動，不是八筆。`hx_targets`／`hx_urls` 仍然對著原始 baseline 比，所以這條例外不會變成
「可以隨便改接線」的許可。

### 文件站：Learn 從九課變十一課

前面兩輪做完 oob 與 indicator，但站上一個字都沒有：`hx-swap-oob` 只在第 05 課的
「Server-side helpers」清單裡有一行。補上兩課（英文與中文各一份，共用同一支 `learn.js`）：

| 課 | 標題 | 內容 |
|---|---|---|
| 06 | 一次回應，換掉好幾塊：hx-swap-oob | 主通道 vs 頻外、htmx 的三步驟處理順序、回應長什麼樣、page 與 `_results` 差一個變數、四個陷阱 |
| 07 | 請求進行中的那段時間 | htmx 注入的那段 CSS（逐字）、兩個選擇器各管什麼、`hx-disabled-elt`、計數而非開關、不要放在 target 裡面 |

06～09 因此往後推成 08～11，`sections` 清單、鋼印編號、`t0x` 變數名與導言的「九課」一起改。

兩件寫的時候才發現的事：

1. **`code_block()` 的 source 要傳普通字串，不能傳 `{% set %}…{% endset %}`。** 後者產出
   Markup，`<div>` 會被當成真的標記渲染出去。Jinja 的字串字面值可以跨行、裡面可以放 `{%`，
   所以直接寫多行字串。
2. **`fjkit check` 抓到了寫在註解裡的反例。** `search/_detail.html` 有一段註解引用了
   `<p class="text-muted-foreground text-sm">` 當作「不要這樣寫」的示範，檢查器照樣判違規：
   它讀的是 attribute，不管在不在註解裡。那是檢查器在正常運作，所以改寫了註解。

---

## 0.3 Pydantic 整合 + 錯誤呈現層（提案 → 施工中）

路線圖 0.3 原本只寫「`ValidationError` → 欄位錯誤對映、422 時重繪 partial、
`HX-Retarget`／`HX-Reswap` 輔助、輸入值保留」。研究之後範圍擴大了一圈，理由在下面
第三節：**驗證錯誤要統一處理，就必須先有一個「把訊息送到使用者眼前」的核心能力，而那個
能力現在不存在。** 存在的是 `FlashPlugin`，但它解的是另一個問題（撐過 redirect）。

### 一、開工前實測到的六件事

| | 實測結果 |
|---|---|
| 現況 L1（簽名層） | `POST /tasks title=""` → 422 JSON。`RequestValidationError` 在 handler body 之前丟出，**body 沒跑到** |
| 現況 L2（模型層） | `POST /tasks title="x"*200` → **500**。handler 裡的 `TaskCreate(...)` 丟 pydantic `ValidationError`，沒人接 |
| htmx 不 swap 4xx | vendored htmx 2.0.10 預設 `responseHandling` 是 `[{204,false},{"[23]..",true},{"[45]..",false,error}]`。**「422 時重繪 partial」在預設設定下做不到**，`HX-Retarget`／`HX-Reswap` 也救不了——那兩個只改 target，不決定要不要 swap |
| `HX-Trigger` 不受狀態碼限制 | htmx 的 `Vn()` 在 `htmx:beforeOnLoad` 之後**第一件事**就是讀 `HX-Trigger`，`responseHandling` 的比對在那之後。**所以 500 的 toast 送得到，不必動 `responseHandling`** |
| 例外處理器拿得到的東西 | `await request.form()` 回傳**已解析且被 cache 的**表單值（輸入值保留免費）；`request.scope["route"].endpoint` 就是 `@render` 的 wrapper（plan 查得到）；`exc.errors()` 一次給齊 `loc`／`msg`／`input` |
| toaster 已經是 core | `ui/shell.html` 無條件 `{% call toaster() %}`，註解自己寫著「always having it is what lets a toast appear on a page that did not know in advance that one was coming」。`{% if flash is defined %}` 是防禦性寫法，沒裝 plugin 也不會爆 |

**順手挖到的既有缺陷**：`form(reset_on_success=true)` 發的是無條件的
`hx-on::after-request="this.reset()"`，而 `htmx:afterRequest` 成功失敗都觸發。名字寫
on success，行為不是。所以現在送出空標題，使用者看不到錯誤，**打的字還會被清掉**。

### 二、pydantic 不再是禁區（2026-08-23 裁決）

`test_rendering.py` 那兩條依賴守門測試原本把 `pydantic` 擋在 `fjkit/charts/` 以外。
裁決是**移除這條限制**：`fastapi` 對 `pydantic>=2.9.0` 是無條件依賴（`requires()` 第二條，
不帶 extra 標記），`import fjkit` 跑完 `sys.modules` 裡就已經有 `pydantic` 與
`pydantic_core`，安裝成本與 import 成本都確認為零。§12 那個等裁決的 charts 項目一併結案。

守門測試改成 `declared` 含 `pydantic`，`fjkit/charts/` 的路徑豁免與
`test_the_charts_exemption_covers_pydantic_and_nothing_else` 隨之退休。

### 三、為什麼範圍擴大：三層，不是兩層

驗證錯誤要統一處理，就要回答「錯誤以什麼形式出現在使用者面前」。答案按請求種類分岔，
而這是 HTTP 的事實，不是設計選擇：

| 請求 | 錯誤該長什麼樣 | 機制 |
|---|---|---|
| htmx swap | 頁面留著、冒一個 toast | `HX-Trigger` |
| 一般導覽 | 錯誤頁 | 直接渲染模板。沒有「當下的頁面」可以 toast |
| POST 後 redirect | 訊息要活過 redirect | flash cookie |

`flash.py` 自己的 docstring 寫得清楚：flash 存在是因為 **`HX-Trigger` 撐不過 redirect**。
反過來也成立——**不 redirect 的回應用 flash 是錯的工具**，那是為一個現在就要畫出來的訊息
寫一個 cookie。所以要搬進 core 的不是 flash，是它底下那一層：

| 層 | 內容 | 要 secret？ | 原本 | 現在 |
|---|---|---|---|---|
| **1 呈現** | `toaster()` 區域 + `toast()` macro | 否 | 已經是 core | 不動 |
| **2 送達「這一個回應」** | `messages.add(request, …)`；htmx 走 `HX-Trigger`，整頁渲染直接進 context | 否 | **不存在** | **`fjkit/messages.py`，core** |
| **3 活過一次 redirect** | 簽章 cookie | **是** | `FlashPlugin` | **維持 plugin，改成疊在第 2 層上** |

第 3 層留在 plugin 的理由很具體：**它需要 `secret`**。搬進 core 等於每個 app 都要給一把
金鑰，包括沒有表單、沒有訊息的 app。`mount_fjkit(app)` 現在零設定就能跑，那件事會結束。

### 四、驗證錯誤分兩層落地

| 層 | 設定 | 顯示 |
|---|---|---|
| **Tier 0** | 零。裝了 fjkit 就有 | toast（htmx）或錯誤頁（一般導覽），狀態碼 422 |
| **Tier 1** | `@render(..., invalid="tasks/_new_form.html")` | 紅字回到欄位下面、輸入值保留、`HX-Retarget` 到表單本身 |

Tier 0 就是「統一處理」：**每一條路由立刻有合理行為，handler 一行都不用改**。
Tier 1 在想要更好的 UX 時逐條升級。兩層共用同一個 `field_errors()`，不是兩套機制。

**選方案三（全域 exception handler）而不是方案二（`FromForm[Model]` 依賴注入），是刻意的**：
要求是不改變任何原始的 FastAPI 寫法。`Annotated[str, Form()]`、`ServiceDep`、回傳模型
全部照舊，設定只加在 fjkit 自己的 `@render` 上。代價寫在第六節。

### 五、`HX-Retarget` 因此有了真實用途

Tier 1 的 `invalid=` 只渲染得出表單本身（handler 沒跑，board 要的 `tasks`／`stats`／
`owners` 不存在），而 demo 的表單原本 target 是 `#board`，所以**必須**把 swap 改指到表單
自己。路線圖那兩個 header 在方案二裡是順便出貨的孤兒，在這裡是必要條件，而且 demo 會走過。

### 六、三個誠實的限制

1. **`invalid=` 的模板只拿得到 `errors`、`values`、context processors，加上
   `invalid_context` 明說要給的。** handler 沒跑過。想重繪整塊 board 就得寫
   `invalid_context`，而那份程式碼會跟 GET handler 重疊。`@render` 用 `functools.wraps`，
   所以 `__wrapped__` 讓重疊變成重用，不是複製。
2. **錯誤重繪的邊界是「表單」，不是「表單所在的區塊」。**
3. **「零改動」嚴格說是「FastAPI 那一半零改動」。** fjkit 自己的裝飾器多了兩個參數。

### 七、兩個要付的代價

- **每頁預設多約 120 bytes 的 JS。** basecoat 的 toaster 是元素方法
  （`#toaster.toast({...})`），不是 document 事件監聽，所以 `HX-Trigger` 要變成 toast，
  shell 裡需要一段監聽器。§7 那條寫「每頁預設僅 htmx + basecoat，不新增」，這是那條上限
  第二次被真的測試（第一次是 A11 的 charts）。替代方案是 OOB swap，但那要讓 5xx 也可 swap，
  副作用大得多，不採用。
- **全站 `Exception` handler 會改變除錯手感。** 開發時要看 traceback，不是一個寫著「出了點
  問題」的 toast。掛在 `FjkitConfig` 的 dev/prod 開關上，並確認測試的
  `raise_server_exceptions` 沒被吃掉。

### 八、施工清單

- [x] **一**：`fjkit/messages.py`（第 2 層 core）+ `FlashPlugin` 改成疊在上面 + shell 的
      toaster 改讀 `fjkit_messages()` + 那段監聽器（`28b18b1`）
- [x] **二**：`fjkit/forms.py`（`field_errors`）+ `fjkit/errors.py`（Tier 0，全部路由零設定）
      + shell 的 `<meta name="htmx-config">` 讓 422 可 swap（`df04d22`）
- [x] **三**：`@render(invalid=, invalid_context=)` + `fjkit/htmx.py`（`HX-*` 輔助）
      + demo 兩張表單各證一半（`e36c27c`）
- [x] **四**：全站 500 handler，共用第 2 層的送達機制（`df04d22`，`catch_unexpected_errors`）
- [x] 修 `form(reset_on_success=…)` 的無條件重設
- [x] 依賴守門測試改掉（第二節）
- [x] 測試：`test_messages.py` 19 條、`test_errors.py` 46 條、demo 的 `test_validation.py` 12 條
- [ ] 文件站重建（動到 `ui/shell.html`、`ui/form.html`）
- [ ] CHARTER 第 9 節 0.3 那一列、第 12 節那兩個已結案的項目要更新——**那是你的檔案，我不動**
- [ ] `.claude/skills/fjkit/SKILL.md` 要補「表單錯誤怎麼接」——同上，等你點頭

### 九、施工中定案的三件事

**1. 錯誤訊息文案：純轉手，但欄位名改寫成人看得懂的形式。**
pydantic 的 `msg` 原樣送出（"Field required"）。理由是一份訊息表等於把 i18n 塞進 0.3，
而 fjkit 連 locale 這個概念都還沒有；app 想換字，攔 `FieldErrors` 換掉即可。
補的是**欄位名**：toast 出現在離控制項很遠的地方，"Field required" 單獨一句會讓人
找不到是哪一欄，所以 `FieldErrors.messages()` 前面掛 `label(name)`：`owner_name` →
`Owner name`，`items.0.title` → `Items 1 title`（索引改成一起算）。
**對映的鍵不動**，那是模板查錯誤用的字串。

**2. 巢狀欄位：支援，折成點路徑。**
`("body", "items", 0, "title")` → `items.0.title`。那正是 HTML 表單會用的 `name=`，
所以模板用同一個字串就查得到。折成葉節點會讓兩個不同欄位共用一則訊息。

**3. `loc` 的前綴不用猜，用參數。**
FastAPI 的 `loc` 前面有 `body`／`query`／`path`，handler 自己建的模型沒有。
`field_errors(exc, request_scoped=…)` 由呼叫端說清楚——嗅探開頭是不是 `"body"` 會
一路正確到有人宣告一個叫 `body` 的欄位，然後靜靜地把那個欄位的錯誤丟掉。

### 十、寫完才發現的兩個 bug（測試抓到的）

兩個都是「程式碼跟自己的 docstring 不一致」，也都是先寫測試才浮出來的：

1. **handler 自己丟的 `ValidationError` 沒有被守住。** `_on_model_error` 的 docstring
   寫著「只對宣告了 `invalid=` 的路由生效」，但沒有一行程式在檢查。結果是 service 深處
   `Task(**row)` 失敗會變成一則 422，講一個使用者根本沒填過的欄位：
   **一個偽裝成驗證訊息的 bug，藏在開發者最不會去看的地方**。檢查現在放在「決定要不要
   接手」的那個 handler 裡；沒有 `invalid=` 就照舊往上丟。
2. **`submitted_values` 說「重複欄位留第一個」，實際留最後一個。** Starlette 的
   `FormData.items()` 早就把重複的收斂成最後一個了，要 `multi_items()` 才看得到全部。

### 十一、瀏覽器實測抓到的兩個 bug（測試抓不到的那種）

跑完全部測試、全綠之後，把 demo 開起來用 Chrome 實際點一遍，抓到兩個。
**兩個都是打開頁面就看得見，而整套測試完全沉默的那種。**

1. **toast 是空的。** htmx 對 `HX-Trigger` 的值有分支：JSON **物件**原樣變成
   `event.detail`，其他東西（陣列也算）會被包成 `{value: …}`。送出去的是裸陣列，所以
   shell 的監聽器什麼都沒迭代到，basecoat 畫出一個空的、category 是預設 info 的 toast。
   改成 `{"fjkit:toast": {"messages": [...]}}`：與其讓 shell 依賴 vendored 檔案裡的
   一個分支，不如送一個形狀本來就對的東西。
2. **每一張剛畫出來的表單，輸入框裡都寫著 `None`。** `values.title` 對沒填過的欄位回
   `None`，而 `value=` 原樣塞進屬性。現在 `FieldErrors` 與 `Values` 對「不存在的名字」
   回不同的東西，那個差別就是兩者的語意：**沒有錯誤的欄位沒有話要說**（`None`，macro
   把 `<p>` 省掉）；**沒填東西的欄位有值，那個值是空的**（`""`）。

同時實測確認的四件事：`htmx.config.responseHandling` 讀到了 `422:true`（零 JS）、
被退回的送出會把欄位框紅並保留輸入而下面的板子完全沒動、沒有 `invalid=` 的路由會冒一個
`role="alert"` 的 toast 而且訊息是真的、純 POST 的編輯頁回的是整份文件而且 notes 還在。

**這一節值得留著的理由**：0.3 有 62 條 kit 測試 + 12 條 demo 測試，全綠，而這兩個 bug
一個都沒被擋下。測試守的是伺服器送出去什麼；這兩個壞在瀏覽器拿到之後。

---

## poc_app 回報的三個缺口（2026-09-01）

三件都是另一個 app（ClinicalRetriever 的 poc_app）在用 fjkit 蓋頁面時撞到、
自己繞過去、然後把繞法連同位置一起報回來的。三件的共同點是**繞法都能通過
`fjkit check`**：手抄一份 `.field` 包裝用的是合法的 component class，裸 `<p>`
沒有顏色字面值，所以檢查器對它們全部沉默。這是第 7 節那句「有 CSS 不等於有元件」
的另一個版本：**能通過檢查不等於沒有缺口**。

### 一、`.dialog > * > section` 的捲軸壓在內容上

`static/src/fjkit.css` 那條 `overflow-y-auto` 是我們自己加的（2026-08-18，見上面的
體積表），理由寫在它自己的註解裡而且沒有錯：不加，長面板的內容會溢出視窗，滑鼠還能捲
到、鍵盤到不了。少的是跟著它一起來的槽。

這個 `section` 自己沒有 padding（面板的 24px 在它外面），所以佔版面寬度的傳統捲軸畫在
section 的 padding box 內側，蓋住內容右緣。回報者量到的數字：`offsetWidth 624 /
clientWidth 609`，內容右緣 1222，三張卡片的邊框右緣 1222／1221／1222，捲軸軌道從 1222
開始。**左右不對稱是判準**：左緣有面板的 padding 當槽，右緣沒有。

修法是同一條規則上加一個 `scrollbar-gutter: stable`。選 `stable` 而不是 `pr-*`：它在
捲軸出現與否兩種狀態下都保留軌道，所以內容不會在「長到開始捲」的那一刻橫向跳一次。
macOS 預設的 overlay 捲軸不佔版面寬度，`stable` 在那種環境保留不到東西，而那種環境
本來也沒有東西要清。

**為什麼上游一直沒撞到**：`examples/fjkit-demo` 的 dialog 內容是幾行散文加一個
spinner。要面板裡放得下卡片才看得見，而那不是 app 特有的形狀：任何有邊框或滿版的
子元素都會。

### 一之二、第一版修正不完整：改成 full-bleed padding（同日，使用者截圖回報）

`scrollbar-gutter: stable` 落地當天就被同一個 app 的截圖打回來：Publication 那個
collapsible 聚焦時，右緣仍然被遮。第一版只解了三個症狀裡的一個，而且上面那句
「overlay 捲軸的環境本來也沒有東西要清」**是錯的**：

1. 傳統捲軸的軌道壓在內容邊框上——`stable` 解了這個。
2. macOS overlay 捲軸不佔版面寬度，`stable` 對它保留不到任何東西，捲動時 thumb
   照樣浮在內容右緣上。
3. focus ring 畫在 border box 外側，貼齊捲動容器邊緣的子元素，它的 ring 直接被
   overflow 裁掉——這跟捲軸是哪一種完全無關。

三個症狀同一個成因：**捲動發生在 section 裡，而 section 的邊緣就是內容的邊緣**。
凡是捲動容器畫在自己邊緣的東西（軌道、thumb、裁切線）都落在內容上。

第二版是 shadcn 處理捲動 dialog body 的同款手法：section 用 `-mx-6` 撐到面板
邊緣、自己帶 `px-6`（面板是 `p-6`，兩者剛好抵銷，畫面上什麼都不動），讓捲軸與
裁切線走在 section 自己的 24px padding 帶裡。`stable` 留著，理由只剩一個：
沒有它，傳統捲軸出現的那一刻內容會窄 15px、回流一次。

這次不是用推理收工的。重現頁強制 15px 傳統捲軸實測：`offsetWidth 672 =
clientWidth 657 + 15`，卡片右緣距離軌道 24px，與面板右緣的距離恰為
`(15 + 24) × 0.95`（面板還在 `scale-95`），逐 px 對上；截圖與放大圖確認邊框、
空帶、thumb、面板邊緣四者分離。

### 二、`caption`：沒有辦法寫一行獨立的淡色說明

`card`／`section`／`page_header` 都畫得出說明文字，但那三個的說明都**綁在標題底下**，
是標題區塊的第二行，搬不走。表格下面那行「每五分鐘更新一次」、表單腳註、控制項旁邊的
一句補充——這種獨立的說明沒有出口，而它需要的顏色 `text-muted-foreground` 是 app
模板不准寫的（A2）。回報的那個 app 有 11 處，全部用裸 `<p>`／`<small>` 繞過去。

`caption(text=none)` 進 `ui/data.html`，跟 `link`／`bullet_list` 放一起。它吃參數也吃
區塊，因為「說明裡要放一個 `link()`」是它第二常見的形狀。

### 三、`select_menu`／`combobox` 沒有可見標籤，也接不住 422

`text_field` 那一排欄位每一支都自己畫 `<label for=…>`，指向自己控制的 id。這兩支
scripted 控制項不畫：`label=` 只是 trigger 上的一個 `aria-label`。所以要讓它跟旁邊的
欄位長得一樣，呼叫端只能自己抄一份 `.field` + `.label`——那個 app 抄了，6 個呼叫點、
3 個模板。

**回報裡有一段推論是錯的，值得寫下來**：報告說被退回的欄位「沒有 `<p>` 可寫，所以會變成
一則對開發者說話的 toast」。實際讀 `js/errors.js` 不是這樣：它用 `[name]` 找控制項，
而這兩支的 hidden input 有 `name`，所以找得到；找不到 `aria-describedby` 時它會**自己
建一個 `<p>` 插在控制項後面**。問題在於那個「後面」：hidden input 是 `.select` 包裝
div 的最後一個子元素，所以紅字被畫進 select 框裡面。同時 `aria-invalid` 落在一個
hidden input 上，而收尾的 `first.focus()` 對 hidden input 是空操作。

**所以修法不能只是一個包裝 macro。** 一個外面的 `labelled_field(label)` 畫得出 `<p>`，
但 `errors.js` 讀的是控制項自己的 `aria-describedby`，包裝 macro 碰不到 hidden input，
結果會是兩個 `<p>`，id 還撞在一起。要把洞補起來，只能由**擁有 id 的那支 macro**動手。

落地成 `select_menu` 與 `combobox` 各多三個具名參數，三個之中任何一個有值就從裸控制項
變成一個完整的 field：

- `visible_label` —— `.field` 包裝加一個真的 `<label for>`（`select_menu` 指向 trigger
  按鈕，`combobox` 指向新加的 `{id}-input`）。給了它就不再送 `aria-label`：兩個名字並存
  時螢幕閱讀器唸屬性、不唸畫面上的字，等於用錯的那個蓋掉對的那個。
- `hint`／`error` —— 與其他欄位同一套語意，`error` 取代 `hint` 而不是疊上去。

外加兩件不在報告裡、但不做就補不完的事：

1. **訊息段落一定畫，沒話說的時候是空的加 `hidden`。** 這樣 `errors.js` 有一個位置正確
   的目標可以重用，不會自己建一個插到 select 框裡。
2. **`aria-describedby` 同時放在 trigger 和 hidden input 上。** 放 trigger 是給螢幕閱讀器
   的；放 hidden input 純粹是給 `errors.js` 的——hidden input 根本不在無障礙樹上。

`ui/overlay.html` 因此自己帶了一份 `_message`，沒有去 import `ui/form.html` 的那一份。
理由是 **Jinja 不准 import 底線開頭的名字**，而把那一支改成公開的代價有兩層：一是發佈
一支 app 模板不該呼叫的 helper，二是**會改變 `fjkit eject` 對它的處理**：private helper
會被複製進你自己的檔案，public 的會被再匯出，然後繼續在你腳下移動。`_GAP` 在
`form.html` 與 `layout.html` 各寫一份，是同一個理由。

### 沒做的：`labelled_field`

報告主推的形狀。查完 `errors.js` 之後沒有做，理由是上面第三節那段：它接不住 422，
而接不住 422 之後它剩下的只是一個 `.field` 的 `<div>`，落在第 8 節的拒絕標準
「只是把原生 HTML 元素包一層，沒有補上 a11y、狀態或伺服器互動」。6 個真實呼叫點全部
是 `combobox`／`select_menu`，`visible_label` 之後它們都不需要包裝 macro。

哪天出現一個 fjkit 不擁有的控制項要配標籤，再回來看這一節。那時要補的仍然是
「讓那支控制項自己畫」，不是一個蓋在外面的盒子。

---

## poc_app 回報的另外兩個缺口（2026-09-02）

同一個 app 的續報。前一輪（2026-09-01）之後它採用了 `caption()` 與 `visible_label`，
刪掉手抄的 `.field` 包裝，30 份模板裡已經一個 `class=` 都沒有；剩下的兩處都在登入頁，
而且都已經在該處註明是缺口而不是設計決定。

**兩件都不是 `fjkit check` 擋下來的，而是它看不見的。** 一個是 inline `style`，
一個是 app 自己寫的 `<script>`；檢查器讀 class 屬性，這兩樣都不在它的視野裡。
這是上一輪那句「能通過檢查不等於沒有缺口」的第二個版本，而且更難察覺：上一輪的繞法
至少是合法的 component class，這一輪的兩個繞法是檢查器不看的東西。

**兩者在 `examples/fjkit-demo` 裡都沒有被走過**，這是它們一直沒浮出來的原因。
demo 的 `auth/page.html` 是一般的 in-shell 頁面，`_panel.html` 的密碼欄位是
`text_field(type="password")`、預填了 demo 密碼、沒有任何顯示切換。

### 一、`ui/layout.html` 給不了寬度上限

回報處是一行 inline style，也是該 app 全部模板裡唯一的一行：

```jinja
{% call stack(6, align="center") %}
  <div style="width: min(24rem, 100%)">…</div>
{% endcall %}
```

查證過了，缺口是真的：`stack(align="center")` 會置中但不會封頂，`grid` 是把拿到的寬度
分掉，`split` 那兩個數字是 aside 的 grid track。`grep -n "max-w\|w-\[" ui/layout.html`
是空的。所以呼叫端只有兩個選擇：`max-w-sm`（`fjkit check` 會擋，而且擋得對）或
inline style（檢查器看不到）。

落地為 `centered(width="sm", gap=6)`。width 是封閉列舉——`xs`／`sm`／`md`／`lg`／`xl`／
`prose`——理由跟這個檔案裡每一張查表一樣：Tailwind 靠掃描原始碼找 class，`max-w-{{ width }}`
會指到一個樣式表裡不存在的名字，欄位會以全寬渲染，而且沒有任何東西會說它出錯。

**它不做垂直置中。** 回報者描述的形狀（滿版、無 header、無 nav、一欄置中）是兩件事，
只有寬度那一半是 macro 的事。另一半是把 shell 的 `header` 與 `footer_wrapper` 兩個 block
留空，該 app 已經這樣做。合成一支會讓這支 macro 多一個在常見情況下什麼都不做的參數。

**kit 自己就有一個用得上的地方**：`errors/page.html`。它是 kit 唯一出貨的 standalone
頁面，原本用 `stack(6)`，所以一段道歉文字加一顆按鈕會跟著 shell 的 1152px 拉開。
改成 `centered("lg", gap=6)`。demo 的 `test_a_navigation_gets_a_page` 順帶守住這一條。

### 二、沒有密碼顯示切換，所以 app 得自己寫 JavaScript

`input_group_field` 的 `end` slot 是對的接縫，該 app 也是這樣用的；它必須自己補的是行為，
9 行 `<script>`，是該 app 除了 fjkit 自己的主題切換以外唯一的一段腳本。

**這一項會出貨 kit 自己寫的第二支 JavaScript，屬於第 11 節第 3 條，需要人類裁決。
2026-09-02 由你裁決要做。**

判準不是「app 要寫 9 行」，而是那 9 行為什麼難寫對。兩個限制都不是該 app 的性質，
是**任何會把自己換掉的 fjkit 表單**的性質：

1. **監聽器必須從 `document` 委派。** 被拒絕的登入會把整個面板換掉，綁在按鈕上的監聽器
   跟著舊節點一起消失。在 DOMContentLoaded 綁一次的頁面，得到的是一個只能用一次的
   切換，而且失敗時沒有 console 錯誤，按鈕看起來還是按鈕。
2. **要從 `aria-controls` 讀 input 的 id，不能靠慣例。** id 由 macro 決定（`f-<name>`，
   或被 `id=` 蓋掉）。這支腳本不知道有 `f-` 這個前綴。

狀態也一律從 DOM 讀（`input.type`），不快取：swap 之後 markup 才是權威，記住的布林值
描述的是已經不在頁面上的那個元素。

落地為 `input_group_field(revealable=true, reveal_show="Show", reveal_hide="Hide")` 加
`reveal_scripts()`，`static/js/reveal.js` 共 51 行（含註解）。兩個標籤是參數不是常數，
腳本從元素上讀它們，所以它自己不持有任何一個英文字串。

**它放在 `input_group_field` 而不是 `text_field`**：顯示切換必須坐在 input 的框裡面，
而 `.input-group` 是 kit 裡唯一有位置放它的 markup；一個 `.input` 後面接一顆按鈕是兩個框。

`reveal_scripts()` 逐頁載入，不進 shell，跟 `form_scripts()`／`multiselect_scripts()`
同一條規則：第 7 節管的是「每一頁預設下載什麼」，答案必須維持「htmx 加 basecoat」。

### CSS 體積

| 項目 | raw | gzip |
|---|---|---|
| `centered` 的六條 `max-w-*` | +249〜+291（八個包） | +49〜+63 |
| `revealable` | 0 | 0 |

量法是把 `ui/layout.html` 與 `ui/form.html` 退回 HEAD 重建一次、再放回來重建一次，
因為 `static/dist/` 不進版控，工作目錄裡那一份未必是 HEAD 建出來的。
`revealable` 是 0，因為它用的 `btn`／`data-variant`／`data-size` 早就在裡面。
八個包現在 24.1–24.8 KB gzip，上限 28 KB。

### demo 這次走過了

- `auth/_panel.html` 的密碼欄位改成 `input_group_field(revealable=true)`，
  `auth/page.html` 載入 `reveal_scripts()`。demo 密碼是預填的，所以 Show 就是
  「看清楚你正要送出什麼」。而且**故意用錯密碼送一次**，回來的面板上那顆按鈕一樣能用，
  那正是委派監聽器存在的理由，`test_the_reveal_survives_a_rejected_sign_in` 守著它。
- `centered` 有兩個走法。kit 自己的 `errors/page.html` 是一個，demo 經由 failures 頁的
  整頁導覽到達。demo 自己那個是 `tasks/edit.html`，這個 app 裡唯一「一整頁只有一張表單」
  的頁面，原本四組 fieldset 的短控制項被拉到 shell 的 1152px。改成 `centered("xl", gap=0)`。
  `gap=0` 是因為 `page_header` 自己帶下邊距，這也是這個 app 其他每一頁都把它擺在內容旁邊
  而不是塞進 stack 裡的原因。**寬度上限屬於頁面，不屬於 partial**：htmx 換掉表單時不該
  再帶一份，`test_the_form_page_caps_its_own_measure` 兩邊都斷言。

### 沒做的：standalone 頁面骨架

回報者說這個形狀「與其說是 layout macro，不如說是 page skeleton」。只做了寬度那一半。
另一半（滿版、無 header、無 nav）現在就能用 shell 的 block 做到，該 app 也已經做到。
在只有一個真實呼叫點的時候多發一支 shell 變體，會多出一份要跟 `ui/shell.html` 同步的
`<head>`。第二個頁面需要同一個形狀時再回來看這一節。

---

## 0.4 資料表：可排序表頭、分頁、批次選取（2026-09-04）

路線圖 0.4 那一格的三項全部落地，`ui/table.html` 從 79 行變成 372 行。
`examples/fjkit-demo` 多一個 **Records** 功能，那是這一版的驗收頁；
`packages/fjkit-admin` 還不存在，它是下一輪的事（`goal/admin-investigation.md` §6 Phase 1）。

### 一、三個 macro，一條共同的分工線

| 新東西 | 形狀 |
|---|---|
| 可排序表頭 | 欄位規格多兩個鍵：`sort`（`asc`／`desc`／none）與 `sort_url` |
| 分頁 | `pagination(page, pages, url, param, total, per_page, target, swap, push_url, window, label)` |
| 批次選取 | 欄位規格的 `select: true`（表頭）＋ `select_cell`（資料列）＋ `select_count`（讀數）＋ `select_scripts` |

**三者都不自己組網址。** `sort_url` 與 `pagination(url=…)` 都由路由給，理由是同一條：
query string 歸路由管，因為只有它知道現在開著哪些篩選、哪個參數帶排序、
點已排序的那一欄是要反轉而不是重新套用。macro 猜出來的答案在「一頁上有兩個篩選」
時就是錯的。這條線在 demo 裡是 `features/records/schemas.py` 的 `columns()` 與
`page_url()` 兩個純函式，測試直接讀它們。

**三者都先是連結，才是 swap。** 每個表頭與每個頁碼都渲染真的 `href`，
`target=` 才疊上 `hx-get`／`hx-target`／`hx-swap`／`hx-push-url`。
排序與頁碼是一張清單裡最常被收進書籤、最常被貼給同事的兩件事，
所以關掉 JavaScript 之後它們必須還在。`test_records.py` 兩邊都斷言
每個 `hx-get` 旁邊的 `href` 帶著同一個網址。

### 二、`aria-sort` 與箭頭由同一個值決定

`_ARIA_SORT` 與 `_SORT_ICON` 兩張表都用 `sort` 當鍵。這支元件最常見的壞法是
**箭頭朝上而 `aria-sort` 說 descending**——review 看不出來，畫面上是錯的。
`test_the_arrow_and_aria_sort_say_the_same_thing` 對兩個方向各斷言一次。

第三個狀態（可排序、但目前不是排序中的那一欄）不在任何一張表裡，
落到 `aria-sort="none"` 加雙頭 chevron。沒有它，可排序的欄位跟固定的欄位
在有人點下去之前長得一模一樣。

### 三、`pagination` 在 `pages <= 1` 時不渲染

跟 `table` 自己擁有空狀態同一個理由：只有一頁時那條「1」加兩個灰掉的箭頭
什麼都沒說，而不這樣做的話每個呼叫端都要自己寫一次 `{% if pages > 1 %}`。

走不動的那個箭頭渲染成 `disabled` 的 `<button>`，不是沒有 `href` 的 `<a>`。
**沒有 `href` 的 anchor 完全不進 tab 順序**——箭頭會從鍵盤上消失，
而不是告訴使用者它現在不能用。

首末頁永遠顯示，中間跳號用省略號，所以九頁與九千頁的長度一樣。
`test_the_strip_is_a_fixed_width_however_many_pages_there_are` 對 9,000 頁斷言
只出現 7 個頁碼連結。

### 四、`role="checkbox"` 是寫給 Basecoat 看的

原生 `<input type="checkbox">` 的隱含 role 本來就是 checkbox，寫出來是多餘的——
但 Basecoat 的 table 規則選在它上面：`[&:has([role=checkbox])]:pe-0`，
用來把只放一個核取方塊那一欄的尾端內距拿掉。同一份 CSS 裡的
`tr { data-[state=selected]:bg-muted }` 則是選到的列上色的來源，兩者都是
上游已經預留給批次選取欄的位置，不是我們發明的約定。

### 五、`js/select.js`——第四支自己寫的 JS，逐頁載入（§11 第 3 條，已取得裁決）

2,252 bytes gzip，由 `select_scripts()` 逐頁載入，**不進 shell**，
所以 §7「每頁預設載入」那條一個位元組都沒動。形狀跟 `reveal.js`／`multiselect.js`
完全一樣：從 `document` 委派、狀態每次都從 DOM 讀、不快取任何東西。

**為什麼非有不可**：表頭那顆核取方塊要顯示的第三個狀態是 `indeterminate`，
那是一個**只有 DOM property、沒有對應 HTML 屬性**的狀態——伺服器渲染不出來。
markup 能說的都讓 macro 說了，剩下的才在這裡。

**選取是用 name 當鍵，不是用 table。** name 就是這些方塊送出去的欄位名，
它本來就決定了哪些值會落進同一個請求；共用一個 name 的兩張表對伺服器來說是同一份選取，
在這裡也就是同一份。要兩份獨立選取就給兩個 name，反正本來也得這樣。

**兩個字串都寫在標記裡**（`data-fjkit-select-label`／`-zero`），
所以這支 JS 裡一個英文字都沒有，翻譯頁面能翻譯它們。

**swap 之後不做任何對帳**：新 markup 就是答案。`htmx:load` 掃一遍即可，
而那件事本身也證明了不需要對帳——瀏覽器實測裡，排序 swap 之後讀數自動回到
「None selected」、`indeterminate` 回到 false，因為那是一份全新的、沒有勾選的表格。

### 六、demo 的驗收頁是新開的，不是改 Tasks

Records 是一個新功能（`features/records/`＋`templates/records/`＋`test_records.py` 36 條），
137 列、每頁 12 列、12 頁。**不改 Tasks 板是刻意的**：
`test_parity.py` 對每個 board 探針比對 `hx_attrs`／`ids`／`row_count` 的完整清單，
在既有頁面上加三個功能等於要動 `BOARD_HX_ATTRS` 與 baseline，
而那份 baseline 守的正是「新功能不得讓語意內容倒退」。新路由沒有探針，一條都不用改。

服務層三個決定，每一個都是「壞掉的時候看起來是對的」那一類：

- **排序的 key 帶 `-id` 破平手。** 兩列 owner 相同時若在兩次請求之間互換位置，
  分頁就會靜靜地漏掉一列、重複另一列。
  `test_no_row_is_lost_or_repeated_across_the_pages` 走完 12 頁比對 137 個名字。
- **頁碼在服務層夾住，並且回傳夾過的值。** `?page=900` 是過期書籤，不值得一個 404，
  而用空表格回答它既沒給資料也沒給解釋。
- **未知的 `o=` 退回預設順序，不是 422。** 同樣的理由：那是別人存的網址。

批次動作用 `hx-include="[data-fjkit-select]"` 收選取。htmx 跟表單一樣會略過
沒勾的核取方塊，所以沒有任何地方維護一份清單、也沒有隱藏欄位。

### 七、CSS 體積

量法照 `centered` 那次：把 `ui/table.html` 退回 HEAD 重建一次、再放回來重建一次。

| 項目 | raw | gzip |
|---|---|---|
| 0.4 的 `ui/table.html`（八個包一致） | +166 | +46〜+52 |

八個包現在 24.2–24.8 KB gzip，上限 28 KB。增量這麼小是因為新表頭與分頁條
只用到 `btn`／`data-variant`／`data-size` 與十來個早就在裡面的 utility，
真正新出現的只有 `-mx-2`、`px-1`、`justify-end` 這幾個。

`js/select.js` 5,353 bytes raw／2,252 gzip，**不計入每頁預算**，理由見第五節。

### 八、渲染回歸

`bench/render_bench.py` 第 1 節（50 列的頁面）：1,448.5 → 1,449.5 µs，
落在雜訊裡。新的 `_header` 是**每欄一次**，不是每列一次，熱迴圈沒被碰到。
冷啟動（無 bytecode cache）220.9 → 234.9 ms，`table.html` 變成四倍長之後
多的幾毫秒；暖 cache 15.5 → 16.0 ms。

> 順帶一提：**BACKLOG 曾經提過的 data-driven table**（`table(columns, rows, fields)`
> 由 macro 自己跑迴圈，用來回收元件化的熱迴圈成本）**這一版沒做**。
> 使用者指定的是那三項，而 data-driven 是另一個題目——它會改變 `table` 的呼叫形狀，
> 該有自己的一輪與自己的量測。

### 九、文件站

Components 的 Table 那一課從單一控制項變成兩個分頁（`table`／`pagination`）。
`table` 的狀態選單多兩個值（sortable、batch select），`pagination` 有五個位置
（首頁、中間、末頁、只有三頁、不給計數）——**五個狀態而不是兩個數字旋鈕**，
因為這條分頁條要被檢查的是它在哪裡省略，而那只在特定頁碼上看得到。
中英兩頁的散文都補了，cheatsheet 多四列（`select_cell`／`select_count`／
`select_scripts`／`pagination`），`test_docs_site.py` 那兩條守門測試在補之前是紅的。

### 十、瀏覽器實測（測試看不到的那一半）

`select.js` 沒有任何測試會跑它。實測走過：表頭勾選整欄（12 列全中、
讀數變「12 selected」、列上色）→ 取消一列（`indeterminate` 為 true、
`checked` 為 false、讀數 11、該列取消上色）→ 點 Owner 表頭排序
（URL push 成 `?o=owner`、列重排、選取隨新 markup 歸零）→ 勾兩列按 Archive
（兩列變 Archived、排序與頁碼都留著、toast 顯示「Archived 2 of 2」）→
點第 12 頁（5 列、「133–137 of 137」、Next 灰掉）→ 瀏覽器上一頁（回到第 1 頁且排序還在）。
深淺兩色模式都看過，鍵盤 tab 到表頭連結時 focus 環清楚可見
（`outline: oklch(0.52 0.19 275) solid 2px`，offset −2px）。Console 全程沒有錯誤。

### 十一、補：每頁筆數控制項與列序號（2026-09-04，使用者指定）

**`page_size(url, per_page, options, param, keep, target, …)`**，同樣在 `ui/table.html`。

**它是一個 `<form method="get">`，而那就是整個設計。** 單獨一個 `<select>`
在值變更時沒有任何辦法做出反應——瀏覽器沒有給它那個能力——所以這個選擇必須以
「有人送出的一個請求」的形式抵達伺服器，而 form 就是負責送的那個元素。
兩條路徑送出同一個請求：

```
target="#records"  ->  hx-get，由 select 自己的 change 觸發
沒有 target        ->  一個普通的 GET，加一顆送出鈕
```

兩邊都產生 `GET /records?o=-updated&per_page=25`，因為 htmx 序列化一張表單的方式
跟瀏覽器一樣。**沒有寫任何 JavaScript**（§11 第 3 條因此不適用）。

`hx-trigger="change"` 是第一條路徑會動的原因：form 的預設 trigger 是它自己的 submit
事件，而那條路上根本沒有人送出它；select 的 change 會冒泡到 form。

**送出鈕在 htmx 那條路上包在 `<noscript>` 裡。** 開著腳本時它不渲染，select 自己就會作用；
關掉腳本時它是唯一能作用的東西，而那時 htmx 也沒在跑、不會被它干擾。
這是 `<noscript>` 剛好說出真正意思的少數場合。

**`url` 不能帶 query string。** 原生的 GET 送出會用表單自己的欄位**取代整段 query**，
所以放在 `action=` 裡的東西在那條路上會被安靜地丟掉——htmx 那條會留著，兩條路徑
於是對「現在開著哪個篩選」講出不同答案。要活下來的東西一律放 `keep`，
以 hidden 欄位傳遞，兩條路徑都會序列化它。

**頁碼不在那些東西裡面。** 每頁 12 筆的第 12 頁，換成 50 筆之後是第 3 頁：
那個數字在變更之後指的是別的東西，而唯一一定存在的頁是第一頁。
所以 `keep` 收篩選與排序，永遠不收 `page`。

**`per_page` 傳的是伺服器實際用的值，不是 query string 要求的值。**
一個在 12 列的頁面上顯示 500 的控制項，正在對它唯一存在的目的說謊。

#### demo 端：一個 view 設定散在所有連結上

真正的工作不在那支 macro，在 `_query()`：**只出現在部分連結上的 view 設定，
在有人用了其他那些連結的那一刻就會消失。** 所以每個表頭連結、每個頁碼連結、
批次動作的 URL，全部都帶 `per_page`。排序不得重設每頁筆數，翻頁也不得。
`test_the_size_survives_a_sort` 與 `test_the_size_survives_paging` 走遍所有連結逐一斷言，
因為這種壞法是靜悄悄的：排序之後表格回到 12 列，沒有任何地方說為什麼。

`PAGE_SIZES` 是白名單，也是上限。`?per_page=100000` 是一個 query 就把整張表渲染出來，
而書籤不該有能力要求那件事。

**控制項放在 `pagination` 外面**：`pagination` 在只有一頁時不渲染，而放進去的話，
「產生一頁的那個尺寸」就會變成唯一一個進得去、出不來的設定。
`test_the_control_is_reachable_at_every_size` 守著。

#### 列序號：**沒有新增任何 macro**

`{"label": "#", "width": "narrow", "align": "end"}` 加
`cell(number, tone="muted", numeric=true, align="end")`——四個都是既有參數。
`row_actions()` 存在是因為「靠右、緊湊的一格」在當時沒有辦法用參數表達；
這裡有，所以照 §8 的拒絕標準（「只是把原生元素包一層，沒有補上任何東西」）不做。
**一支再發明一次「淡色靠右數字」的 macro 只會是一個比 `cell` 更差的 `cell`。**

真正需要寫下來的是算式：序號是 `offset + loop.index`，不是 `loop.index`。
`loop.index` 每一頁都從 1 開始，十二頁就會全部編成 1 到 12——**而那在任何單獨一頁上
都看不出有什麼不對**。`offset` 由路由算（`(page - 1) * size`），跟著實際用的尺寸走。
`test_every_row_is_numbered_exactly_once_across_the_whole_table` 走完 12 頁比對 1..137。

序號編的是**清單的順序**，不是紀錄的 id：按 owner 排序會把每一列重新編號。
`test_the_number_is_the_position_not_the_id` 斷言第一列的號碼是 1 而它的 id 不是。

#### 體積與驗證

**CSS 零增量，byte-identical**：`flex items-center gap-2` 與 `select`／`label`／`btn`
早就都在裡面（八個包都跟加這支 macro 之前一個位元組不差）。

瀏覽器實測走過：選 50 → 50 列、「1–50 of 137」、URL push 成 `?o=name&per_page=50`、
**排序還在**（hidden 欄位生效）；第 3 頁改成 25 → 回到第 1 頁（頁碼正確地沒有跟著走）；
所有表頭連結與所有頁碼連結都帶 `per_page=25`；`<noscript>` 的按鈕在開著腳本時不可見。
第 3 頁的序號是 25–36，與摘要一致。深淺兩色模式都看過，console 沒有錯誤。
