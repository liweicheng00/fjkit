# fjkit 架構

五張圖，對應五個不再變動的架構決定。顏色慣例：**fjkit 提供** / **你提供**。

---

## 一 · 套件邊界

app 與 fjkit 只在四個地方接觸，其餘封在套件裡。

```mermaid
flowchart LR
  subgraph you["你的 app"]
    R["features/*/router.py<br/><small>路由、Depends、選模板</small>"]
    P["templates/&lt;f&gt;/page.html<br/><small>只呼叫 macro</small>"]
    T["templates/&lt;f&gt;/_*.html<br/><small>htmx 片段</small>"]
    B["static/brand.css<br/><small>只有 --primary 那幾行</small>"]
  end

  subgraph kit["fjkit"]
    K1["fjkit.Templates<br/><small>Environment · page() · stream()</small>"]
    K2["ui/shell.html<br/><small>head、主題、資產連結</small>"]
    K3["ui/layout · button · form · data · table · icon<br/><small>封閉詞彙表</small>"]
    K4["static/dist/fjkit-&lt;pack&gt;.css<br/><small>八個風格包，發佈時 build 好</small>"]
    K5["static/vendor/{htmx,basecoat}<br/><small>mount_fjkit() 掛載</small>"]
    K6["fjkit check · pytest<br/><small>慣例強制執行</small>"]
  end

  R -->|import| K1
  P -->|extends| K2
  T -->|"{% from %}"| K3
  B -->|覆寫 token| K4
```

四條路徑都是單向的：app 依賴 fjkit，fjkit 不反向引用 app。`brand.css` 是唯一的設定
介面，內容是純 CSS 變數，不經過任何建置。

**不再需要**：`pytailwindcss`、`build_css.py --watch`、`vendor_ui.py`、「改 class 就重 build」。

---

## 二 · 模板解析與 eject

`ChoiceLoader` 把 app 的模板目錄排在套件前面，所以同一行 `{% from %}` 在 eject 前後
解析到不同檔案，呼叫端不必改。

```mermaid
flowchart LR
  Q["{% from &quot;ui/button.html&quot; %}"] --> C{ChoiceLoader}
  C -.->|① 找不到| A1["app/templates/ui/button.html"]
  C ==>|② 命中| K1["fjkit/templates/ui/button.html"]

  Q2["{% from &quot;ui/button.html&quot; %}"] --> C2{ChoiceLoader}
  C2 ==>|① 命中| A2["app/templates/ui/button.html<br/><small>eject 之後</small>"]
  C2 -.->|未到達| K2["fjkit/templates/ui/button.html"]
```

遮蔽是功能，不是意外。代價是 eject 出去的檔案不再跟隨版本升級，所以文件不主推它。
測試：`packages/fjkit/tests/test_vocabulary.py::TestLoaderOverride`。

---

## 三 · 建置時機

管線相同，執行的人與時機不同。差別是右邊少掉的那個 `--watch` 迴圈。

```mermaid
flowchart TB
  subgraph before["現在 — 每個 app 自己 build"]
    direction TB
    BT["你的 template"] --> BC["Tailwind CLI<br/><small>你要裝、你要跑</small>"]
    BB["basecoat 原始碼"] --> BC
    BC --> BO["dist/app.css"] --> BL["&lt;link&gt;"]
    BC -.->|"--watch 得一直開著"| BC
  end

  subgraph after["fjkit — build 發生在發佈時"]
    direction TB
    AT["fjkit 的 template"] --> AC["Tailwind CLI<br/><small>在 fjkit CI，一次</small>"]
    AB["basecoat 原始碼"] --> AC
    AC --> AO["fjkit.css<br/><small>隨套件出貨</small>"] --> AL["&lt;link&gt; ×2"]
    ABR["你的 brand.css"] --> AL
  end
```

實測見 `docs/BACKLOG.md`：225 KB raw / 23.2 KB gzip，其中 217 KB 是 Basecoat 自己的
元件層，與 fjkit 寫了幾個 macro 無關。

---

## 四 · 渲染路徑：一份 partial，兩個入口

完整頁面與 htmx swap 走不同的路，落在同一個模板節點上。

```mermaid
flowchart LR
  S["ui/shell.html"] -.->|extends| P["tasks/page.html"]
  G["GET /tasks"] --> RP["tasks_page()"] --> P
  P -->|include| BD["tasks/_board.html<br/><b>唯一定義</b>"]
  BD --> H["完整 HTML"]

  PO["POST /tasks<br/><small>hx-post</small>"] --> RC["create_task()"]
  RC -->|同一份 partial，直接回傳| BD
  BD --> F["片段 → swap 進 #board"]
```

`_board.html` 有兩條進、兩條出。完整頁面與 htmx 換上去的內容因此渲染自同一份原始碼，
兩者不會漂移。

---

## 五 · 詞彙表守門迴圈

封閉詞彙表要成立，違反就必須被擋下。每一次被擋下，都指出詞彙表缺了什麼。

```mermaid
flowchart LR
  W["寫 page.html"] --> C{"fjkit check"}
  C -->|通過| S["出貨"]
  C -->|"擋下：不在詞彙表<br/><small>例如 grid-cols-7</small>"| M["= 下一個要做的元件"]
  M -->|補進詞彙表| C
```

這條回饋邊是 fjkit 唯一的擴張機制：以示範 app 當測試案例，被擋下的每一個 class 都是
一個還沒做的元件。

實測（0.1 完成時）：

| 目標 | 結果 |
|---|---|
| 舊 `app/templates`（fjkit 之前） | 258 violations |
| `examples/fjkit-demo/app/templates`（fjkit 重寫） | 0 violations |

白名單從 Basecoat 的元件 CSS 自動推導，不是手維護的，所以不會與實際出貨的內容脫節。
它也擋「目前碰巧存在的 utility」：app 若因為 shell 剛好吐出 `gap-4` 就拿來用，哪天
shell 不吐了就會無聲壞掉。
