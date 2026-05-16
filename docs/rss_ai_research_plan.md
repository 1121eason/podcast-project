# Signal Brief 系統流程設計 Survey

更新紀錄：2026/05/11 Claude 完整重寫為中文 system survey（為流程設計 review 使用）

本文件是「Signal Brief / Informative AI」系統的**端到端流程 + 邏輯 + 閾值 + 模型**單一來源。所有 review 對話都應該以此文件為基準。

---

## 0. 系統總覽

```
Google Sheet (RSS List)
       │  W1 12h
       ▼
┌─────────────────────────────────────────────────────────┐
│  Firestore: rss_sources (≈262 sources, ≈127 fetchable)  │
└────┬────────────────────────────────────────────────────┘
     │  W2 30m  (ingest, create-only)
     ▼
┌─────────────────────────────────────────────────────────┐
│  Firestore: rss_items  (≈3000–4000 new items / day)     │
└────┬────────────────────────────────────────────────────┘
     │  W4 30m  (+5–10m after W2)
     │  /signals/process-new-items
     │  ─ article extraction (selective)
     │  ─ canonicalization     (selective LLM)
     │  ─ multi-vector embedding (4 vectors per item)
     │  ─ hybrid centroid matching (+ adjudication band)
     ▼
┌─────────────────────────────────────────────────────────┐
│  Firestore: rss_signals  (≈150–250 / day, 增量更新)      │
└────┬────────────────────────────────────────────────────┘
     │  W5 1h:30  /signals/verify  (規則)
     │             /signals/judge   (LLM，quality_gate)
     │  W6 1h:45  /signals/business-impact
     ▼
┌─────────────────────────────────────────────────────────┐
│  Firestore: rss_signals（補上 cluster_status /          │
│  topic_heat / importance_score / impacted_* / …）       │
└────┬────────────────────────────────────────────────────┘
     │  W7 daily  /signals/consolidate-daily
     │  ─ 接 30 天 story threads
     │  ─ 補 today_delta / do_not_repeat / continuation_hint
     ▼
┌─────────────────────────────────────────────────────────┐
│  Firestore: rss_story_threads（≈中長期事件線）           │
└────┬────────────────────────────────────────────────────┘
     │  W8 07:00  /briefings/generate （Layer A 研究稿）
     │  W9 07:30  /podcasts/run-daily
     │   ├─ generate_daily_podcast_script  (Layer B 口語稿)
     │   ├─ synthesize_podcast_audio       (TTS → GCS MP3)
     │   └─ create_publish_package         (上架用 metadata)
     ▼
┌─────────────────────────────────────────────────────────┐
│  Firestore: rss_briefings / rss_podcast_scripts /       │
│             rss_podcast_episodes / rss_publish_packages │
│  GCS:       signal-brief-audio-…/podcasts/<date>/*.mp3   │
└─────────────────────────────────────────────────────────┘
```

### 每日量級與目標成本

| 量級 | 估值 | 來源 |
|---|---|---|
| Fetchable sources | ≈127 | Phase 1 production |
| 新 RSS items / 30 min | 40–80 | Phase 1 production |
| 新 items / day | 3000–4000 | 推估 |
| 新 signals / day | 150–250 | Phase 2 ≈460/run × multi-source 21–24% 推估收斂後 |
| importance ≥ 60 signals / day | 30–60 | Phase 3 acceptance 估計 5–20% |
| importance ≥ 80 signals / day | 5–15 | Phase 3 acceptance 1–8% |
| **目標月費** | **< $30 USD** | Signal Intelligence v2 設計目標 |

> 5/6–5/10 五天累積成本 ≈ NTD 2000 (~$13/天 = $390/月)，遠超目標。已知主因：舊 Phase 2 全量 4h re-cluster + ingest 每次更新 last_seen_at + 缺 quality gate。Signal Intelligence v2 已修；本文件後段「已知設計問題」列出剩餘可疑點。

---

## 1. n8n 排程一覽

| ID | 名稱 | 排程 | Endpoint | 寫入 Sheet | Body 建議 |
|---|---|---|---|---|---|
| W1 | Sheet Sync | 每 12 小時 | `POST /sources/sheets/sync` | Sync_Log | — |
| W2 | RSS Ingest | 每 30 分鐘 | `POST /sources/rss/ingest` | Ingest_Log | `since_hours=2, max_workers=10, timeout_seconds=25`（RSSHub URL 自動限 2 並發） |
| W3 | Daily Report | 每日 08:00 | `GET /sources/rss/signal-report?since_hours=24` | Daily_Report | — |
| W4 | Signal Process (v2) | 每 30 分鐘，W2 +5–10m | `POST /signals/process-new-items` | Signal_Process_Log | `since_hours=6, limit_items=250, max_workers=5, article_extraction=selective, canonicalize=selective, embed=true, match=true, run_bucket=UTC_30_MIN_FLOOR` |
| W5 | Verify + Judge | 每小時 :30 | `POST /signals/verify` 然後 `POST /signals/judge` | Judgement_Log | judge: `since_hours=4, quality_gate=supported_or_promoted, run_bucket=UTC_HOUR_FLOOR` |
| W6 | Business Impact | 每小時 :45 | `POST /signals/business-impact` | Impact_Log | `since_hours=24, min_score=60, max_signals_per_run=100, max_workers=5, run_bucket=UTC_HOUR_FLOOR` |
| W7 | Daily Consolidation | 每日 06:45 | `POST /signals/consolidate-daily` | Consolidate_Log | `since_hours=36, story_lookback_days=30, max_threads=200, run_bucket=DAILY_YYYY_MM_DD` |
| W8 | Daily Briefing | 每日 07:00 | `POST /briefings/generate` | Briefing_Log | `min_score=60, max_sections=10, max_signals_input=80, run_bucket=DAILY_YYYY_MM_DD` |
| W9 | Daily Podcast | 每日 07:30 | `POST /podcasts/run-daily` | Podcast_Log | `write_google_doc=true, run_bucket=DAILY_YYYY_MM_DD`（內部會傳 `_script` / `_audio` / `_package` 子桶） |

舊 `POST /signals/cluster`（Phase 2 全量分群）保留為 shadow，比對穩定後下線。

**所有昂貴 endpoint 都需傳 `run_bucket`**：n8n retry 同一個 bucket 不會重打模型 / TTS（透過 `workflow_runs` Firestore collection 鎖定）。

---

## 2. 階段詳述

每階段都採同一格式：**輸入 → 邏輯 → 閾值 / 數字 → 模型 → 輸出 → 成本 → 已知問題**。

---

### 階段 0：Source Registry（W1 Sheet Sync）

| 項 | 內容 |
|---|---|
| **輸入** | Google Sheet `RSS List` worksheet |
| **邏輯** | 讀 sheet → batch write 到 Firestore `rss_sources`；sheet 內被移除的 source 在 Firestore 標 non-fetchable |
| **閾值 / 數字** | 只有 `狀態 = ✅ OK (200)` 或 `200` 才標 fetchable |
| **模型** | 無（純資料同步） |
| **輸出** | Firestore `rss_sources` |
| **成本** | $0 |
| **已知問題** | 14 個 source 在 Apps Script health check 過關但 ingest 持續失敗（flaky），需手動 prune；silent source（一週零產出）也要 prune |

---

### 階段 1：RSS Ingest（W2，30m）

| 項 | 內容 |
|---|---|
| **輸入** | Firestore `rss_sources` fetchable=true 的 source |
| **邏輯** | `httpx` 並行抓 feed → 解析 → 按 `source_id + guid/url/content_hash` 去重 → **create-only**：已存在的 item 不再更新 `last_seen_at` / `summary` / `published_at`（v2 降本決策，避免每 30 分鐘重寫 Firestore）。**Worker split**：URL 含 `zeabur.app`（RSSHub）走 `DEFAULT_RSSHUB_WORKERS=2` 並發、其他維持 `DEFAULT_MAX_WORKERS=10`，兩個 ThreadPoolExecutor 同時跑。 |
| **閾值 / 數字** | per-feed `DEFAULT_FEED_TIMEOUT_SECONDS=25`（從 10 升上去，因 RSSHub 冷啟動 4-8s）；`DEFAULT_MAX_WORKERS=10`（非 RSSHub）；`DEFAULT_RSSHUB_WORKERS=2`（zeabur 並發上限）；`since_hours=2` 為防漏設定（實際 dedupe 早就擋掉重複） |
| **模型** | 無 |
| **輸出** | Firestore `rss_items`（新 item 寫入；既有 item skip）；`rss_ingest_runs`（run metadata + per-source counts） |
| **成本** | Firestore writes only；30m × 40–80 new ≈ 50–100 writes / run |
| **設計依據** | 244 source × 8 worker 並發、10s timeout 時 audit fail 43 個（36 個是 zeabur ReadTimeout）。改成 timeout=25 + zeabur 限 2 worker 後 fail 降到 11 個（pass rate 72% → 86%）。修法本質是「容器吃不下並發冷啟動」，timeout 拉長治標、限並發治本。 |
| **已知問題** | `.gov` 站（BLS / FTC / CFTC / CISA）並發 8 時 403、單獨打全活——下一步要加 `.gov` 低並發 pool（同 RSSHub 模式）。 |

