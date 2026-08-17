# Jinja2 的 CPU / memory 評估

每個數字都來自 `bench/render_bench.py`，可以自己重跑：

```bash
uv run python bench/render_bench.py            # 全部
uv run python bench/render_bench.py memory     # 單一段落
uv run python bench/render_bench.py --json     # 給 CI 吃
```

> 測試機：Apple M1 Pro · Python 3.13.0 · Jinja2 3.1.6 · Starlette 1.6.0。
> **絕對數字換一台機器就不一樣，排序不會變。** 下面每一節的結論靠的是排序。

---

## TL;DR

| 做的事 | 效果 | 值不值得 |
|---|---|---|
| bytecode cache 寫進 image | 冷啟動 **102 ms → 4.3 ms**（24×） | ✅ 最大的一筆 |
| 大頁面改 stream | 峰值記憶體 **22 MB → 16 KB**（與頁面大小無關） | ✅ 第二大 |
| stream 一定要 buffering | 同一頁 **1233 ms → 19 ms**（65×） | ✅ 不做就別 stream |
| 重複元件用 macro 不用 include | 省 **20–30%**，差距隨列數線性長 | ✅ 順手 |
| `trim_blocks` / `lstrip_blocks` | 少 3.3% bytes（CPU 不變） | ✅ 一行設定 |
| 重的 handler 別跑在 event loop 上 | 最糟停頓 **140 ms → 1.0 ms** | ✅ 有大頁面就要做 |
| `auto_reload=False` | **量不到**（跑幾次正負號會換邊） | ⚠️ 該關，但別當效能手段 |
| `import ... without context` | **量不到** | ⚠️ 為了正確性而做，不是為了速度 |
| `StrictUndefined` → `Undefined` | **量不到** | ❌ 不要為了效能拿掉 |

一句話：**Jinja 的成本幾乎不在「渲染」，而在「編譯」「峰值記憶體」和「誰在跑它」。**

---

## 1. Environment 設定：多數旋鈕根本不重要

50 列的頁面（含 template inheritance）：

```
get_template + render, auto_reload=True       380.4 us
get_template + render, auto_reload=False      391.7 us   1.03x
  ... template 提到迴圈外                      399.6 us   1.05x
  ... 再把 StrictUndefined 換成 Undefined      371.5 us   0.98x
```

**注意 `auto_reload=False` 這次比 True 還「慢」。** 這不是真的變慢——
是這三個設定的差異小到落在 run-to-run 噪音裡（±3%），連跑幾次正負號會換邊。
這就是結論本身：**這三個旋鈕在暖機後的 process 上量不出來。** 原因：

- `auto_reload` 的成本記在 **`get_template()`**，不是 `render()`——它對繼承鏈上每個檔案做一次 `stat()`。
  在 SSD 上那是幾微秒，被 370 µs 的渲染整個淹掉。
  **該關掉是因為 production 的檔案不會變（改了也不該熱生效），不是因為它慢。**
- `get_template()` 本身只是 `cache_size=400` 的 LRU 查表，沒必要為了它做全域變數。
- `StrictUndefined` 量不出差別。**不要為了效能拿掉它**——它把「變數打錯字」從「安靜輸出空字串」變成錯誤。

真正決定這 370 µs 的是 **要輸出多少節點**。想快，就是輸出少一點（見 §3、§5）。

---

## 2. 冷啟動：唯一數量級的差距

Jinja 把每個 template 編譯成 Python 原始碼再 `compile()`。第一次載入 21 個 template：

```
compile from source      101.8 ms      21 templates
warm bytecode cache        4.3 ms      21 templates   0.04x
```

**24 倍。** 而且這 100 ms 是純 CPU，發生在 process 能服務第一個 request 之前。

長時間跑的 server 看不到它。看得到的是：`--reload` 每次存檔、rolling deploy 的每個新 pod、
autoscaling 起的每個新 replica、serverless 的每次 cold start。

`FjkitConfig` 的 `bytecode_cache_dir` 一設就開 `FileSystemBytecodeCache`。**production 的正解是把 cache 目錄
烤進 image**，讓第一個 request 就吃到熱的：

```dockerfile
RUN uv run python -c "\
from app.config import Settings; from app.templating import build_environment; \
env = build_environment(Settings(template_auto_reload=False)); \
[env.get_template(n) for n in env.list_templates()]"
```

> cache 檔以 template 的 mtime + 內容雜湊為 key，改了 template 會自動失效，不用手動清。

記憶體那邊：21 個 template 編完常駐約 1–2 MB（一個 template ≈ 一個 Python module 的
code object）。`cache_size=400` 的預設值遠大於多數 app 的 template 數，等於「永不淘汰」，
這正是你要的——不必調小。

---

## 3. 重複元件：inline vs macro vs include

