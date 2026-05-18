# n8n + Google Sheet Log Setup

這份文件是 Informative AI RSS pipeline 的 n8n 排程與 Sheet log 規格。目標是讓每個 W* workflow 都同時保留可分析的數字欄位，以及人類可讀的 `log_summary`。

## Log Contract

所有排程 endpoint 的 response 都會包含：

```json
{
  "log_summary_version": 1,
  "log_summary": [
    "[ok] W7 整合 152 個 signal 到 47 條 thread",
    "[warn] 2 個 signal 疑似掛錯 thread，建議打開 viewer 檢查 mismatch flag"
  ]
}
```

n8n 寫入 Google Sheet 時，把 `log_summary` 用 `\n` join 成單一 cell。數字欄位仍然照寫，未來做趨勢分析會用到。

標準 Sheet 欄位：

| column | meaning |
| --- | --- |
| `logged_at` | n8n 寫入時間 |
| `workflow` | W2 / W4 / W5_verify / W5_judge / W6 / W7 / W8 / W9 |
| `run_bucket` | 本次 idempotency bucket |
| `status` | success / skipped_duplicate / failed |
| `duration_ms` | endpoint 回傳耗時 |
| `input_tokens` | 該 workflow 的主要 LLM input tokens，沒有則 0 |
| `output_tokens` | 該 workflow 的主要 LLM output tokens，沒有則 0 |
| `cost_usd` | 該 workflow 的主要成本，沒有則 0 |
| `primary_count_1` | workflow 主要 count，例如 new_item_count / judged_signal_count |
| `primary_count_2` | workflow 次要 count，例如 failed_source_count / retry_count |
| `workflow_run_id` | Firestore `workflow_runs` id；W2/W5_verify 可留空 |
| `log_summary` | `response.log_summary.join("\n")` |
| `error_message` | HTTP 或 workflow error |

## run_bucket Rules

- W4：`UTC_30_MIN_FLOOR`，例如 `2026_05_16T0030Z`
- W5 / W6：`UTC_HOUR_FLOOR`，例如 `2026_05_16T0000Z`
- W7 / W8 / W9：依 `BRIEFING_TIMEZONE` 的 `DAILY_YYYY_MM_DD`，例如 `DAILY_2026_05_16`
- W9 `run-daily` 內部會自動拆成 `<run_bucket>_script`、`<run_bucket>_audio`、`<run_bucket>_package`

同一個 `run_bucket` retry 時，昂貴 workflow 會回 `skipped_duplicate=true`，並在 `log_summary` 第一行顯示 `[skip]`。

## Workflow Schedule

| W | schedule | endpoint | sheet | payload |
| --- | --- | --- | --- | --- |
| W2 RSS Ingest | 每 30 分鐘 | `POST /sources/rss/ingest` | `Ingest_Log` | `{ "since_hours": 2, "max_workers": 10, "timeout_seconds": 25 }` （`since_hours` 是防漏設定；實際 dedupe 早就擋掉重複，2 小時足夠覆蓋 30 分鐘排程的延遲；用 24 會多 12× 不必要的 Firestore reads） |
| W4 Signal Process | W2 後 5-10 分鐘 | `POST /signals/process-new-items` | `Signal_Process_Log` | `{ "since_hours": 24, "limit_items": 50, "max_workers": 5, "article_extraction": "selective", "canonicalize": "selective", "embed": true, "match": true, "run_bucket": "UTC_30_MIN_FLOOR" }`（2026-05-18 穩定期設定；`250` 只作手動補 backlog） |
| W5 Verify | 每小時 :25 | `POST /signals/verify` | `Verify_Log` | `{ "since_hours": 24, "force": false }` |
| W5 Judge | 每小時 :30 | `POST /signals/judge` | `Judgement_Log` | `{ "since_hours": 4, "max_workers": 5, "force": false, "max_signals_per_run": 200, "quality_gate": "supported_or_promoted", "run_bucket": "UTC_HOUR_FLOOR" }` |
| W6 Business Impact | 每小時 :45 | `POST /signals/business-impact` | `Impact_Log` | `{ "since_hours": 24, "min_score": 60, "max_workers": 5, "force": false, "max_signals_per_run": 100, "run_bucket": "UTC_HOUR_FLOOR" }` |
| W7 Daily Consolidation | 每日 06:45 | `POST /signals/consolidate-daily` | `Consolidate_Log` | `{ "since_hours": 36, "story_lookback_days": 30, "max_threads": 200, "run_bucket": "DAILY_YYYY_MM_DD" }` |
| W8 Daily Briefing | 每日 07:00 | `POST /briefings/generate` | `Briefing_Log` | `{ "score_threshold": 60, "max_sections": 10, "max_signals_input": 80, "write_google_doc": true, "run_bucket": "DAILY_YYYY_MM_DD" }` |
| W9 Daily Podcast | 每日 07:30 | `POST /podcasts/run-daily` | `Podcast_Log` | `{ "write_google_doc": true, "force_audio": false, "force_package": false, "run_bucket": "DAILY_YYYY_MM_DD" }` |