---

### 階段 2：Item v2 Processing — Article + Canonical + Embedding（W4 內含三步）

#### 2.1 Article Extraction（X1 gate，selective）

| 項 | 內容 |
|---|---|
| **輸入** | 一個 `RssItem` |
| **邏輯** | **`should_extract_article(item)` 收斂成單一規則**：`len(summary) < RSS_SUFFICIENT_CHARS(400)` 才爬。RSS 給的 desc/encoded ≥ 400 字視為自足、跳過 HTTP fetch。命中才 `extract_article_lead(item)` 用 `httpx` + 內建 `HTMLParser` 解析，截到 `ARTICLE_LEAD_CHAR_LIMIT(1600)` 字。Hash 未變一律跳過。**status 分三檔**：`success`（lead ≥ 500 字 = X2 通過）、`thin`（lead < 500 字）、`failed`（HTTP 4xx/5xx/timeout）、`skipped`（X1 不過、不該爬）。 |
| **閾值 / 數字** | `RSS_SUFFICIENT_CHARS=400`（X1，跳過 scrape 門檻）、`SCRAPE_USEFUL_CHARS=500`（X2，success vs thin）、`ARTICLE_LEAD_CHAR_LIMIT=1600`（截斷上限）；模式：`off` / `selective`（預設） / `force` |
| **模型** | 無（純 HTTP + HTML 解析） |
| **輸出** | `item.article_lead`、`item.article_text_hash`、`item.article_extract_status` ∈ {success, thin, failed, skipped} |
| **成本** | network only；可忽略 |
| **設計依據** | 基於 244 個 fetchable source × 2 個 item = 488 個 item 的抽樣實測：**13% RSS 自足**（X1 跳過）、**59% 爬蟲補強有效**（X2 success）、**11% 爬到但 thin**（X2 thin）、**15% 爬不到**（付費牆 / 反爬）、**11% feed 暫斷**（transient）。 |
| **已知問題** | 付費牆 source（WSJ / NYT / MarketWatch / OpenAI 等 ~17 個）就是 RSS desc 100-200 字、scrape 403/401，靠下游 X3 gate 處理。 |

#### 2.2 Item Signals 機械抽取（**Plan A 已實作 2026-05-13**，取代 Canonicalization）

| 項 | 內容 |
|---|---|
| **輸入** | `RssItem`（title + summary + article_lead + metadata） |
| **邏輯** | `rss_item_signals_service.extract_item_signals(item)`——純函數、0 LLM、0 IO。產出小型結構化 dict：`{entities, primary_action, event_tags, market_tags, publisher_tier, lang}`。Entities 來自 NER + `MAJOR_ENTITY_PATTERNS` 字典 + ticker regex（`$AAPL` / `2330.TW` / `700.HK` / `7203.T`）；primary_action 用 zh/en 動詞字典逐一掃描 title→text；event_tags 是 `BLACK_SWAN_PATTERNS` 命中清單；publisher_tier 分 `aggregator` / `tier1` / `other`；lang 用中文字佔比判斷。Hash 未變一律跳過。 |
| **閾值 / 數字** | max_entities=8；無 LLM mode 切換 |
| **模型** | **無**（regex + dict + 子字串比對） |
| **輸出** | `item.item_signals`（dict）、`item.item_signals_hash`、`item.item_signals_at` |
| **成本** | 純 CPU；忽略 |
| **下游讀者** | (1) `build_embedding_inputs.entity` view 吃 `entities` 拼字串；(2) `build_embedding_inputs.impact` view 吃 `event_tags`；(3) `_item_entities()`、`_item_action()` 讀作 matching hard-gate input；(4) `_prune_active_signals` 用 entities 做 candidate filter；(5) match adjudication prompt 直接 dump 整包進 LLM context |
| **與舊 canonical_event 的關係** | `canonical_event` 欄位**保留**做向後相容（讀取時 fallback），但**寫入路徑已關閉**——新 item 永遠走 item_signals。一個 cycle 後可刪 `rss_canonical_event_service.py`。 |
| **與舊版差異** | 舊：`selective` mode 用 LLM 約 500 calls/天、`rule_fallback` 是另一條品質不同的路徑、`canonical_event_text` 進 embedding；新：**零 LLM**、單一品質路徑、embedding 直接吃 raw title+summary+lead。預期 cluster quality 不退步因為下游 `importance_service` 會用 LLM 重寫 `key_entities` / `what_happened`（驗證過 blast radius）。 |

#### 2.3 Multi-vector Embedding

| 項 | 內容 |
|---|---|
| **輸入** | 4 段 compact text：event / entity / impact / context |
| **邏輯** | 每段獨立 embed；hash 未變則 cache hit 跳過。primary `gemini-embedding-001`（768 dim）失敗（quota / 503 / unavailable）時自動切 Vertex fallback `text-embedding-004` |
| **閾值 / 數字** | `MAX_INPUT_CHARS=2048`、`DEFAULT_BATCH_SIZE=100`、`MAX_RETRY=3`、`EMBEDDING_DIM=768`、`COST_PER_1K_CHARS=$0.000025` |
| **模型** | `gemini-embedding-001`（primary）+ `text-embedding-004`（fallback） |
| **輸出** | `event_embedding` / `entity_embedding` / `impact_embedding` / `context_embedding` + `event_embedding_hash` + `embedding_version` |
| **成本** | 每 item 4 段 × ≈ 1000 chars ≈ $0.0001；3500 items/day → ≈ $0.35/天 = $10.5/月（cache hit 後實際更低） |
| **已知問題** | embedding_inputs 結構若改，hash 會全部失效一次性重算。Plan A 拔 canonical 後會觸發一次全量 re-embed（一次性成本 ≈ $3）。 |

#### 2.4 X3 Thin-Item Gate（位於 embedding 之後、matching 之前）

| 項 | 內容 |
|---|---|
| **輸入** | 已 embed 完成的 `RssItem` |
| **邏輯** | `is_too_thin_for_new_signal(item)`：`len(title + summary + article_lead) < MIN_TOTAL_FOR_NEW_SIGNAL(200)`。命中時：**允許 match 既有 signal**（高 embedding 相似度仍能 cluster），但 `outcome != "matched"` 時 `continue`、不寫 signal、不增加 `new_signal_count`、計入 `thin_dropped_count`。 |
| **閾值 / 數字** | `MIN_TOTAL_FOR_NEW_SIGNAL=200`（X3，定義於 `rss_signal_matching_service.py`） |
| **目的** | 付費牆 source（NYT/WSJ/MarketWatch/OpenAI 等）desc 只有 100-200 字，embedding 訊號量不足。直接讓它們開新 signal 會變孤兒、汙染下游 cluster；但若 embedding 對到既有 cluster 就允許加入（多源驗證）。 |
| **輸出** | `thin_dropped_count`（新 stat，寫進 `process_new_items` response 與 Signal_Process_Log） |
| **預期觸發頻率** | 10-30 items/天（基於抽樣：付費牆 + thin scrape 約 15% × 過濾掉能 match 既有 signal 的部分） |
| **已知問題** | thin items 還是吃了 embedding 成本（X3 在 embedding 之後）。要更積極可以把 gate 提前到 embedding 之前——但 embedding 成本 ~$10/月，目前 ROI 不夠誘人。 |

---

### 階段 3：Signal Matching（Hybrid + Hard Gate + Adjudication）

這是 v2 的核心，**取代** Phase 2 的全量 agglomerative clustering。

#### 3.1 Hybrid Match Score

```
score = 0.45 * cos(event_embedding,   signal.event_centroid)
      + 0.20 * max( cos(entity_emb,   signal.entity_centroid),
                    overlap(item.entities, signal.key_entities) )
      + 0.15 * cos(impact_embedding,  signal.impact_centroid)
      + 0.10 * cos(context_embedding, signal.context_centroid)
      + 0.10 * time_source_score   # 時間鄰近 + 來源去重
```

每個 item 對 active signal pool 計算上式（numpy batch 加速）。

#### 3.2 Active Signals 三層 Pruning

`active_signals` pool 上限 1000，超過時依序：

1. **Entity overlap**：item entity 與 signal entity 任一相交，命中即收
2. **Category / desk overlap**：fallback
3. **Recency**：最後 fallback，依 `window_end` 排序取 200

最終 cap 在 200 個 candidate 才丟給 hybrid matcher。

#### 3.3 Hard Gate（直接擋，不打 LLM）

```
若 item entity ∩ signal entity == ∅
   且 event cosine < 0.92
   → 擋（不合併）

若 item action 與 signal action 是 OPPOSITE_ACTION_PAIRS 之一（漲/跌、批准/拒絕、ceasefire/attack…）
   → 擋
```