同一列 markup，三種寫法，每列 3 個欄位：

```
             inline us      macro us     include us
  10 rows         19.8          38.1           41.8
 100 rows        167.8         319.7          384.4
1000 rows      1,608.6       3,031.4        3,925.6
```

兩個結論，方向相反，都要記住：

**(a) `{% include %}` 放進迴圈裡比 macro 慢 20–30%**，而且差距隨列數線性長。
include 每一圈都要重新解析 template 名稱、走 loader、建一個新的 Context 物件；
macro 只是對一個「已經建好的 module」做函式呼叫。
→ **重複的元件一律 macro。** 這也是 `packages/fjkit/src/fjkit/templates/ui/` 全部是 macro 的原因。

**(b) macro 不是免費的——它比 inline 貴一倍。**
每列多約 1.4 µs（1000 列多 1.4 ms）。這是抽象的價格，多數頁面付得起：
一個 50 列的表格差 70 µs，不值得為它放棄可維護性。

→ **預設用 macro。只有在「單一迴圈跑幾千列」的報表頁，把那一列 inline 回去才是合理的優化**，
而且要留註解說明為什麼這裡跟別的地方不一樣。這份 repo 的 `tasks/report.html` 就是這樣寫的。

---

## 4. `with context`：為了正確性，不是為了速度

```
                              1 row        20 rows
without context (default)     10.5 us      67.0 us
with context                  10.2 us      64.6 us   0.97x
```

跟 §1 一樣：**差異落在噪音裡，重跑正負號會換邊。**

`{% from "x.html" import y %}`（預設 = without context）拿到的是 Jinja 在 Template 物件上
**快取過一次**的 module；加了 `with context` 每次 render 都會重建那個 module，
重跑被 import 檔案裡所有 top-level 語句。

**因為 module 通常很小**，重建一次不到 1 µs，量不出來。真正的理由是設計面的：
`with context` 讓 macro 偷偷讀到呼叫端的變數，參數列就不再是契約了。
`ui/*.html` 的 macro 一律顯式收 `request`，就是為了留在便宜且明確的那一邊。

（但如果哪天某個 macro 檔案的 top-level 長出昂貴的東西——大 dict、`{% set %}` 迴圈——
「量不到」就會變成量得到。`ui/icon.html` 的 icon path 表正是這種東西：
它靠 without context 只建一次，加上 `with context` 就會變成每個 request 重建一次。）

---

## 5. Whitespace：一行設定，3.3% 的 bytes

200 列的頁面：

```
trim_blocks off      68,463 bytes      1,393.6 us
trim_blocks on       66,172 bytes      1,392.4 us   （bytes 0.97x，時間持平）
```

`trim_blocks` + `lstrip_blocks` 讓 template 可以照人類習慣縮排，
而不用把縮排送給瀏覽器。**省的是 bytes，不是 CPU**——渲染時間沒動，
因為要輸出的節點數量一樣，只是每個節點短一點。
（3.3% 的 bytes 過 gzip 之後會再縮水，所以這是「順手做」等級的收益，不是優化手段。）

已經在 `app/templating.py` 開好。**不要**為了再擠幾個 byte 去手寫 `{%-` `-%}`——
那個回報遠小於它對可讀性的破壞。

---

## 6. 記憶體：這才是 Jinja 真正會傷到你的地方

`template.render()` 會把每個片段都做成字串、放進 list、最後 join 成一個大字串。
峰值 ≈ **HTML 大小的 3.6 倍**：

```
                             render()      stream(64)      stream(5)
 1,000 rows (0.3 MiB)      1,123.8 KiB       15.2 KiB       7.2 KiB
20,000 rows (6.1 MiB)     22,354.2 KiB       15.9 KiB       7.9 KiB
```

三件事值得注意：

1. **`render()` 是線性的**：6 MiB 的頁面吃 22 MB。20 個併發請求 = 440 MB，
   而這是「容器被 OOM kill」的典型長相。
2. **stream 是常數的**：頁面多大都是 ~16 KB，因為同時只有一個 buffer 活著。
3. 多數頁面根本不在這個尺度。一般的 HTMX 片段是幾 KB，`render()` 完全正確。

→ **判準不是「大不大」而是「有沒有上限」**：
資料列數由使用者輸入決定（匯出、報表、搜尋結果、`?limit=`）就 stream；
形狀固定的頁面就 `render()`。`app/templating.py` 兩個方法都提供，
`/tasks/report` 是 stream 的例子。

---

## 7. 要 stream 就一定要 buffering

這是最容易踩、也最貴的一個坑。2000 列的頁面：

```
                 chunks       jinja ms     over ASGI ms
no buffering     18,042           15.6          1,232.6
buffer=16         1,128           15.6             96.0
buffer=64           282           15.2             35.0
buffer=512           36           15.1             18.9
```