## Model Routing / A-B Test

模型選擇現在有兩種不用 redeploy 的控制方式：

1. **全域 runtime config**：`PATCH /admin/model-routing` 寫入 Firestore `runtime_config/model_routing`，約 60 秒 cache 後生效。Zeabur 請設定 `MODEL_ROUTING_RUNTIME_ENABLED=true`；本機若要測 Firestore runtime read 也設同一個 env。
2. **單次 workflow override**：在 W4/W5/W6/W7/W8/W9 payload 裡帶 `model_overrides`，只影響該次 run，優先序最高。

優先序固定是：

```text
request.model_overrides
→ Firestore runtime_config/model_routing
→ Zeabur env variables
→ app/core/config.py default
```

可用 route key：

| route key | workflow | providers |
| --- | --- | --- |
| `w4_canonicalization` | W4 legacy canonical helper | gemini |
| `w4_match_adjudication` | W4 item → signal 模糊區判斷 | gemini |
| `w5_judgement` | W5 importance score | gemini / openai |
| `w6_business_impact` | W6 business impact | gemini / openai |
| `w7_thread_refine` | W7 Pro thread memory refine | gemini |
| `w7_phase_assignment` | W7 phase assignment | gemini |
| `w8_briefing` | W8 daily briefing | gemini / openai |
| `w9_podcast_script` | W9 podcast script | gemini / openai |

全域改模型：

```http
PATCH /admin/model-routing
X-Admin-Token: <ADMIN_TOKEN>
Content-Type: application/json

{
  "note": "W8/W9 A-B test baseline",
  "routes": {
    "w8_briefing": {
      "provider": "gemini",
      "model": "gemini-2.5-pro"
    },
    "w9_podcast_script": {
      "provider": "openai",
      "model": "gpt-5",
      "reasoning_effort": "medium"
    }
  }
}
```

查目前實際生效模型：

```http
GET /admin/model-routing
X-Admin-Token: <ADMIN_TOKEN>
```

若 `runtime_config.enabled=false`，代表 backend 沒有啟用 Firestore runtime read/write；先在 Zeabur 設 `MODEL_ROUTING_RUNTIME_ENABLED=true` 再重啟 service。

單次 A/B test payload 範例：

```json
{
  "score_threshold": 60,
  "max_sections": 10,
  "max_signals_input": 80,
  "write_google_doc": false,
  "run_bucket": "DAILY_2026_05_16_w8_openai_B",
  "model_overrides": {
    "w8_briefing": {
      "provider": "openai",
      "model": "gpt-5",
      "reasoning_effort": "medium"
    }
  }
}
```

A/B test 請使用不同 `run_bucket`，例如：

- A：`DAILY_2026_05_16_w8_gemini_A`
- B：`DAILY_2026_05_16_w8_openai_B`

原因：`workflow_run_id` 仍由 `workflow + run_bucket` 決定；同一個 bucket 會被 idempotency guard 視為 duplicate，昂貴步驟不會重跑。

每個支援 override 的 workflow response 會多一個 `model_routing` 欄位，n8n 可以把它存進 raw JSON 或另開欄位記錄：

```json
{
  "model_routing": {
    "w8_briefing": {
      "provider": "openai",
      "model": "gpt-5",
      "reasoning_effort": "medium",
      "source": "request"
    }
  }
}
```

## Per-W Sheet Column Mapping