#### 3.4 Threshold 三檔判定

| score 區間 | 行為 |
|---|---|
| `≥ 0.86`（generic title `≥ 0.90`） | Auto-merge：把 item 加進既有 signal，centroid 用 `0.85` decay 更新 |
| `[0.76, 0.86)` review band | 視觸發條件決定是否呼叫 Pro adjudication |
| `< 0.76` | 開新 provisional signal，記下 top-5 candidate ids 供日後 review |

#### 3.5 Adjudication 觸發條件（任一命中即觸發）

```
review band 內，且：
  - title/summary 命中 black-swan / major entity 關鍵字
  - 既有 best_signal.importance_score ≥ 70
  - best_score ≥ 0.82（高分模糊）
  - top-1 與 top-2 差距 ≤ 0.04（接近平手）
```

#### 3.6 Adjudication LLM

| 項 | 內容 |
|---|---|
| **模型** | `gemini-2.5-pro` (`MATCH_ADJUDICATION_MODEL_GEMINI`) |
| **輸出** | `{decision: same_event | same_thread | different_event, confidence, rationale}` |
| **confidence 門檻** | **三處都 hardcoded 為 0.55**（建議拆檔：same_event 0.65、其他 0.50） |

| decision | 動作 |
|---|---|
| `same_event` + confidence ≥ 0.55 | 合併進既有 signal |
| `same_thread` + confidence ≥ 0.55 | 新 provisional signal，但 thread_id 接到既有 signal 的 thread |
| `different_event` + confidence ≥ 0.55 | 完全獨立的新 signal |
| 任一 confidence < 0.55 | fallback 為 candidate（保留 top-5 candidate ids） |

#### 3.7 數字總表

| 設定 | 預設值 | 位置 |
|---|---|---|
| `SIGNAL_MATCH_AUTO_THRESHOLD` | 0.86 | settings |
| `SIGNAL_MATCH_REVIEW_THRESHOLD` | 0.76 | settings |
| `SIGNAL_MATCH_GENERIC_AUTO_THRESHOLD` | 0.90 | settings |
| Hard gate cosine | **0.92** | hardcoded |
| `CENTROID_DECAY` | 0.85 | settings |
| Adjudication trigger — high-score band | **0.82** | hardcoded |
| Adjudication trigger — top-2 margin | **0.04** | hardcoded |
| Adjudication trigger — importance | **≥ 70** | hardcoded |
| Adjudication confidence cutoff | **0.55** ×3 | hardcoded |
| Active pool cap | 200 | hardcoded |
| `RSS_SUFFICIENT_CHARS`（X1，跳過 scrape） | **400** | hardcoded (article_extraction_service) |
| `SCRAPE_USEFUL_CHARS`（X2，success vs thin） | **500** | hardcoded (article_extraction_service) |
| `MIN_TOTAL_FOR_NEW_SIGNAL`（X3，thin gate） | **200** | hardcoded (signal_matching_service) |
| `ARTICLE_LEAD_CHAR_LIMIT`（截斷上限） | 1600 | hardcoded |
| `DEFAULT_FEED_TIMEOUT_SECONDS`（ingest） | **25** | rss_ingest_service |
| `DEFAULT_MAX_WORKERS`（非 RSSHub） | 10 | rss_ingest_service |
| `DEFAULT_RSSHUB_WORKERS`（zeabur 並發上限） | **2** | rss_ingest_service |

#### 3.8 Shadow Metrics（每次 process-new-items 回傳）

`auto_match_count`、`adjudicated_match_count`、`same_thread_candidate_count`、`different_event_adjudication_count`、`adjudication_failed_count`、`review_band_count`、`match_score_avg`、`candidate_match_ratio`、`new_signal_ratio`、`duplicate_prevention_ratio`、`supported_signal_write_count`、`singleton_signal_write_count`、**`thin_dropped_count`**（X3 gate 觸發次數）

#### 3.9 已知問題（matching）

- 所有 hardcoded 數字應集中到 settings（Round 1）
- `GENERIC_AUTO_THRESHOLD=0.90` 設計矛盾，generic 標題本來 cosine 就低，永遠擋不下來
- adjudication confidence=0.55 對「合併」與「分開」同樣寬鬆，建議拆三檔
- adjudication margin=0.04 太敏感，建議 0.06–0.08
- X3 gate 在 embedding 之後觸發，仍然花了 embedding cost；要更積極可以前移到 embedding 之前（但目前 embedding 成本 ~$10/月，ROI 不高）

---

### 階段 4：Verify — Rule-based Cross-verification（W5 第一步）

| 項 | 內容 |
|---|---|
| **輸入** | 近 N 小時的 signal（預設 4 小時） |
| **邏輯** | 把 signal 的 publishers 分到獨立 ecosystem group，計算 `independent_groups` |
| **模型** | 無 |
| **輸出** | `cluster_status` + `topic_heat` |
| **成本** | $0 |

#### Cluster Status 規則

```
single_source         : sources == 1
confirmed             : sources >= 3 AND independent_groups >= 3
confirmed             : sources >= 3 AND "Global" in markets AND independent_groups >= 2
regional_only         : sources >= 3 AND single market and not Global
partially_supported   : everything else with sources >= 2
```

#### Topic Heat 規則

```
viral   : sources >= 5 AND publishers >= 4
high    : sources >= 3 AND publishers >= 3
medium  : sources >= 2
low     : sources == 1
```

Publisher group：`western_finance` / `western_general` / `us_business` / `us_tech` / `tw_finance` / `tw_general` / `europe_general` / `asia_finance`。

---

### 階段 5：Judge — Importance LLM（W5 第二步）

| 項 | 內容 |
|---|---|
| **輸入** | 通過 quality_gate 的 signal |
| **邏輯** | 對每個 signal 呼叫 LLM → 0–100 importance + impact_type + reasoning + heat_vs_importance_note。LLM 結果再經 **code-level guard rails** 強制蓋頂（避免 prompt 失效時亂打高分） |
| **模型（預設）** | `gemini-2.5-flash`（`JUDGEMENT_MODEL_GEMINI`） |
| **模型（OpenAI 備用）** | `gpt-5-mini`（`JUDGEMENT_MODEL_OPENAI`）；`JUDGEMENT_REASONING_EFFORT=medium` |
| **輸出** | `importance_score`、`impact_type`、`key_entities`、`regions`、`reasoning`、`heat_vs_importance_note` |

#### Quality Gate 預設 `supported_or_promoted`

跳過 low-value singleton；以下情況例外照樣送 judge：

- signal 命中 `MAJOR_ENTITY_PATTERNS` 或 `BLACK_SWAN_PATTERNS`（21 entity + 28 action 類關鍵字）
- signal 標題已被視為值得 promote

#### Code-level Guard Rails（程式硬蓋）

| 蓋頂條件 | 上限 | 位置 |
|---|---|---|
| Market wrap 標題（regex 命中「盤後」「market wrap」「closing bell」…） | **importance ≤ 45** | `MARKET_WRAP_CAP=45` |
| 單一公司非系統性業績稿 | **importance ≤ 65** | `SINGLE_CORP_CAP=65` |
| Public health 非市場性 | **importance ≤ 65** | `PUBLIC_HEALTH_CAP=65` |
| 單源 analysis/feature 文章 | **≤ ANALYSIS_CAP** | (待確認值) |

> Phase 3 v3 修復決策：2026-05-07 LLM 對「歐股盤後」打 90 分，故加 regex guard。

#### Importance Score 用途分檔

| 分數區間 | 用途 |
|---|---|
| `< 60` | 不進 briefing / impact / podcast |
| `≥ 60` | briefing 與 business_impact 預設候選 |
| `≥ 70` | matching 階段觸發 adjudication；briefing 內 high-count 統計 |
| `≥ 80` | story thread promotion；podcast top changes 強候選 |

#### 成本

| Provider | 單價 (per 1k tokens) | 估算 |
|---|---|---|
| Gemini Flash | input $0.075 / output $0.30 | 1 signal ≈ $0.0002；100/天 ≈ $0.02/天 = $0.6/月 |
| OpenAI gpt-5-mini | input $0.25 / output $2.00 | 1 signal ≈ $0.001；100/天 ≈ $0.1/天 = $3/月 |