注意 **`jinja ms` 那一欄完全沒動**。Jinja 不在乎你怎麼消耗它的 generator。
成本全部發生在上面一層：**每一個 yield 出來的片段都會變成一個 ASGI
`http.response.body` message 加一個 HTTP chunked-encoding frame。**
沒 buffering 的話，一頁 = 18042 個 message → **比 buffered 慢 65 倍，而且比直接
`render()` 還慢**。

`app/templating.py` 的 `stream()` 預設 `buffer_size=64`；很大的頁面調到 512。
`TemplateStream.enable_buffering(n)` 的 `n` 是**節點數不是 bytes**，而且必須 > 1。

---

## 8. 誰在跑 render：CPU-bound 的東西放在 event loop 上會凍住整個 process

Jinja 渲染是**同步、純 CPU、不放 GIL** 的 Python。放錯地方，一個慢頁面會拖垮所有頁面。

測法：一個 task 不斷打 `/ping`，同時跑 4 個 4000 列的重渲染。
關鍵指標是**連續兩次 ping 之間最大的間隔**——那就是 event loop 對其他所有人不可用的時間。

```
                                   4 renders ms    pings served    worst stall ms
async def — renders on the loop           139.2             117             139.6
def — Starlette threadpool                131.5             163              23.0
async def + run_in_threadpool             124.7             156              22.9
async def + StreamingResponse             359.8           1,297               1.0
```

逐行讀：

- **`async def` 直接 render**：loop 被鎖 140 ms，剛好是 4 個 render 的總和。
  期間這個 worker **什麼都不能做**——不能收新連線、不能回 health check。
- **改成 `def`（Starlette 丟 threadpool）**：最糟停頓掉到 23 ms，好很多，但**不是零**。
  原因是 GIL：render 是純 Python bytecode，只在 `sys.setswitchinterval()`（預設 5 ms）
  的邊界才換手。**把 CPU-bound 工作丟到 thread 不會給你一個空閒的 loop，
  只會給你 5 ms 粒度的交錯。**
- **`run_in_threadpool`** 跟上一行是同一件事，差別只在寫法。
- **stream**：最糟停頓 **1.0 ms**——因為每個 chunk 之間都會回到 loop。
  代價是總時間 2.6 倍（每個 chunk 一次 threadpool 往返）。

實務規則：

| 情況 | 怎麼寫 |
|---|---|
| HTMX 片段、一般頁面（render < 1 ms） | `async def` 直接 render。threadpool 那一跳（~50–100 µs）比 render 本身還貴 |
| 中等頁面（1–20 ms） | 用 `def`，讓 Starlette 丟 threadpool |
| 大／無上限的頁面 | `stream()`，並且接受吞吐量的代價 |
| 任何情況 | **worker 數才是真正的解**：`--workers N`。多 process 才是 CPython 繞開 GIL 的方法 |

---

## 9. 其他值得知道的

**MarkupSafe 的 C 加速一定要在。** autoescape 會對每個輸出的值跑一次跳脫；
純 Python fallback 慢好幾倍。確認方式：

```bash
uv run python -c "from markupsafe import _speedups; print('ok')"
```

用 uv 裝的 wheel 本來就帶著它。會掉的情境是某些 musl/ARM 的 source build。

**不要在 template 裡整形資料。** `| map | select | zip | list` 這種鏈比等價的 Python 慢，
也更難讀。router 遞給 template 的應該是已經成形的東西——
這份 repo 的 `STATUS_FILTERS` / `PRIORITY_OPTIONS` 是 module 常數就是這個道理。

**`enable_async=True` 不要預設打開。** 它存在的理由是「在 template 裡 await」。
一旦打開，每個 block 都會包上 coroutine，同步渲染反而變慢；
而且 template 本來就不該去抓資料。

**CSS 也算在頁面成本裡。** 這個 stack 的 `packages/fjkit/src/fjkit/static/dist/fjkit-<pack>.css` 是 225 KB
（gzip 23.5 KB / brotli 18.5 KB），涵蓋整套 Basecoat 元件。量測當時只 build 一個風格包；
現在八個都 build，但一頁只載一個，所以頁面成本沒變（各包 23.5–24.1 KB gzip）。
Basecoat 的 skin 是單一檔案，沒辦法按元件 tree-shake；23.5 KB 跟 Bootstrap 同級，
而且是**一次快取、之後每一頁都免費**——比起每頁重送的 markup，這是划算的一邊。

**量測，不要相信直覺。** 這份文件裡有一半的結論跟一般說法相反
（`auto_reload` 沒差、macro 比 inline 慢、threadpool 沒有真的解放 loop）。
`Server-Timing` header 每個 response 都有，devtools 的 Network 面板直接看得到。