對每個 W*，n8n 取以下值塞進對應 Sheet 欄位。**每行都要照這張表設**——亂填會讓未來 cross-W dashboard 變垃圾資料。

| W | duration_ms | input_tokens | output_tokens | cost_usd | primary_count_1 | primary_count_2 |
| --- | --- | --- | --- | --- | --- | --- |
| W2 RSS Ingest | `response.duration_ms` | 0 | 0 | 0 | `response.new_item_count` | `response.failed_source_count` |
| W4 Signal Process | `response.duration_ms` | `response.adjudication_input_tokens` | `response.adjudication_output_tokens` | `response.total_cost_usd` | `response.signals_written_count` | `response.adjudication_failed_count` |
| W5 Verify | `response.duration_ms` | 0 | 0 | 0 | `response.verified_signal_count` | `response.skipped_already_verified_count` |
| W5 Judge | `response.duration_ms` | `response.total_input_tokens` | `response.total_output_tokens` | `response.total_cost_usd` | `response.judged_signal_count` | `response.failed_signal_count` |
| W6 Business Impact | `response.duration_ms` | `response.total_input_tokens` | `response.total_output_tokens` | `response.total_cost_usd` | `response.analyzed_signal_count` | `response.failed_signal_count` |
| W7 Daily Consolidation | `response.duration_ms` | `response.phase_llm_input_tokens` | `response.phase_llm_output_tokens` | `response.phase_llm_cost_usd` | `response.phases_upserted` | `response.thread_mismatch_flagged_count` |
| W8 Daily Briefing | `response.duration_ms` | `response.input_tokens` | `response.output_tokens` | `response.cost_usd` | `response.selected_signal_count` | `response.briefing_retry_count` |
| W9 Daily Podcast | `response.run.duration_ms` | `response.script.input_tokens` | `response.script.output_tokens` | `response.run.cost_usd` | `response.script.word_count` | `response.script.script_retry_count` |

備註：

- `cost_usd` 為 0 的 row 表示該 W 不直接呼叫 LLM（只用 embedding 或純 Firestore）
- W4 之前 `cost_usd` 只報 embedding 成本（漏 Pro adjudication）；2026-05-16 修復後 `total_cost_usd` 才完整。請務必用 `total_cost_usd` 而不是 `embedding_cost_usd`
- W7 / W9 等 multi-stage workflow 的 token 欄只取「主要 LLM stage」的 tokens；TTS / embedding / refine 等次要支出體現在數字欄但不在 token 欄

W4 `Signal_Process_Log` 額外建議欄位（2026-05-18 穩定觀察用）：

| column | value |
| --- | --- |
| `candidate_item_count` | `response.candidate_item_count` |
| `processed_item_count` | `response.processed_item_count` |
| `embedded_item_count` | `response.embedded_item_count` |
| `article_extracted_count` | `response.article_extracted_count` |
| `thin_dropped_count` | `response.thin_dropped_count` |
| `adjudication_call_count` | `response.adjudication_call_count` |

`fin` 不是 API 欄位；若 Sheet 已有此欄，可用 `Y` 表示 `success` / `skipped_duplicate`，`N` 表示 `failed`。新表可直接省略 `fin`，以 `status` 為準。

## W4 n8n Implementation Notes

W4 v2 必須呼叫：

```text
POST https://informative-ai.zeabur.app/signals/process-new-items
```

不要再打舊端點 `/signals/cluster`。舊端點是 legacy shadow clustering，會讓 payload / log mapping 對不上。

建議 flow：

```text
Schedule Trigger
→ Build W4 Payload
→ HTTP Request
→ IF
   ├─ true  → Normalize W4 Success → Append row in sheet
   └─ false → Normalize W4 Error   → Append row in sheet
```

HTTP Request 設定：

```text
Method: POST
URL: https://informative-ai.zeabur.app/signals/process-new-items
Authentication: Generic Credential Type / Header Auth
Header: X-Admin-Token
Send Body: on
Body Content Type: JSON
Specify Body: Using JSON
JSON: {{ JSON.stringify($json.body) }}
Settings → Continue On Fail: true
Timeout: 900000 ms
```

正式排程用的 `Build W4 Payload`：