> **⚠️ 已知 bug**：[rss_importance_service.py:46](app/services/rss_importance_service.py#L46) 的 `PROVIDER_PRICING` 仍用 Pro 單價 ($1.25/$10)，但實際 model 已換成 Flash → 系統回報的成本是真實成本的 ~16 倍。修正建議：把 PRICING 改成依 model 名動態查詢。

---

### 階段 6：Business Impact（W6，每小時）

| 項 | 內容 |
|---|---|
| **輸入** | `importance ≥ 60` 的 signal |
| **邏輯** | 對每個 signal 呼叫 LLM 抽取影響面 |
| **模型（預設）** | `gemini-2.5-flash`（`IMPACT_MODEL_GEMINI`） |
| **模型（OpenAI 備用）** | `gpt-5-mini`；`IMPACT_REASONING_EFFORT=high` |
| **輸出 schema** | `impacted_sectors[≤5]`、`impacted_assets[≤5]`、`impacted_regions[≤5]`、`watch_points[≤5]`、`counterfactual[≤200字]`、`gap_note[≤200字]` |
| **重試** | 每個 signal 最多 2 次（json parse + 例外各算一次） |
| **參數** | `min_score=60`、`max_signals_per_run=100`、`max_workers=5` |

#### 成本

| Provider | 估算 | 月費 |
|---|---|---|
| Gemini Flash | 50 signal/天 × $0.001 | ≈ $1.5/月 |
| OpenAI gpt-5-mini high effort | 50 × $0.01 | ≈ $15/月 |

> **⚠️ 設計可疑**：`IMPACT_REASONING_EFFORT=high` 對純 list 抽取明顯過頭，建議降到 `medium` 或 `minimal`，預估省 30–40% output tokens。

> **⚠️ Pricing bug 同階段 5**：實際是 Flash，但 PROVIDER_PRICING 用 Pro 單價。

---

### 階段 7：Daily Consolidation — Story Threads + Phase Tree（W7，每日）

| 項 | 內容 |
|---|---|
| **輸入** | 近 36 小時的 signal + 30 天 active threads + 該 thread 的 active phases |
| **邏輯** | 三步：(1) signal → thread 配對（cosine event/context centroid）；(2) **phase 分派**（W4 evidence shortcut → cosine ≥ 0.82 heuristic → 模糊區走 LLM batch）；(3) thread 記憶 refine（importance ≥ 80 用 Pro，每天最多 10）。 |
| **模型** | `gemini-2.5-flash`（phase assignment）+ `gemini-2.5-pro`（重大 thread refine） |
| **參數** | `since_hours=36`、`story_lookback_days=30`、`max_threads=200`、refine 上限 10、`PHASE_COSINE_AUTO_THRESHOLD=0.82`、`PHASE_DORMANT_AFTER_DAYS=7` |
| **輸出** | Firestore `rss_story_threads` 更新 + `rss_thread_phases` 更新 |

#### 7.1 Thread matching（既有，未變）

```
新 thread 條件：
  signal.importance_score ≥ 80
  且 沒有命中既有 thread（cosine < 0.76）

既有 thread 接續：
  signal 命中 thread 的 entity 或 cosine ≥ 0.76
  → 加為 thread member、更新 today_delta
```

#### 7.2 Composite story priority（2026-05-15 取代 importance-led sort）

W7 candidate 排序由 `_story_priority_key` 決定，依序：

1. **W4 evidence**（`adjudication_decision in {same_event, same_thread}`）
2. **Recency**（`window_end`）
3. **Signal status**（`confirmed > supported > promoted > provisional`）
4. **Publisher tier**（`tier1 > other > aggregator`）
5. **Importance bucket**（`critical > high > medium > noise`）

importance 從主導變 tie-breaker bucket——**降低 W5 一分錯導致整條 pipeline 偏的風險**。

#### 7.3 Phase Tree（2026-05-15 新增）

**概念**：phase 是 thread 內部的「敘事軸」（一條 thread 一週 2–5 個），有自己的 lifecycle。signals 不再只掛 thread，而是掛在 phase 之下。樹狀結構讓 viewer 與下游 LLM 都能看出「故事到哪一階段、怎麼發展、新軸是什麼」。

**Phase status**：
- `emerging`：剛開、signal_count < 2
- `active`：signal_count ≥ 2
- `dormant`：last_advanced_at 距今 ≥ `PHASE_DORMANT_AFTER_DAYS=7`
- `resolved`：LLM 明示

**Lazy bootstrap**：W7 第一次碰到 thread 時自動建一個 seed phase（無 LLM 成本、無 migration），之後自然分支。

**Phase 分派三層**：
1. **W4 evidence shortcut**：signal 帶 `adjudication_decision in {same_event, same_thread}` → 配最近 phase，不打 LLM。
2. **Cosine pre-filter**：cosine vs phase.event_centroid ≥ `PHASE_COSINE_AUTO_THRESHOLD=0.82` → 直接掛，不打 LLM。
3. **LLM batch**：每條 thread 內模糊 signals 一次 Flash call，吐 5-decision 詞彙。

**5-decision 詞彙**：

| Decision | 動作 |
|---|---|
| `continues_core` | 延續既有 phase，bump `last_advanced_at` |
| `new_axis` | 開新 phase，`parent_phase_id` 指出 fork 點，`status=emerging` |
| `background_repeat` | 掛回去但 `signal.is_background_repeat=true`、不前進 phase、不算入 today_delta |
| `different_thread` | flag `signal.adjudication_rationale="thread_mismatch_suspected:..."`，掛到 fallback phase 不變孤兒 |
| `duplicate_suspected` | 疑似 W4 漏抓重複，flag with `duplicate_of_signal_id`，**不開新 phase** |

#### 7.4 W4 adjudication metadata 持久化（2026-05-15）

W4 已經算好 `same_event / same_thread / different_event` 但只把 thread_id 寫進 signal——decision/confidence/rationale 全被丟。修法：`_apply_adjudication_to_signal()` helper 把四個欄位寫到 signal（`adjudication_decision`、`adjudication_confidence`、`adjudication_rationale`、`adjudication_candidate_thread_id`）。**$0 成本，純利**——W7 phase pass 直接 short-circuit 不用重判。

#### 7.5 Read-only viewer

`GET /viewer/`：FastAPI 內 serve 單頁 Cytoscape.js phase tree（pinned `cytoscape@3.30.2` CDN，零 build）。
- 左側 thread 列表（podcast 3+ 天沒覆蓋會 dim、mismatch flag 會 badge）
- 中間 phase 樹：node color=status, size=`signal_count`, edges=parent→child（dashed = new_axis 分支）
- 右側 panel：phase 細節 + signals + W4 chip + decision log
- toolbar 「show W5 influence」toggle 才會把 importance 影響呈現為 opacity（**預設不顯示，刻意避免 W5 leak**）

API：`GET /api/threads`、`GET /api/threads/{thread_id}`，read-only。

#### 7.6 觀測欄位（W7 response / Consolidate_Log 撈）

`phases_upserted`、`phases_created`、`phases_advanced`、`phase_heuristic_assignments`、`phase_w4_evidence_assignments`、`phase_llm_calls`、`phase_llm_invalid_id_count`、`background_repeat_count`、`thread_mismatch_flagged_count`、`duplicate_suspected_count`。

#### 成本

- Phase assignment LLM：~10–30 Flash calls/天 ≈ **$0.5–1/月**
- Thread refine（既有）：10 Pro × $0.005 ≈ $0.05/天 = $1.5/月
- W4 metadata 持久化：**$0 added**

#### 已知問題

- `STORY_THREAD_PROMOTION_SCORE=80` 太嚴，一週可能 < 30 個 thread；建議降到 70。
- v1 phase 詞彙中 `duplicate_suspected` 只 flag、不自動 merge——等人工觀察 1–2 週再決定 auto 規則。
- Phase-level `today_delta`、`continuation_prompt_hint`、`do_not_repeat_points` 已寫進 schema 但 **W8/W9 尚未消費**——還是讀 thread-level。等 phase 品質驗證一週後再串。
- 沒有 W7 audit script，等累積 ≥ 7 天 W7 run 後再寫 `scripts/w7_phase_audit.py`。

---

### 階段 8：Daily Briefing（W8，07:00）

| 項 | 內容 |
|---|---|
| **輸入** | `importance ≥ 60` 的近 24 小時 signal（上限 80 個）+ 昨日 briefing（過濾 `briefing_date < today` 取最新）+ **這些 signal 對應的 thread + phase tree（2026-05-15 新增）** |
| **邏輯** | (1) 按 thread 分組 signal，附 thread context（known_background / do_not_repeat_points / continuation_prompt_hint / today_delta）+ phase 列表；(2) 沒掛 thread 的進 ungrouped；(3) 全部丟給 LLM 一次產出整篇 briefing；(4) validation 失敗時 retry 一次（feedback 帶錯誤摘要） |
| **模型（預設）** | `gemini-2.5-pro`（`BRIEFING_MODEL_GEMINI`） |
| **模型（OpenAI 備用）** | `gpt-5`；`BRIEFING_REASONING_EFFORT=medium` |
| **參數** | `min_score=60`、`max_sections=10`、`max_signals_input=80`、retry 上限 1 |
| **輸出 schema** | overview + top_changes[4–6] + categories[4 個][sections] + closing |

#### 8.1 Thread / Phase context 注入（2026-05-15）

W8 從 W7 寫的 thread + phase 結構讀以下欄位餵 LLM：

- `thread.known_background`、`thread.do_not_repeat_points`、`thread.continuation_prompt_hint`、`thread.today_delta`、`thread.last_covered_in_podcast_at`、`thread.status`
- `phase.title` / `status` / `signal_count` / `parent_phase_id` / `novelty_reason`（每條 thread 列出其 phase tree）
- `signal.is_background_repeat`（W7 phase pass 標的）
- `signal.adjudication_decision`（W4 寫的：`same_event` / `same_thread` / `different_event`）
- `signal.adjudication_rationale`（W4 + W7 共用文字欄位；W7 phase decisions 寫成 `thread_mismatch_suspected:...` / `duplicate_suspected:...` 開頭）
- 從 `adjudication_rationale` 派生的兩個 boolean：`thread_mismatch_suspected` / `duplicate_suspected`（W7 phase flags，需顯式輸出讓 LLM 看得到）

Prompt 規則（明示給 LLM）：

1. `do_not_repeat_points` 列出的內容**禁止再寫**
2. `is_background_repeat == true` 的 signal **不要單獨開 section**
3. `phase.status == "emerging"` 是新軸 → 優先寫
4. 全 `dormant` 的 thread → 跳過
5. `continuation_prompt_hint` 的語感可直接借用
6. 延續主題的 section 設 `is_continuation: true`，`continuation_note` 從 known_background 取最少必要背景
7. `thread_mismatch_suspected == true`（W7 phase 標的）→ 謹慎、不用該 thread context 推論
8. `duplicate_suspected == true`（W7 phase 標的）→ 不單獨開 section，當補充來源即可

> ⚠️ **欄位來源差異**：`adjudication_decision` 是 W4 的 item↔signal 判斷（`same_event` / `same_thread` / `different_event`）；`thread_mismatch_suspected` / `duplicate_suspected` 是 W7 phase pass 的判斷，寫在 `adjudication_rationale` 文字內、由 W8 派生為 boolean。**不要混淆**——W4 的 `adjudication_decision` 從來不會是 `different_thread` 或 `duplicate_suspected`。

#### 8.2 Retry-on-validation-failure（2026-05-15）

`_generate_with_retry` wrap LLM call + validate；第一次 raise ValueError 時把錯誤摘要塞進 prompt 頂部 `retry_feedback` placeholder 再 call 一次。token 跨 attempt 累積。兩次都失敗才 raise。

> **目的**：Pro 模型偶爾少欄位的 case，從「整天沒 briefing」變成自動修復。

**觀測**：retry_count 同時寫進 `result["briefing_retry_count"]`（API response，n8n Briefing_Log）與 `signal_pool_health.briefing_retry_count`（Firestore 持久化，可 retroactive 算觸發率）。一週若都 0 表示 retry 是純保險；若常 1 則 prompt 品質有問題。

#### Briefing 4 大分類（給 podcast 再 remap 用）

```
國際局勢
國際金融
科技發展（podcast 會拆成 AI / 半導體 兩塊）
其他商業趨勢
```

#### 每 section 必含

1. What happened
2. Why it matters
3. Who it affects
4. Next watch point
5. `referenced_urls`（提供 publish package 用）

#### Continuity 欄位

briefing service 會額外回填：
- `today_delta`：今天新增的事件點
- `do_not_repeat_points`：昨日已講過，今天不該再帶背景
- `continuation_prompt_hint`：給 podcast 的「以一句話帶過昨日背景」提示

#### 成本

| Provider | 估算 | 月費 |
|---|---|---|
| Gemini Pro | 1 briefing/天 × 8k input × 4k output × $1.25/$10 | ≈ $1.5/天 = $45/月 |
| OpenAI gpt-5 | 同上 × $1.25/$10 | ≈ $45/月 |

> Briefing 是**全系統最貴單次呼叫**（單篇 ~$1.5），但每天只跑一次，總月費可控。重點不是省成本，是品質。

---

### 階段 9：Podcast Script（W9 第一步）

| 項 | 內容 |
|---|---|
| **輸入** | 今天的 briefing + **昨日 podcast script**（重複防止真正基準）+ 昨日 briefing 摘要（次要參考）+ **briefing 引用 signals 對應的 thread + phase tree**（W7 結構） |
| **邏輯** | 把 briefing 4 分類 remap 為 podcast 6 主題，**注入 thread / phase context + 昨日實際播出的 podcast 段落**，加上 8 條連續性規則，產出 6500–7500 字口語稿 + show_notes + episode_title；validation 失敗時 retry 一次 |
| **模型（預設）** | `gemini-2.5-pro`（`PODCAST_SCRIPT_MODEL_GEMINI`） |
| **模型（OpenAI 備用）** | `gpt-5`；`PODCAST_SCRIPT_REASONING_EFFORT=medium` |
| **參數** | retry 上限 1 |
| **輸出** | Firestore `rss_podcast_scripts`（script 文本、word_count、themes_covered、themes_skipped、show_notes、google_doc_url、validation_warnings 含 `script_retry_count=N` 字串） |

#### 9.1 連續性 context 注入（2026-05-15）

W9 的連續性 context 比 W8 多一層——**載入「昨日實際播出的 podcast script」**：

- 從 `rss_podcast_scripts` 抓 briefing_date 嚴格小於 today 的最新一篇
- 輸出 episode_title + themes_covered + themes_skipped + 各 segment 標題與前 200 字
- **這是 prompt 中重複防止的真正基準**——聽眾追蹤的是「昨天 podcast 講了什麼」，不是「昨天 briefing 寫了什麼」

並從 W8 已建好的 thread + phase 結構反查：

- 從 briefing 的 `referenced_signal_ids`（top_changes + sections）反查 signals
- 反查 threads + phases，按 thread 分組（與 W8 同 shape）
- W7 phase flags（`thread_mismatch_suspected` / `duplicate_suspected`）由共用 helper `signal_v2_utils.phase_flags_from_rationale` 派生

Prompt 規則（8 條，podcast 語感版本）：

1. **聽眾追蹤的是昨天 podcast 講了什麼**——同主題昨天詳述 + 今日無新進展 → 跳過；有新進展 → 只寫 delta
2. `thread.do_not_repeat_points` 列出的內容禁止再講
3. `is_background_repeat == true` → 不單獨開 sub-topic
4. `phase.status == "emerging"` → 優先寫；全 dormant → 跳過
5. `thread_mismatch_suspected == true` → 謹慎、不用該 thread context 推論
6. `duplicate_suspected == true` → 不單獨開 sub-topic
7. 全新主題 → 完整鋪陳
8. 延續事件用「延續⋯⋯今天的新變化是⋯⋯」語感，不從背景重新開場

> ⚠️ **優先序**：當 `yesterday_podcast_summary` 與 `briefing.is_continuation` 衝突時，**以 podcast 摘要為準**——那是聽眾真實聽到的。

#### 9.2 Retry-on-validation-failure（2026-05-15）

`_generate_script_with_retry` wrap LLM call + validate；第一次 raise ValueError 時把錯誤摘要塞進 prompt 頂部 `retry_feedback` placeholder 再 call 一次。token 跨 attempt 累積。兩次都失敗才 raise。

**觀測**：retry_count 寫進 `validation_warnings` 為 `script_retry_count=N` 字串（持久化）+ `result["script_retry_count"]`（API response）。模式與 W8 完全一致。

#### 6 主題映射

| Phase 4 category | Phase 5 podcast theme |
|---|---|
| 國際局勢 | 政治與地緣風險 |
| 國際金融 | 全球財經、市場與關鍵數字 |
| 科技發展（拆 1） | 科技與 AI |
| 科技發展（拆 2） | 半導體與供應鏈 |
| 其他商業趨勢 | 全球企業與商業動作 |
| （LLM 自選） | 其他值得關注的重要訊號 |

#### 腳本結構（總計 ~20 min / 6500–7500 字）

| 段 | 時長 | 字數 | 內容 |
|---|---|---|---|
| Opening | 30s | ~150 | 「歡迎回到 Informative AI。」+ 今日 mood + 3 themes |
| Top changes | 5 min | ~1500 | 4–6 條，200–300 字/條 |
| Themed deep dives | 12 min | ~4000 | 從 6 themes 選 3–5 個，600–800 字/條 |
| Closing | 2 min | ~600 | 彙整 watch_points + 「明天見。」 |

#### 編輯規範（每事件必答 4 問）

1. What happened
2. Why it matters
3. Who it affects
4. What to watch next

#### 必固定文字

- 開場：「歡迎回到 Informative AI。」
- 收尾：「感謝各位今天的收聽，明天見。」

#### 成本

≈ $1/篇 × 1/天 = $30/月（Pro）。

#### 已知問題

- 6 主題 + 4 必答 + 6500–7500 字字數預算數學上偏緊，實務上 themed deep dives 容易被擠掉。建議跑 5 篇 sample 量實際分佈。

---

### 階段 10：Podcast Audio — TTS Long Audio（W9 子步驟）

| 項 | 內容 |
|---|---|
| **輸入** | `RssPodcastScript`（純文字 script） |
| **邏輯** | 呼叫 Google TTS Long Audio Synthesis → 輸出 MP3 直接到 GCS。idempotent ID = `episode_{script_id}` |
| **模型 / 聲線** | `cmn-TW-Chirp3-HD-Charon` (`PODCAST_TTS_VOICE`)；`PODCAST_TTS_LANGUAGE_CODE=cmn-TW`；`PODCAST_TTS_LOCATION=global` |
| **timeout** | 1800 秒 (`PODCAST_TTS_TIMEOUT_SECONDS`) |
| **輸出** | GCS `gs://signal-brief-audio-…/podcasts/<date>/<script_id>.mp3` + Firestore `rss_podcast_episodes` |
| **idempotency** | sub-bucket `<run_bucket>_audio`；既有 episode 且有 audio_url 且 `force=False` → 跳過 |

#### 成本

Google TTS Long Audio Chirp3-HD：$0.016 / 1k chars（推估）。7500 字 ≈ $0.12/篇 × 1/天 = $3.6/月。

GCS storage：30 天 lifecycle，平均 ~30 MB/episode，30 episodes → < 1 GB。$0.02/GB-month ≈ 可忽略。

---

### 階段 11：Publish Package（W9 子步驟）

| 項 | 內容 |
|---|---|
| **輸入** | `RssPodcastScript` + `RssPodcastEpisode` |
| **邏輯** | 從 briefing 與 show_notes 抽取 source URL（去重保序），組成 publish metadata。idempotent ID = `package_{script_id}` |
| **輸出** | Firestore `rss_publish_packages`（episode_title、show_notes、audio_url、google_doc_url、source_urls） |
| **idempotency** | sub-bucket `<run_bucket>_package`；既有 package 且 `force=False` → 跳過 |

無 LLM、無外部費用。

---

## 3. 全部 Threshold / 數字索引（單表查詢）

> 表格內標 ⚠️ 的是建議 Review 的可疑值。

### 3.1 Matching 階段

| Settings 名 | 預設值 | 用途 | Review |
|---|---|---|---|
| `SIGNAL_MATCH_AUTO_THRESHOLD` | 0.86 | hybrid ≥ 此值 auto-merge | shadow 後校準 |
| `SIGNAL_MATCH_REVIEW_THRESHOLD` | 0.76 | review band 下限 | shadow 後校準 |
| `SIGNAL_MATCH_GENERIC_AUTO_THRESHOLD` | 0.90 | generic 標題用嚴格 auto-merge | ⚠️ 設計矛盾，建議改為「直接降為 importance≤45」 |
| Hard gate cosine | 0.92 | entity disjoint 時的硬牆 | hardcoded → 搬 settings |
| `CENTROID_DECAY` | 0.85 | centroid 更新權重（舊 85% / 新 15%） | ⚠️ 太黏舊內容，建議 0.70 |
| Adjudication 高分模糊 | 0.82 | review band 內 score ≥ 此值觸發 Pro | hardcoded |
| Adjudication margin | 0.04 | top-2 差距 ≤ 此值觸發 Pro | ⚠️ 太敏感，建議 0.06–0.08 |
| Adjudication importance | ≥ 70 | best signal importance ≥ 此值觸發 Pro | hardcoded |
| Adjudication confidence | 0.55 ×3 | LLM 回應 confidence 採信下限 | ⚠️ 建議拆三檔（same_event 0.65 / 其餘 0.50） |
| Active pool cap | 200 | 一個 item 配對的 candidate signal 上限 | hardcoded |

### 3.2 Importance 階段

| 名 | 值 | 用途 | Review |
|---|---|---|---|
| `JUDGEMENT_REASONING_EFFORT` | `medium` | GPT-5 family reasoning depth | OK |
| `MARKET_WRAP_CAP` | 45 | wrap 文章硬蓋頂 | OK（已修過一次） |
| `SINGLE_CORP_CAP` | 65 | 單源非系統性業績稿蓋頂 | OK |
| `PUBLIC_HEALTH_CAP` | 65 | public health 非市場性蓋頂 | OK |
| `ANALYSIS_CAP` | (待確認) | 單源 analysis/feature 蓋頂 | 確認實際值 |

### 3.3 Score 分檔（importance）

| 分數 | 用途 | Review |
|---|---|---|
| `≥ 60` | briefing / impact 候選下限 | OK |
| `≥ 70` | matching adjudication 觸發 / briefing high-count 統計 | ⚠️ 與 `≥ 60` 候選池不對齊，可考慮降至 60 |
| `≥ 80` | story thread promotion / podcast top changes 強候選 | ⚠️ 一週素材太少，建議降至 70 |

### 3.3.1 W7 Phase Tree（2026-05-15 新增）

| Settings 名 | 預設值 | 用途 | Review |
|---|---|---|---|
| `PHASE_ASSIGNMENT_MODEL_GEMINI` | `gemini-2.5-flash` | phase 分派 LLM | 監測 `phase_llm_invalid_id_count` 比率，>5% 升 Pro |
| `PHASE_COSINE_AUTO_THRESHOLD` | 0.82 | cosine ≥ 此值不打 LLM 直接掛 phase | shadow 後校準 |
| `PHASE_DORMANT_AFTER_DAYS` | 7 | active phase 無新 signal 多久標 dormant | OK |

### 3.4 Briefing / Podcast

| 名 | 值 | 用途 |
|---|---|---|
| `BRIEFING_REASONING_EFFORT` | `medium` | OK |
| `DEFAULT_SCORE_THRESHOLD` | 60 | min_score |
| `DEFAULT_MAX_SECTIONS` | 10 | briefing section 上限 |
| `DEFAULT_MAX_SIGNALS_INPUT` | 80 | briefing 輸入 signal 上限 |
| `IMPACT_REASONING_EFFORT` | `high` | ⚠️ 純 list 抽取建議降到 medium / minimal |
| Podcast 字數 | 6500–7500 | OK |
| Top changes | 4–6 | OK |
| Themed deep dives | 3–5 | OK |

### 3.5 TTS / Audio

| 名 | 值 |
|---|---|
| `PODCAST_TTS_VOICE` | `cmn-TW-Chirp3-HD-Charon` |
| `PODCAST_TTS_LANGUAGE_CODE` | `cmn-TW` |
| `PODCAST_TTS_LOCATION` | `global` |
| `PODCAST_TTS_TIMEOUT_SECONDS` | 1800 |
| GCS bucket lifecycle | 30 天自動刪除 |

### 3.6 Embedding

| 名 | 值 |
|---|---|
| `EMBEDDING_MODEL` | `gemini-embedding-001` |
| `EMBEDDING_FALLBACK_MODEL` | `text-embedding-004` |
| `EMBEDDING_DIM` | 768 |
| `MAX_INPUT_CHARS` | 2048 |
| `DEFAULT_BATCH_SIZE` | 100 |
| `MAX_RETRY` | 3 |
| `COST_PER_1K_CHARS_USD` | 0.000025 |

---

## 4. 全部模型索引（單表查詢）

| 階段 | 預設 Provider | Default Model | OpenAI Backup | Effort | 備註 |
|---|---|---|---|---|---|
| Canonicalize (selective) | gemini | `gemini-2.5-flash` | — | — | 命中才呼叫 |
| Embedding | gemini | `gemini-embedding-001` | — | — | Vertex `text-embedding-004` fallback |
| Match Adjudication | gemini | `gemini-2.5-pro` | — | — | review band only |
| Judge (Importance) | gemini | `gemini-2.5-flash` | `gpt-5-mini` | medium | ✅ PRICING bug 已於 2026-05-16 修復（`llm_cost_utils` 改用 per-1M-tokens） |
| Business Impact | gemini | `gemini-2.5-flash` | `gpt-5-mini` | high | ⚠️ effort 建議降 |
| Story Thread Refine | gemini | `gemini-2.5-pro` | — | — | 重大 thread only，每天 ≤ 10 |
| Phase Assignment (W7 phase tree) | gemini | `gemini-2.5-flash` | — | — | 每天 ~10–30 calls，one per thread receiving signals |
| Briefing | gemini | `gemini-2.5-pro` | `gpt-5` | medium | 全系統最貴單次 |
| Podcast Script | gemini | `gemini-2.5-pro` | `gpt-5` | medium | |
| Podcast TTS | google | `Long Audio Synthesis (Chirp3-HD-Charon)` | — | — | cmn-TW |

---

## 5. 成本估算彙整

> 假設 Gemini provider、每天 3500 items / 200 signals / 50 importance≥60 signals / 1 briefing / 1 podcast。

> ⚠️ **2026-05-16 重要修正**：之前 `compute_llm_cost` 有 1000× 放大 bug（`llm_cost_utils.py` 把 `$1.25/M` 寫成 `1.25 / 1000` 後乘 raw token count）。修復後重新估算。**舊 Firestore 的 `cost_usd` 欄位全部 ×1000 偏高**，未來看 GCP billing 為準。

| 階段 | 月費估算 (USD)（修正後） | 備註 |
|---|---|---|
| RSS Ingest (Firestore writes) | < $1 | create-only 後降本 |
| Canonicalize (Flash, selective) | $0.0015 | 500 hits/day × Flash per-token |
| Embedding (Gemini) | $0.01 | 768-dim, cache hit 後極低 |
| Matching Adjudication (Pro) | $0.003 | review band hit ~10/天 |
| Judge / Importance (Flash) | $0.0006 | 100/天 |
| Business Impact (Flash medium) | $0.0015 | 50/天 |
| Story Thread Refine (Pro) | $0.0015 | 10/天 |
| Phase Assignment (Flash, W7 phase tree) | $0.0005–0.001 | 10–30/天，cosine + W4 evidence pre-filter 後 |
| Briefing (Pro) | $0.045 | 1 篇/天 × ~$0.0015（8k input + 4k output）|
| Podcast Script (Pro) | $0.03 | 1 篇/天 × ~$0.001（更短 prompt）|
| Podcast TTS (Chirp3-HD) | $3.6 | 7500 字 × $0.016/1k —— **不受 LLM 修正影響** |
| GCS storage (30 天 lifecycle) | < $1 | — |
| **LLM/embedding 小計** | **≈ $0.10/月** | |
| **TTS + 基礎建設小計** | **≈ $5/月** | TTS 是真實大頭 |
| **總計** | **≈ $5/月** | 遠低於 $30 目標，且大頭是 TTS 而非 LLM |

> 修正後 LLM 成本基本可忽略（每月 $0.10 量級）。**TTS 才是真實成本大頭**——因為 TTS 計費按字元數、不受 token 計算 bug 影響。
>
> 之前認為「Briefing + Podcast Script 佔 $75」是錯估的結果——這兩條實際 < $0.10/月。
>
> **對齊真實值的方法**：等 GCP billing 累積一週，看 Vertex AI / Gemini API 真實扣款金額，比對 Firestore 內 `cost_usd` 累計值。差異不該超過 ~10%（餘量是 retry / fallback / Embedding cache miss）。

> ⚠️ **舊資料修正待決策**：`rss_briefings.cost_usd` / `rss_podcast_scripts.cost_usd` / `rss_judgement_runs.total_cost_usd` / `rss_business_impact_runs.total_cost_usd` 在 2026-05-16 之前寫的值全部 ×1000 偏高。可選擇：(a) 跑 migration script 全部 / 1000 修正；(b) 留著當警示、未來分析時手動除 1000；(c) 直接以 GCP billing 為準。建議 (c) + 在 Firestore 加一個 `cost_correction_note` 欄位標明 cutoff 日期。

---

## 6. 三層判斷流程圖（Hard Gate / Threshold / Adjudication）

```
┌──────────────────────────────────────────────────────────┐
│ 對每個新 RssItem 計算 hybrid_score(item, signal)         │
└──────────────────────────────────────────────────────────┘
                         │
                         ▼
       ┌─────────────────────────────────────┐
       │ Hard Gate (no LLM)                  │
       │  - entity disjoint & cos < 0.92     │
       │  - opposite action                  │
       │  → 擋（直接視為 not match）          │
       └─────────────────────────────────────┘
                         │
              通過 Hard Gate
                         ▼
       ┌─────────────────────────────────────┐
       │ Score Bucket                         │
       └─────────────────────────────────────┘
              │              │              │
           ≥0.86         [0.76,0.86)       <0.76
              │              │              │
              ▼              ▼              ▼
        Auto-merge      Review Band     New Signal
                         │
                         ▼
              ┌────────────────────────────┐
              │ Adjudication Trigger?       │
              │  - black-swan / major       │
              │  - importance ≥ 70          │
              │  - score ≥ 0.82             │
              │  - margin ≤ 0.04            │
              └────────────────────────────┘
                  │            │
                 命中          沒中
                  │            │
                  ▼            ▼
        Gemini Pro裁決      candidate
        (same_event /          (記下 top-5
         same_thread /          candidate ids)
         different_event)
                  │
                  ▼
        confidence ≥ 0.55?
                  │
              是 / 否
                  │
       依 decision 寫入 / fallback candidate
```

---

## 7. 設計 Review 重點（已知可疑 / 待驗證）

### 🔴 強建議改（風險低、收益明確）

| # | 項目 | 現值 | 建議 | 預估收益 |
|---|---|---|---|---|
| 1 | `IMPACT_REASONING_EFFORT` | `high` | `medium` 或 `minimal` | OpenAI provider 下省 $5/月 + 速度提升 |
| 2 | `PROVIDER_PRICING` 表用 Pro 單價但 model 是 Flash | bug | 改成依 model 名動態查詢 | 成本回報準確化（不影響實際花費） |
| 3 | Adjudication confidence 0.55 ×3 | 同值 | 拆三檔：same_event 0.65 / same_thread 0.55 / different_event 0.50 | 減少錯誤合併（不可逆） |
| 4 | 所有 hardcoded 數字（0.92、0.04、0.82、0.55、70、200、45、65） | 散在程式碼 | 集中到 `app/core/config.py` | 後續調參不用改程式碼 |

### 🟡 待 shadow 驗證

| # | 項目 | 假設 | 驗證方式 |
|---|---|---|---|
| 5 | `SIGNAL_MATCH_AUTO_THRESHOLD=0.86` | 是否偏鬆/偏緊 | 跑 3 天看 `duplicate_prevention_ratio` |
| 6 | `CENTROID_DECAY=0.85` | 太黏舊內容、延續事件被誤判 new | 量 same-event 在 3 天內被誤分裂為新 signal 的比例 |
| 7 | `STORY_THREAD_PROMOTION_SCORE=80` | 太嚴、thread 太少 | 跑 1 週看 active thread 數量；< 30 即降到 70 |
| 8 | `IMPORTANCE ≥ 70` adjudication trigger | 與 ≥60 候選池不對齊 | 量 60–70 區間實際被誤合的比例 |
| 9 | Podcast 字數 6500–7500 vs 6 themes vs 4 必答 | 數學偏緊 | 跑 5 篇看每段實際長度分佈 |

### 🟢 設計矛盾（建議改設計，非改值）

| # | 項目 | 問題 | 建議 |
|---|---|---|---|
| 10 | `SIGNAL_MATCH_GENERIC_AUTO_THRESHOLD=0.90` | generic 標題 cosine 一定低，這條 gate 永遠擋不下 | 改設計：generic 標題不走 matching path，直接 cap importance ≤ 45 |
| 11 | Provider 切換是 stage-level 而非 task-level | 同一階段所有 task 共用 provider | 評估按 task 細分（如 briefing 用 Pro、podcast 用 Flash） |
| 12 | `MAJOR_ENTITY_PATTERNS` 只 21 個 | 缺 ARM/AMD/Intel/Broadcom/Huawei/鴻海/聯電 | 從 production 抽 entity frequency top 50 動態維護 |

---

## 8. Firestore Collections 總覽

| Collection | 用途 | 寫入時機 |
|---|---|---|
| `rss_sources` | source registry | W1 Sheet sync |
| `rss_items` | RSS 原始 item | W2 ingest（create-only） |
| `rss_ingest_runs` | ingest run metadata | W2 |
| `rss_signals` | 增量 signal 主表（含 importance、impact、centroid 等） | W4 / W5 / W6 |
| `rss_clustering_runs` | 舊 Phase 2 全量 cluster run（shadow） | 舊 W4 |
| `rss_signal_process_runs` | v2 process-new-items run metadata | W4 |
| `rss_judgement_runs` | judge run metadata | W5 |
| `rss_business_impact_runs` | impact run metadata | W6 |
| `rss_story_threads` | 30 天 thread bookkeeping | W7 |
| `rss_thread_phases` | thread 內部敘事軸（phase tree） | W7 phase pass（2026-05-15+） |
| `rss_consolidation_runs` | consolidate-daily run metadata | W7 |
| `rss_briefings` | 每日 Layer A 研究稿 | W8 |
| `rss_podcast_scripts` | Layer B 口語稿 | W9 |
| `rss_podcast_episodes` | TTS 音訊 metadata | W9 子步驟 |
| `rss_publish_packages` | 上架用 metadata | W9 子步驟 |
| `rss_podcast_runs` | run-daily run metadata | W9 |
| `workflow_runs` | n8n retry idempotency key | 所有昂貴 endpoint |

---

## 9. 觀察期 Acceptance（建議）

| 指標 | 目標 | 量法 |
|---|---|---|
| Daily cost | < $30 USD（中期 < $100 也可接受） | GCP billing |
| Briefing 一次生成成功率 | ≥ 95% | workflow_runs.success_count / total |
| Podcast 一次生成成功率 | ≥ 95% | 同上 |
| Importance ≥ 80 精確度 | 20 個 manual sample ≥ 16/20 | 每週手動標 |
| Importance < 20 噪音正確率 | 20 個 manual sample ≥ 18/20 | 每週手動標 |
| Podcast 重複率（vs 前 7 天） | < 15% | trigram overlap |
| `duplicate_prevention_ratio` (v2 shadow) | 30–50% | W4 metrics |
| `candidate_match_ratio` | 5–15% | W4 metrics |
| `new_signal_ratio` | 30–50% | W4 metrics |
| `adjudication_failed_count` | 持續為 0 | W4 metrics |

---

## 10. Phase 6–9 Roadmap（簡要，僅列前置條件）

| Phase | 內容 | 前置 |
|---|---|---|
| Phase 6 (Tier 1) | 加 ≈25 個 RSS 官方來源 + prune 14 個 flaky source | 與 Phase 3–5 並行 |
| Phase 7 (Tier 2) | Watchlist / RSSHub routes / X 帳號監控 / Reddit | Phase 4 完成 |
| Phase 8 (Tier 3) | Active research / Structured data API（FRED/TWSE）/ Alt data | Phase 5 穩定 |
| Phase 9 (Tier 4) | Bloomberg / Refinitiv 等付費資料 | 有付費客戶 |

Roadmap 詳情參見舊版本（git history）。本次重寫聚焦現有系統的 design review。

---

## 11. Operating Principles（保留）

1. **RSS 頻率不等於重要性**：source 健康只是運維問題。
2. **Topic heat 與 importance 是兩個正交維度**：熱門 ≠ 重要（celebrity gossip 不該打高分）。
3. **每個 Phase 通過 acceptance 才開下一個**：Phase 6 (source expansion) 可並行。
4. **每個階段監控成本**：Phase 1–2 ≈ 免費；Phase 3 預算 $10/月；Phase 4+ 由本文件追蹤。
5. **Manual sampling 是必須 acceptance gate**：LLM-only 驗證不夠。

---

## 12. Glossary

| 詞 | 定義 |
|---|---|
| **Source** | `RSS List` Sheet 中的一行，含 feed URL |
| **Item** | 一則 RSS 文章 |
| **Signal / Cluster** | 一群 item 被視為描述同一事件的集合 |
| **Provisional Signal** | v2 matching 後尚未確認、僅單 member 的 signal |
| **Story Thread** | 跨多天的事件線（v2），用來給 podcast 提供 continuity |
| **cluster_status** | rule-based 多源確認程度（single_source / partially_supported / confirmed / regional_only） |
| **topic_heat** | rule-based 來源數熱度（low / medium / high / viral） |
| **importance_score** | LLM 0–100 真實重要性（與 heat 正交） |
| **Hybrid Score** | v2 matching 用的 4 cosine + entity overlap + time/source 加權分 |
| **Adjudication Band** | hybrid score 落在 [0.76, 0.86) 且觸發條件命中時的 LLM 裁決區間 |
| **Quality Gate** | judge 階段預設只跑 supported_or_promoted 的篩選 |
| **run_bucket** | n8n 排程桶（`UTC_30_MIN_FLOOR` / `UTC_HOUR_FLOOR` / `DAILY_YYYY_MM_DD`），retry idempotency 用 |
| **today_delta** | thread 對「今天新增的事件點」摘要 |
| **do_not_repeat_points** | thread 對「昨日已講、今天不該重複帶」的列表 |
| **continuation_prompt_hint** | thread 給 podcast 的「以一句話帶過背景」提示 |
| **Phase**（2026-05-15+） | thread 內部的「敘事軸 / 階段」。一條 thread 一週 2–5 個。signals 掛在 phase 之下；phase 有自己的 status（emerging / active / dormant / resolved）與 parent_phase_id（fork 來源） |
| **Phase decision vocab** | W7 phase 分派 LLM 的 5 個輸出：`continues_core`（延續）/ `new_axis`（開新軸）/ `background_repeat`（重複舊內容）/ `different_thread`（疑似 thread 掛錯）/ `duplicate_suspected`（疑似 W4 漏抓重複） |
| **W4 evidence shortcut** | W7 phase 分派時若 signal 帶 `adjudication_decision in {same_event, same_thread}`，直接配最近 phase 不打 LLM——尊重 W4 已付的 LLM 成本 |
| **is_background_repeat** | signal 上的 flag。phase decision 為 `background_repeat` 時設，下游 viewer / 之後的 W8/W9 可用來淡化 |

---

## 13. Decision Log（最近）

| 日期 | 決策 | 理由 |
|---|---|---|
| 2026-05-05 | RSS pipeline v1 上 production | source pool 穩定 |
| 2026-05-06 | Sheet sync 改 12h | Apps Script 12h 更新一次 state |
| 2026-05-07 | Phase 3 v3：market-wrap regex cap ≤ 45 | LLM 對「歐股盤後」打 90 分 |
| 2026-05-10 | RSS ingest 改 create-only | 降 Firestore writes 成本 |
| 2026-05-10 | Signal Intelligence v2 上線（incremental + hash cache + multi-vector + thread） | Phase 2 全量 re-cluster 太貴 |
| 2026-05-11 | v2 6 個優先級 bug 修復（P0–P5） | Claude code review |
| 2026-05-11 | 文件重寫為中文 system survey | 為流程設計 review 使用 |
| 2026-05-15 | W4 adjudication metadata 持久化 | 之前 same_thread decision/confidence/rationale 算完即丟，W7 拿不到；改寫到 signal 後 W7 可 short-circuit |
| 2026-05-15 | W7 candidate sort 改 composite priority | 取代 importance-led sort，降低 W5 一分錯滲透 W7 排序的風險 |
| 2026-05-15 | W7 Phase Tree 上線 | thread 內部新增 phase 抽象（status / parent_phase_id），三層分派（W4 evidence → cosine 0.82 → Flash batch），目標讓 viewer / 下游 LLM 看出「故事到哪一階段、新軸是什麼」 |
| 2026-05-15 | Read-only viewer `/viewer/` 上線 | FastAPI 內 serve Cytoscape.js phase tree（pinned 3.30.2 CDN），零 build；node size=signal_count（**不**用 importance）、importance 透過 toggle 才顯示為 opacity |
| 2026-05-15 | W8 Thread / Phase context 注入 prompt | W7 寫好的 thread.known_background / do_not_repeat / continuation_hint / phase tree / is_background_repeat / adjudication_decision 之前全被 W8 丟掉。改為按 thread 分組餵 LLM，prompt 規則由結構驅動（8 條），補完 W6 收尾標的「斷頭」 |
| 2026-05-15 | W8 retry-on-validation-failure | Pro 偶爾少欄位 → 之前整天沒 briefing；新加 1 次 retry，feedback 帶錯誤摘要餵 LLM，自動修復 |
| 2026-05-15 | W8 phase flag 欄位對齊修復 | prompt 規則 7、8 之前指 `adjudication_decision == "different_thread"`（W4 欄位永遠不會是這值，W7 寫在 `adjudication_rationale` 文字裡），靜默失效。改派生 `thread_mismatch_suspected` / `duplicate_suspected` boolean 給 LLM |
| 2026-05-15 | W8 briefing_retry_count 持久化 | retry_count 之前算了沒用；現在進 `result` + `signal_pool_health`，可 retroactive 算觸發率驗證「retry 是純保險」假設 |
| 2026-05-15 | W9 載入「昨日實際 podcast script」 | 之前只載昨日 briefing 摘要；但聽眾追蹤的是 podcast 真的講了什麼。新加 `_yesterday_podcast_summary` 抽 episode_title / themes_covered / 各 segment 標題與前 200 字，prompt 明示優先於 briefing 摘要 |
| 2026-05-15 | W9 thread + phase context 注入 | 從 briefing 的 referenced_signal_ids 反查 signals → threads → phases，按 thread 分組餵 LLM。與 W8 同 shape，podcast 語感的 8 條連續性規則 |
| 2026-05-15 | W9 retry-on-validation-failure | 同 W8 模式；retry_count 寫進 validation_warnings 持久化 + result["script_retry_count"] |
| 2026-05-15 | `phase_flags_from_rationale` 移到 `signal_v2_utils` | W8/W9 共用 helper；避免 service-level 互相 import |
| 2026-05-16 | `compute_llm_cost` 1000× bug 修復 | Codex review 發現；歷史所有 `cost_usd` ×1000 偏高，§5 月費估算同步修正（$98/月 → $5/月，TTS 才是真實大頭）|
| 2026-05-16 | `get_latest_podcast_script_before(date)` 取代 `list_recent + Python filter` | 修 W9 podcast 重複防止 lookup 邊界（同日 reruns ≥ 5 次擠掉昨日 / 跳播日誤標）；prompt 文案改「上一集」誠實命名 |