```javascript
const now = new Date();
const minute = Math.floor(now.getUTCMinutes() / 30) * 30;
now.setUTCMinutes(minute, 0, 0);

const yyyy = now.getUTCFullYear();
const mm = String(now.getUTCMonth() + 1).padStart(2, "0");
const dd = String(now.getUTCDate()).padStart(2, "0");
const hh = String(now.getUTCHours()).padStart(2, "0");
const mi = String(now.getUTCMinutes()).padStart(2, "0");

const run_bucket = `${yyyy}_${mm}_${dd}T${hh}${mi}Z`;

return [{
  json: {
    run_bucket,
    body: {
      since_hours: 24,
      limit_items: 50,
      max_workers: 5,
      article_extraction: "selective",
      canonicalize: "selective",
      embed: true,
      match: true,
      run_bucket
    }
  }
}];
```

手動測試若要避開 duplicate guard，可暫時用 manual bucket：

```javascript
const now = new Date();
const run_bucket = `manual_w4_selective_50_${now.toISOString().replace(/[-:.]/g, "").slice(0, 15)}Z`;
```

測完要改回 UTC 30 分鐘 bucket；正式排程不要每次都用 `Date.now()`，否則 n8n retry 會重跑昂貴步驟。

IF node 建議條件：

```text
value1: {{ $json.log_summary_version }}
operator: is equal to
value2: {{ 1 }}
```

成功 path normalize：

```javascript
const r = items[0].json;
const logged_at = new Date().toISOString().replace(/\.\d+Z$/, "Z");
const timestamp_brisbane = new Date().toLocaleString("sv-SE", {
  timeZone: "Australia/Brisbane",
  hour12: false,
});
const skipped = r.skipped_duplicate === true;

return [{ json: {
  logged_at,
  timestamp_brisbane,
  workflow: "W4",
  run_bucket: r.run_bucket || "",
  status: skipped ? "skipped_duplicate" : "success",
  duration_ms: r.duration_ms || 0,
  input_tokens: r.adjudication_input_tokens || 0,
  output_tokens: r.adjudication_output_tokens || 0,
  cost_usd: r.total_cost_usd || 0,
  primary_count_1: r.signals_written_count || 0,
  primary_count_2: r.adjudication_failed_count || 0,
  candidate_item_count: r.candidate_item_count || 0,
  processed_item_count: r.processed_item_count || 0,
  embedded_item_count: r.embedded_item_count || 0,
  article_extracted_count: r.article_extracted_count || 0,
  thin_dropped_count: r.thin_dropped_count || 0,
  adjudication_call_count: r.adjudication_call_count || 0,
  workflow_run_id: r.workflow_run_id || "",
  log_summary: (r.log_summary || []).join("\n"),
  error_message: "",
}}];
```

Error path normalize：

```javascript
const err = items[0].json;
const status = err.error?.httpCode || err.statusCode || err.error?.response?.status || err.error?.status || 500;

let body = err.error?.body || err.error?.response?.data || err.body || {};
if (typeof body === "string") {
  try { body = JSON.parse(body); } catch (_) {}
}

const detail = body.detail || body.message || err.error?.message || err.message || "unknown error";
const logged_at = new Date().toISOString().replace(/\.\d+Z$/, "Z");
const timestamp_brisbane = new Date().toLocaleString("sv-SE", {
  timeZone: "Australia/Brisbane",
  hour12: false,
});
const run_bucket = $("Build W4 Payload").first().json.run_bucket || "";

return [{ json: {
  logged_at,
  timestamp_brisbane,
  workflow: "W4",
  run_bucket,
  status: "failed",
  duration_ms: 0,
  input_tokens: 0,
  output_tokens: 0,
  cost_usd: 0,
  primary_count_1: 0,
  primary_count_2: 0,
  candidate_item_count: 0,
  processed_item_count: 0,
  embedded_item_count: 0,
  article_extracted_count: 0,
  thin_dropped_count: 0,
  adjudication_call_count: 0,
  workflow_run_id: "",
  log_summary: `[warn] HTTP ${status}: ${String(detail).slice(0, 300)}`,
  error_message: `HTTP ${status}: ${String(detail).slice(0, 500)}`,
}}];
```

2026-05-18 production validation:

- `limit_items=50`, `article_extraction=off` processed 50/50, wrote 19 signals, `thin_dropped_count=25`, cost `$0.001488`, duration `199s`.
- `limit_items=50`, `article_extraction=selective` processed 22/22, extracted 11 articles, wrote 12 signals, `thin_dropped_count=6`, cost `$0.007473`, duration `166s`.
- Selective mode is the intended W4 optimization and should stay on. Observe W4 for 24h before moving W5/W6 forward.
- `limit_items=250` is for manual backlog catch-up only after W4 has run cleanly for 24h and Firestore vector index exemptions are in place.

## Failure / Error Branch

**只有 W9 `run-daily` 在 raise 之前會把 `failure_summary`（含 `log_summary`）寫進 `workflow_runs` 文件**（[rss_podcast_run_service.py](app/services/rss_podcast_run_service.py)）。其他 6 個 service 在 exception path 直接 raise，n8n 收到 HTTP 5xx、response body 通常不含 `log_summary`。

n8n error branch 推薦處理：

```javascript
// n8n Function node — normalize error payload
const status = items[0].json.status_code || items[0].error?.httpCode || 500;
const body = items[0].json.error?.body || items[0].json.body || {};
const message = body.detail || items[0].json.error?.message || "unknown error";
const log_summary = (body.log_summary || []).join("\n")
                    || `[warn] HTTP ${status}: ${message}`;
return [{ json: {
  status: "failed",
  error_message: `HTTP ${status}: ${String(message).slice(0, 500)}`,
  log_summary,
  duration_ms: 0,
  // 其他數字欄都填 0（避免 Sheet expression undefined）
}}];
```

要對其他 6 個 service 也拿到結構化 failure summary，可選擇：

1. **被動方式**（不改 backend）：n8n 在 error branch 後追加一個 Firestore Read node，查 `workflow_runs/<run_id>` 取 `summary.log_summary`。需要 W4/W5/W6/W7/W8 也走 `start_workflow_run`（W7/W8/W9 已經是；W4/W5_judge/W6 也已經是；只有 W2/W5_verify 沒包，這兩個失敗本來就罕見）。
2. **主動方式**（改 backend）：把 W9 run-daily 的 failure summary 模式複製到其他 service。中等工作量，留下一輪。

> 建議先採方式 1。production 跑 1 週若發現 W4/W5/W6 有結構化失敗摘要的需求再做方式 2。

## How To Read `log_summary`

- `[ok]`：正常完成或健康狀態。
- `[new]`：新 signal / 新 thread / 新 phase / 新稿件等值得注意的新東西。
- `[repeat]`：重複、cache、略過或 background repeat。
- `[warn]`：需要人工抽查的警示，例如 mismatch、retry、LLM output 品質偏弱。
- `[cost]`：token / LLM / TTS 成本。
- `[time]`：duration 或慢來源。
- `[skip]`：同一個 `run_bucket` 已完成或正在執行，這次沒有重跑昂貴步驟。

排查優先順序建議：

1. 先看 `[warn]`：mismatch、retry、失敗數是否異常。
2. 再看 `[new]`：今天有沒有新故事軸、podcast 是否有新內容。
3. 最後看 `[cost]` / `[time]`：token、費用、耗時是否比平常高。

## n8n Node Pattern

每個 workflow 建議使用同一個形狀：

1. Cron node 產生 schedule。
2. Function node 產生 `run_bucket`。
3. HTTP Request node 呼叫 endpoint。
4. Function node normalize response：
   - `status = response.skipped_duplicate ? "skipped_duplicate" : "success"`
   - `log_summary = (response.log_summary || []).join("\n")`
   - `input_tokens / output_tokens / cost_usd` 依 workflow 對應欄位取值。
5. Google Sheets append row。
6. Error branch 寫入同一張表，`status=failed`，`error_message` 填 HTTP error。

W9 `run-daily` 的 Sheet row 取值：

- `duration_ms = response.run.duration_ms`
- `cost_usd = response.run.cost_usd`
- `primary_count_1 = response.script.word_count`
- `primary_count_2 = response.script.script_retry_count || 0`
- `workflow_run_id = response.workflow_run_id || ""`

若某欄沒有對應值，填 `0` 或空字串，不要讓 n8n expression 因 undefined 中斷。
