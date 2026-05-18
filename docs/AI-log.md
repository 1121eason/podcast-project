# AI Log

## 2026/05/09 23:59 - Codex 更新
- 更新者：Codex
- 進度：開始實作 Phase 5 無人工審稿完整流程。
- 更新內容：建立 AI-log，後續每次程式、測試、README、roadmap、Google Doc 輸出邏輯更新都會追加紀錄。
- 影響檔案：docs/AI-log.md
- 測試/驗證：尚未執行，先建立追蹤文件。
- 下一步：補全 podcast script、TTS/GCS、publish package、API 與測試。

## 2026/05/09 23:59 - Codex 更新
- 更新者：Codex
- 進度：完成 Phase 5 服務層與 API 第一批實作。
- 更新內容：強化 podcast script validation 與 episode title，新增 TTS long audio 到 GCS、publish package 建立、run-daily orchestration，並新增 episode/package/today 查詢 API。
- 影響檔案：app/models/podcast.py, app/core/config.py, requirements.txt, app/clients/firestore_client.py, app/services/rss_podcast_script_service.py, app/prompts/podcast_script_v1.txt, app/services/podcast_doc_writer.py, app/services/rss_podcast_audio_service.py, app/services/rss_publish_package_service.py, app/services/rss_podcast_run_service.py, app/api/routes_podcasts.py
- 測試/驗證：尚未執行，下一步補測試後一起跑。
- 下一步：更新 README/roadmap/env 文件並加入 Phase 5 測試。

## 2026/05/09 23:59 - Codex 更新
- 更新者：Codex
- 進度：完成 Phase 5 文件與環境範例更新。
- 更新內容：README 改為無人工審稿的現有 API 流程，roadmap 改為 Informative AI、run-daily、GCS MP3 與觀察期發佈包，環境範例補上 GCS/TTS 設定。
- 影響檔案：README.md, docs/rss_ai_research_plan.md, .env.example, .env.local.example, docs/AI-log.md
- 測試/驗證：尚未執行，文件更新已補 Codex 更新註記。
- 下一步：新增 podcast script/audio/package/API 測試。

## 2026/05/09 23:59 - Codex 更新
- 更新者：Codex
- 進度：完成 Phase 5 測試新增。
- 更新內容：新增 podcast script validation、TTS/GCS、publish package、Google Doc 備份稿、Podcast API 測試，並先用 py_compile 檢查語法。
- 影響檔案：tests/test_rss_podcast_script_service.py, tests/test_rss_podcast_audio_service.py, tests/test_rss_publish_package_service.py, tests/test_podcast_doc_writer.py, tests/test_podcasts_api.py, docs/AI-log.md
- 測試/驗證：`python3 -m py_compile ...` 通過。
- 下一步：執行 unittest，修正任何失敗。

## 2026/05/10 00:08 - Codex 更新
- 更新者：Codex
- 進度：完成 Phase 5 驗證。
- 更新內容：使用專案 `.venv` 跑新增測試與全套 unittest，確認無人工審稿 podcast flow 沒有破壞既有測試。
- 影響檔案：docs/AI-log.md
- 測試/驗證：`.venv/bin/python -m unittest tests.test_rss_podcast_script_service tests.test_rss_podcast_audio_service tests.test_rss_publish_package_service tests.test_podcast_doc_writer tests.test_podcasts_api` 通過 12 tests；`.venv/bin/python -m unittest discover -s tests` 通過 82 tests。
- 下一步：設定實際 `GCS_AUDIO_BUCKET` 後可用 `/podcasts/run-daily` 做端到端實機觀察。

## 2026/05/10 01:49 - Codex 更新
- 更新者：Codex
- 進度：完成 Phase 5 GCP API 與 service account 權限設定。
- 更新內容：啟用 `texttospeech.googleapis.com` 與 `storage.googleapis.com`，替 `podcast-worker1@podcast-project-491300.iam.gserviceaccount.com` 加上 `roles/texttospeech.editor`，並在 `gs://signal-brief-audio-1121-informative-ai-audio` 加上 `roles/storage.objectAdmin`。
- 影響檔案：docs/AI-log.md
- 測試/驗證：已確認 API 啟用；project IAM 查到 `roles/texttospeech.editor`；bucket IAM 查到 `roles/storage.objectAdmin`。
- 下一步：可用 `/podcasts/run-daily` 做實機音訊產生測試，並檢查 GCS MP3 output。

## 2026/05/10 08:03 - Codex 更新
- 更新者：Codex
- 進度：確認 Zeabur n8n instance 時區。
- 更新內容：讀取 `https://easonnn.zeabur.app/rest/settings`，確認 n8n instance timezone 為 `Asia/Taipei`。
- 影響檔案：docs/AI-log.md
- 測試/驗證：`/rest/settings` 回傳 `timezone: "Asia/Taipei"`，`/healthz` 回傳 `{"status":"ok"}`。
- 下一步：如果 podcast 排程要用 Brisbane 時間，需在 n8n workflow timezone 或 Zeabur `GENERIC_TIMEZONE` 調整為 `Australia/Brisbane`。

## 2026/05/10 08:19 - Codex 更新
- 更新者：Codex
- 進度：嘗試準備將 Zeabur n8n 時區改為 Brisbane。
- 更新內容：確認本機沒有 Zeabur CLI，也沒有 `ZEABUR_TOKEN`；目前只能讀取 n8n `/rest/settings`，無法直接修改 Zeabur service environment variables。
- 影響檔案：docs/AI-log.md
- 測試/驗證：`which zeabur` 未找到；`printenv` 未找到 Zeabur/n8n timezone token；`/rest/settings` 仍回傳 `timezone: "Asia/Taipei"`。
- 下一步：需在 Zeabur Dashboard 新增 `GENERIC_TIMEZONE=Australia/Brisbane` 並 redeploy/restart，或提供 Zeabur CLI token 後由 Codex 代改。

## 2026/05/10 08:40 - Codex 更新
- 更新者：Codex
- 進度：完成 RSS Sync 狀態判斷修復並推上 GitHub。
- 更新內容：排查 `Sync_Log` 發現 production 仍只接受 `✅ OK (200)`，導致 `RSS List` 中純 `200` 的來源被判成 `not_ok`，`fetchable_source_count` 掉到 1。已更新本地程式讓 `200` 與 `✅ OK (200)` 都視為 stable/fetchable，並只提交 RSS 修復相關檔案到分支 `rss-status-200-fetchable`。
- 影響檔案：app/services/rss_source_service.py, tests/test_rss_source_service.py, docs/AI-log.md
- 測試/驗證：`.venv/bin/python -m unittest tests.test_rss_source_service` 通過；用新版邏輯對目前 Sheet dry-run 顯示 251 sources、213 fetchable、38 non-fetchable；production `/sources/rss/health` 仍顯示舊狀態 `fetchable_source_count=1`。
- GitHub：commit `43b6d0e`；draft PR `https://github.com/1121eason/podcast-project/pull/1`。
- 下一步：merge/deploy PR 後重跑 `/sources/sheets/sync`，再檢查 `Sync_Log` 與 `/sources/rss/health` 是否回到約 213 個 fetchable sources。

## 2026/05/10 15:05 - Codex 更新
- 更新者：Codex
- 進度：完成 RSS Ingest Firestore writes 降本調整。
- 更新內容：將 RSS item ingest 改為 create-only；已存在的 `rss_items` 不再更新 `last_seen_at`、`published_at` 或 `summary`，改記為 `skipped_existing_item_count`。同時移除 ingest 每次執行後對 `rss_sources` 的狀態回寫，source 健康狀態改由 n8n 12 小時檢查與 Sheet Sync 負責。
- 影響檔案：app/clients/firestore_client.py, app/models/rss.py, app/services/rss_ingest_service.py, tests/test_rss_ingest_service.py, docs/AI-log.md
- 測試/驗證：`.venv/bin/python -m unittest tests.test_rss_ingest_service` 通過 4 tests；`.venv/bin/python -m unittest tests.test_sources_api` 通過 3 tests；`.venv/bin/python -m unittest discover -s tests` 通過 82 tests。
- 下一步：部署後觀察 `Ingest_Log` 的 `updated_item_count` 是否降為 0，並追蹤新增的 `skipped_existing_item_count`。

## 2026/05/10 23:48 - Codex 更新
- 更新者：Codex
- 進度：完成 Signal Intelligence v2 第一版實作。
- 目標：把「RSS item → 全量 4h clustering → signals」升級為 Gemini-first、embedding-heavy、LLM-selective 的增量訊號處理流程，降低重複模型調用與重複 signal 寫入，並支援 podcast continuity。
- 設計決策：
  - 模型政策改為 Gemini 優先：Judgement、Business Impact、Briefing、Podcast 預設走 Gemini；OpenAI provider 保留 fallback。
  - Embedding 預設 `gemini-embedding-001`，支援多向量：event / entity / impact / context；若 SDK 或環境不支援，保留既有 Vertex embedding fallback 設計。
  - LLM selective：canonicalization 預設只在資訊不足、generic title、重大 entity / black-swan keyword 等情境呼叫 `gemini-2.5-flash`；matching 疑難區先建立 candidate，不在第一版大量呼叫 Pro；Daily Consolidation 只針對高重要度既有 thread 最多 10 個呼叫 `gemini-2.5-pro` 精修記憶。
  - `run_bucket` 是 n8n 每次排程的固定桶，例如 `UTC_30_MIN_FLOOR` 或 `DAILY_YYYY_MM_DD`；`workflow_runs` 用 `{workflow_name}_{run_bucket}` 防止 retry 重跑昂貴流程。
  - hash cache 是用穩定 hash 判斷輸入是否變更；未變更就跳過 article extraction / canonicalization / embedding / thread memory 更新。
- 行為變更：
  - 新增 `POST /signals/process-new-items`：讀取最近新 RSS items，選擇性文章抽取、選擇性 canonicalization、全量 multi-vector embedding，再用 centroid matching 增量加入既有 signal 或建立 provisional signal。
  - 新增 `POST /signals/consolidate-daily`：不做每日重新分群，而是把最近 signals 接到 30 天 active story threads，更新 `known_background`、`covered_points`、`today_delta`、`novelty_score`、`do_not_repeat_points` 與 podcast continuation hint；重大延續 thread 會選擇性用 Gemini Pro refine。
  - 擴充 `/signals/judge`：支援 `quality_gate` 與 `run_bucket`，預設只讓 supported / confirmed / promoted 或重大 singleton 進模型判斷，跳過 low-value singleton 與 generic market wrap。
  - 擴充 `/signals/business-impact`、`/briefings/generate`、`/podcasts/generate-script`、`/podcasts/run-daily`：支援 `run_bucket`，避免 n8n retry 重複花模型費。
  - Briefing candidate 排序加入 `novelty_score`；prompt 與 podcast prompt 加入 thread/today_delta/continuity 指示，避免延續事件每天重講背景。
- 影響檔案：
  - app/core/config.py
  - .env.example
  - .env.local.example
  - app/clients/gemini_client.py
  - app/clients/embedding_client.py
  - app/clients/firestore_client.py
  - app/models/rss.py
  - app/models/signal.py
  - app/api/routes_signals.py
  - app/api/routes_briefings.py
  - app/api/routes_podcasts.py
  - app/services/signal_v2_utils.py
  - app/services/workflow_run_service.py
  - app/services/rss_article_extraction_service.py
  - app/services/rss_canonical_event_service.py
  - app/services/rss_signal_matching_service.py
  - app/services/rss_signal_processor_service.py
  - app/services/rss_story_thread_service.py
  - app/services/rss_importance_service.py
  - app/services/rss_business_impact_service.py
  - app/services/rss_briefing_service.py
  - app/services/rss_podcast_script_service.py
  - app/services/rss_podcast_run_service.py
  - app/prompts/editorial_briefing_v2.txt
  - app/prompts/podcast_script_v1.txt
  - tests/test_signal_intelligence_v2.py
  - tests/test_signals_api.py
  - tests/test_podcasts_api.py
  - docs/AI-log.md
- n8n 注意事項：
  - W1 Sheet Sync 維持：`12h → POST /sources/sheets/sync → Sync_Log`。
  - W2 RSS Ingest 維持：`30m → POST /sources/rss/ingest → Ingest_Log`，只寫新 item。
  - 新增 W4 Signal Processor：W2 後 5-10 分鐘跑 `POST /signals/process-new-items`，body 建議 `{ "since_hours": 6, "limit_items": 250, "max_workers": 5, "article_extraction": "selective", "canonicalize": "selective", "embed": true, "match": true, "run_bucket": "UTC_30_MIN_FLOOR" }`。
  - W5 Verify + Judge：每小時 :30 跑 `/signals/verify` 後 `/signals/judge`，Judge body 加 `{ "quality_gate": "supported_or_promoted", "run_bucket": "UTC_HOUR_FLOOR" }`。
  - W6 Business Impact：每小時 :45 跑 `/signals/business-impact`，加 `run_bucket`。
  - 新增 W7 Daily Consolidation：briefing 前跑 `/signals/consolidate-daily`，body 建議 `{ "since_hours": 36, "story_lookback_days": 30, "max_threads": 200, "run_bucket": "DAILY_YYYY_MM_DD" }`。
  - W8 Briefing / W9 Podcast 端點不變，但 body 可帶 daily `run_bucket`；W4/W7 timeout 建議 600-900 秒，retry 關閉或最多 1 次。
  - 舊 `/signals/cluster` 保留，建議先 shadow comparison 3 天，再切掉舊 W4。
- 測試/驗證：
  - `.venv/bin/python -m py_compile app/services/rss_briefing_service.py app/services/rss_podcast_script_service.py app/services/rss_podcast_run_service.py app/services/rss_signal_processor_service.py app/services/rss_signal_matching_service.py app/services/rss_story_thread_service.py` 通過。
  - `.venv/bin/python -m unittest tests.test_signal_intelligence_v2` 通過 11 tests。
  - `.venv/bin/python -m unittest discover tests` 通過 96 tests。
  - 備註：本機 regression 過程中 Docs API 初始化因 sandbox 無網路出現 DNS error log，但相關測試仍通過，未影響本次 v2 行為。
- 下一步：
  - 部署後先讓 `/signals/process-new-items` 與舊 `/signals/cluster` shadow 3 天，比較 singleton ratio、duplicate signal count、judgement candidate count、Firestore writes、模型 token 用量與 podcast repetition。
  - 若 candidate match 比例過高，再微調 `SIGNAL_MATCH_AUTO_THRESHOLD` / `SIGNAL_MATCH_REVIEW_THRESHOLD` 與 hard gates。
  - 下一版可把 candidate match 疑難區接上 `gemini-2.5-pro` adjudication，進一步降低人工檢查與錯誤合併。

## 2026/05/11 01:30 - Claude 更新（gate/threshold/prompt review 計劃 + 文件中文化 system survey）
- 更新者：Claude (Opus 4.7)
- 進度：在 P0–P5 bug 修復之後，使用者進入「gate / threshold / prompt 邏輯檢查」階段。本次未動 code，只做了：(a) 三輪 review 計劃、(b) Pipeline 每階段 threshold/gate/prompt 對照表、(c) 各數值合理性評估（含新發現 1 個 bug）、(d) 把 `docs/rss_ai_research_plan.md` 完整重寫為中文 system survey。
- 對話脈絡：
  1. 使用者要求「gate / threshold / prompt 邏輯檢查」計劃 → Claude 給出三輪：Round 1 threshold 校準（含 magic number 集中化）、Round 2 gate 一致性審查、Round 3 prompt 一致性與重複輸出。
  2. 使用者要求用表格呈現，並說清楚每個值的「階段」「目的」→ 給了 11 個階段（matching / adjudication / canonicalize / embedding / verify / judge / consolidation / impact / briefing / podcast / TTS）的對照表，含「太高會 / 太低會」雙向風險。
  3. 使用者問「這些值有沒有設定不妥的、根據過去測試與 GCP 資料」→ Claude 明確標記「沒有 production data 讀取權限」，僅能用 AI-log incident + 程式碼合理性推論。給出 12 條疑慮，分🔴🟡🟢三級。
  4. 使用者最後要求把 `docs/rss_ai_research_plan.md` 轉換為中文 system survey，作為流程設計 review 的單一來源。Claude 完整重寫（836 行，13 章）。
- 重大發現（**新 bug**，未修）：
  - **PRICING 表與實際 model 不一致** — [app/services/rss_importance_service.py:46](app/services/rss_importance_service.py#L46) 與 [app/services/rss_business_impact_service.py:24](app/services/rss_business_impact_service.py#L24) 的 `PROVIDER_PRICING["gemini"]` 仍是 Pro 單價 `{"input": 1.25/1000, "output": 10.0/1000}`，但實際 `JUDGEMENT_MODEL_GEMINI` 與 `IMPACT_MODEL_GEMINI` 都已是 `gemini-2.5-flash`（單價 `{"input": 0.075/1000, "output": 0.30/1000}`）→ Firestore `rss_judgement_runs.total_cost_usd` 與 `rss_business_impact_runs.total_cost_usd` 被高估約 16 倍。不影響實際 GCP billing，只影響系統內部成本回報。修法：把 PRICING 改成依 model 名 lookup（或拆 `gemini_flash` / `gemini_pro` 兩鍵）。
- threshold / 模型實際確認（修正之前認知差異）：
  - `JUDGEMENT_MODEL_GEMINI` 與 `IMPACT_MODEL_GEMINI` 實際是 `gemini-2.5-flash`（不是 Pro，AI-log 較早段有寫成 Pro）。
  - `BRIEFING_MODEL_GEMINI` = `gemini-2.5-pro`，`PODCAST_SCRIPT_MODEL_GEMINI` = `gemini-2.5-pro`，`MATCH_ADJUDICATION_MODEL_GEMINI` = `gemini-2.5-pro`。
  - Importance code-level guard rails：`MARKET_WRAP_CAP=45`、`SINGLE_CORP_CAP=65`、`PUBLIC_HEALTH_CAP=65`、`ANALYSIS_CAP`（值待確認）。
  - Briefing 預設：`DEFAULT_SCORE_THRESHOLD=60`、`DEFAULT_MAX_SECTIONS=10`、`DEFAULT_MAX_SIGNALS_INPUT=80`。
  - TTS：`PODCAST_TTS_TIMEOUT_SECONDS=1800`、`PODCAST_TTS_LOCATION=global`、聲線現行預設 `cmn-TW-Wavenet-B`。
- review 重點清單（從文件 §7 整理，給未來實施參考）：
  - 🔴 強建議改（風險低、收益明確）：
    1. `IMPACT_REASONING_EFFORT: high → medium` 或 `minimal`（純 list 抽取不需深推理）。
    2. 修 PROVIDER_PRICING 對應 Flash 單價。
    3. Adjudication confidence 0.55 ×3 拆三檔：`same_event ≥ 0.65`（合併不可逆，較嚴）、`same_thread ≥ 0.55`、`different_event ≥ 0.50`。
    4. 所有 hardcoded 數字（0.92 hard gate、0.04 margin、0.82 high-score band、≥70 importance trigger、0.55 confidence、200 active pool cap、45/65 caps）集中到 `app/core/config.py`。
  - 🟡 待 shadow 驗證：`SIGNAL_MATCH_AUTO_THRESHOLD=0.86` 數值、`CENTROID_DECAY=0.85` 太黏舊內容、`STORY_THREAD_PROMOTION_SCORE=80` 太嚴、`IMPORTANCE ≥ 70` adjudication trigger 與 ≥60 候選池不對齊、podcast 字數 6500–7500 vs 6 themes vs 4 必答 數學偏緊。
  - 🟢 設計矛盾（建議改設計，非改值）：`SIGNAL_MATCH_GENERIC_AUTO_THRESHOLD=0.90`（generic 標題 cosine 一定低，gate 永遠擋不下）→ 改設計成「generic 標題不走 matching path，直接 cap importance ≤ 45」；provider 切換是 stage-level 而非 task-level（可拆 briefing-Pro / podcast-Flash）；`MAJOR_ENTITY_PATTERNS` 只 21 個，缺 ARM/AMD/Intel/Broadcom/Huawei/鴻海/聯電 等常見主體，建議從 production 抽 top 50 動態維護。
- 文件變動 — `docs/rss_ai_research_plan.md` 完整重寫為中文 system survey（836 行，取代舊英文 roadmap 為主的版本）：
  - §0 系統總覽（ASCII 流程圖 + 每日量級 + 目標月費）
  - §1 n8n 排程一覽（W1–W9 完整 body 範例）
  - §2 11 階段詳述（每階段：輸入 / 邏輯 / 閾值 / 模型 / 輸出 / 成本 / 已知問題）— 階段 0 source registry、1 ingest、2.1 article extraction、2.2 canonicalize、2.3 embedding、3 matching（hybrid + hard gate + adjudication，含 3.1–3.9 子節）、4 verify、5 judge（含 quality gate + code guard rails）、6 business impact、7 daily consolidation、8 briefing、9 podcast script、10 TTS、11 publish package
  - §3 全部 threshold / 數字索引（5 大類，標記 ⚠️ 可疑值）
  - §4 全部模型索引（含 provider / effort）
  - §5 成本估算彙整（總計 ≈ $98/月，主要在 briefing $45 + podcast $30）
  - §6 三層判斷流程 ASCII 圖（Hard Gate / Threshold / Adjudication）
  - §7 Design Review 重點 12 條（🔴 4 / 🟡 5 / 🟢 3）
  - §8 Firestore Collections 總覽（16 個 collection）
  - §9 觀察期 Acceptance 指標
  - §10 Phase 6–9 Roadmap 簡要（詳情參 git history）
  - §11 Operating Principles
  - §12 Glossary（新增 Provisional Signal / Story Thread / Hybrid Score / Adjudication Band / today_delta / do_not_repeat_points / continuation_prompt_hint）
  - §13 Decision Log（補上 2026-05-10 v2 上線、2026-05-11 P0–P5 修復、2026-05-11 文件重寫）
- 影響檔案：
  - docs/rss_ai_research_plan.md（完整重寫）
  - docs/AI-log.md（本條目）
- 測試/驗證：無 code 變更；最後一次跑 `.venv/bin/python3 -m unittest discover -s tests` 仍 99 tests OK（與 01:30 之前狀態一致）。
- 給 Codex 的下一步建議：
  - 短期（不需 production data 就能做）：修 PROVIDER_PRICING bug、降 `IMPACT_REASONING_EFFORT` 到 medium、把 magic number 集中到 settings、adjudication confidence 拆三檔。建議單獨開 PR `gate-threshold-round-1`。
  - 中期（需要 shadow log）：W4 把 process-new-items shadow metrics 寫入 Sheet `Signal_Process_Log` 並建立 3 天 dashboard；觀察 duplicate_prevention_ratio / candidate_match_ratio / new_signal_ratio 分佈再校準閾值。
  - 長期（prompt review）：對齊 4 個 prompt（importance / impact / briefing / podcast）的共用詞彙（key_entities / impact_type / watch_points 等），抽出 `prompts/_shared_concepts.md`；新增 fixture-based regression test 驗證 podcast continuity（昨天提到 X、今天提到 X 不該再 ≥80 字背景）。

## 2026/05/11 00:30 - Claude 更新（交接給 Codex）
- 更新者：Claude (Opus 4.7)
- 進度：完成 Signal Intelligence v2 + Phase 5 的 code review + 6 個優先級 bug 修復 + 文件補強。
- 背景：使用者反映 5 天累積 ~NTD 2000 GCP/API 費用（n8n 已關閉，所以僅是過去消耗）。我假設主要驅動是 Phase 2 全量 4h re-cluster + ingest 每次更新 last_seen_at + 缺乏 quality gate。Signal Intelligence v2 設計上應能把月費壓到 ~$30，但實作有 6 處 bug / 風險點需要先補。
- 修復項目：
  - **P0** `app/services/rss_business_impact_service.py`：原本沒包 try/except，例外時 `workflow_runs` 會永遠停在 `running` 並阻擋 retry。已 import `fail_workflow_run` 並用 try/except 包住主流程。
  - **P1** `app/services/signal_v2_utils.py`：`BLACK_SWAN_PATTERNS` 包了 iran / taiwan / china / war / sanction / tariff / hormuz / 供應鏈 / 戰爭 / 制裁 / 關稅 等 entity / 國名，30–50% 的地緣訊號都會命中導致 `is_major_or_black_swan` 動不動就 true、Pro adjudication 過度啟動。已重新拆成「entity 名單」與「action 類 black-swan keyword（ceasefire、bankruptcy、rate cut、export ban …）」兩組；MAJOR_ENTITY_PATTERNS 也補上 anthropic / berkshire / jpmorgan / exxonmobil / asml / samsung / 三星。
  - **P2** `app/services/rss_podcast_audio_service.py` + `rss_publish_package_service.py` + `rss_podcast_run_service.py`：原本只有 `run_daily_podcast` orchestrator 走 workflow_run，子步驟 audio / package 沒包，retry 時 TTS 會重打、publish package 會重寫。已給兩個子函式各自加 `run_bucket` 參數並在內部 start/complete/fail；`run_daily_podcast` 用 `<run_bucket>_audio` / `_package` 子桶傳下去。
  - **P3** `app/clients/embedding_client.py`：原本 `EMBEDDING_FALLBACK_MODEL` 設了但完全沒被讀。primary `gemini-embedding-001` 一遇到 quota / 503 / unavailable 會重試 3 次再炸，導致 process-new-items 整批 fail。已加 `_ensure_fallback_model`（lazy init Vertex `text-embedding-004`）+ `_is_recoverable_quota_error` 偵測 quota / 429 / 503 / unavailable，命中時優先打 fallback；fallback 也失敗才走指數退避重試。
  - **P4** `app/services/rss_briefing_service.py` + `rss_podcast_script_service.py`：`_yesterday_briefing_summary` 原本用 `recent[1]`（list_recent_briefings 的第二筆），如果今天還沒寫入會誤把今天當「昨天」、或漏掉真正昨天的。改成 `_yesterday_briefing_summary(today_date)` 過濾 `briefing_date < today_date` 並依 briefing_date desc 排序取第一筆。
  - **P5** `app/services/signal_v2_utils.py` + `rss_signal_matching_service.py` + `rss_signal_processor_service.py`：matching 時對 N 個 active signal 各算 4 次 cosine，N 增長後 O(N) 連續計算昂貴；active_signals 上限 1000 個無 pruning。已加：
    - `cosine_similarity_batch(query, candidates)`（numpy 加速，單一 query vs N candidate 一次算完）。
    - 把 `match_item_to_signal` 改成預先 batch 計算 event/entity/impact/context 4 個 sim 向量，再進迴圈組分。
    - `_prune_active_signals(item, active_signals, max_candidates=200)`：超過 200 時依 entity overlap → category/desk overlap → recency 三層 pre-filter，cap 在 200 才丟給 hybrid matcher。
- 影響檔案：
  - app/services/rss_business_impact_service.py
  - app/services/signal_v2_utils.py
  - app/services/rss_signal_matching_service.py
  - app/services/rss_signal_processor_service.py
  - app/services/rss_briefing_service.py
  - app/services/rss_podcast_script_service.py
  - app/services/rss_podcast_audio_service.py
  - app/services/rss_publish_package_service.py
  - app/services/rss_podcast_run_service.py
  - app/clients/embedding_client.py
  - docs/rss_ai_research_plan.md（新增 Signal Intelligence v2 段落 + Phase 5 標 Done + n8n W4–W9 表）
  - README.md（新增 v2 端點 curl + workflow_runs idempotency 註記）
  - docs/AI-log.md
- 測試/驗證：
  - 每個 P 修完都跑一次 `.venv/bin/python3 -m unittest discover -s tests`，最終 99 tests 全綠（與修復前數量一致）。
  - 沒有新增測試；P5 的 batch cosine 與 pruning 是純效能 / 對等行為的重構，依賴既有 14 tests in test_signal_intelligence_v2 覆蓋。
- n8n / 部署注意事項：
  - 部署後第一輪建議在 staging body 多加 `run_bucket`（推薦：W4 `UTC_30_MIN_FLOOR`、W5/W6 `UTC_HOUR_FLOOR`、W7/W8/W9 `DAILY_YYYY_MM_DD`），確認 retry 會回傳 `skipped_duplicate=true` 而不是重打。
  - W9 `/podcasts/run-daily` 子步驟 audio / package 現在各自有 `<run_bucket>_audio` / `_package` 桶；如果 run-daily 在 audio 階段 timeout，retry 同一個 `run_bucket` 不會重做 script，但 audio 子步驟會繼續往下嘗試。
  - 若觀察到 `embedding_skipped_cached_count` 沒有上升、或 `embedded_item_count` 占比很高，多半是 `_prepare_text` 截斷後 hash 變了；先別當 bug，看是否與 article_lead 改寫有關。
- 下一步（使用者明確指示）：
  - 進入「gate / threshold / prompt 邏輯檢查」階段——重點審視：
    1. SIGNAL_MATCH_AUTO_THRESHOLD / SIGNAL_MATCH_REVIEW_THRESHOLD / SIGNAL_MATCH_GENERIC_AUTO_THRESHOLD 三個閾值與 hard gate 0.92 是否合理；建議用 shadow run 一週 candidate_match_ratio / new_signal_ratio 校準。
    2. quality_gate（judge 階段）篩選邏輯 — 哪些 cluster_status / importance score 該進 Pro，哪些直接 noise。
    3. Prompt 們：editorial_briefing_v2、podcast_script_v1、business_impact_v1、importance_judge、match_adjudication 是否互相一致、是否會重複輸出 do_not_repeat_points。
  - 建議分三輪：threshold/gate 數值校準 → prompt 一致性比對 → 整體 cost / quality 端到端 metrics review。

## 2026/05/11 00:02 - Codex 更新
- 更新者：Codex
- 進度：完成 Signal Intelligence v2 下一步優化：review-band Gemini adjudication 與 shadow metrics。
- 目標：降低模糊區錯誤合併與重複 signal 建立，並讓 n8n shadow run 可直接觀察 v2 是否真的改善成本與品質。
- 行為變更：
  - `rss_signal_matching_service.match_item_to_signal` 新增 `allow_adjudication` 開關；一般單元呼叫預設不打模型，`/signals/process-new-items` 才會啟用。
  - Hybrid score 落在 review band，且命中重大/black-swan、高重要度既有 signal、高分模糊或 top candidates margin 太小時，才呼叫 `MATCH_ADJUDICATION_MODEL_GEMINI`。
  - Gemini adjudication 回傳 `same_event` 時自動合併；`same_thread` 時建立新 provisional signal 但接上既有 thread；`different_event` 時建立全新 signal，不保留 candidate merge。
  - `/signals/process-new-items` response 新增 shadow metrics：`auto_match_count`、`adjudicated_match_count`、`same_thread_candidate_count`、`different_event_adjudication_count`、`adjudication_failed_count`、`review_band_count`、`match_score_avg`、`candidate_match_ratio`、`new_signal_ratio`、`duplicate_prevention_ratio`、`supported_signal_write_count`、`singleton_signal_write_count`。
- 影響檔案：
  - app/services/rss_signal_matching_service.py
  - app/services/rss_signal_processor_service.py
  - tests/test_signal_intelligence_v2.py
  - docs/AI-log.md
- n8n 注意事項：
  - W4 `Signal_Process_Log` 建議新增欄位記錄上述 shadow metrics。
  - Shadow comparison 期間特別看 `candidate_match_ratio`、`new_signal_ratio`、`duplicate_prevention_ratio`、`singleton_signal_write_count`。
  - 若 `adjudication_failed_count` 持續大於 0，優先檢查 Vertex/Gemini 權限、model name 與 timeout。
- 測試/驗證：
  - `.venv/bin/python -m py_compile app/services/rss_signal_matching_service.py app/services/rss_signal_processor_service.py tests/test_signal_intelligence_v2.py` 通過。
  - `.venv/bin/python -m unittest tests.test_signal_intelligence_v2` 通過 14 tests。
  - `.venv/bin/python -m unittest discover tests` 通過 99 tests。
- 下一步：
  - 建議進入 n8n shadow logging 優化：把 W4/W7 response metrics 寫入 Sheet，並設計 3 天 comparison dashboard 欄位。

## 2026/05/13 08:30 - Claude 更新
- 更新者：Claude
- 進度：完成 RSS pipeline 從 ingest 到 signal gating 的全鏈路體檢與閾值校準，同時清理 RSS List 並補上 18 個新 source。
- 目標：解決 audit 顯示 20% source ingest fail 的問題，並把「要不要爬全文 / 爬到了算不算成功 / 太薄能不能開新 signal」三段決策從散在 code 裡的 hard-coded 規則改成三條清晰的閾值（X1/X2/X3）。
- 設計決策：
  - **問題定位**：audit 43 個 fail 裡 36 個是 zeabur ReadTimeout。診斷後排除 RSSHub 實例壞掉假設，根因是 `DEFAULT_FEED_TIMEOUT_SECONDS=10` < RSSHub 冷啟動 4-8s + 並發爭用。10 個 worker 同時打 50 個 zeabur URL 時，第 3-8 個工作者排隊到 12-20s，10s timeout 立刻斷線。
  - **三個閾值的取數**：基於 244 個 fetchable source × 2 個 item = 488 個 item 的實測爬蟲取樣結果決定。X1=400（13% source 達標自足）/ X2=500（與 X1 對齊，分 success vs thin）/ X3=200（embedding 在 200 字以下訊號量極度不穩）。
  - **Zeabur RSSHub 雙實例策略**：原本 `easonn` + `informative-ai-rss` 兩個實例 route catalog 不同（前者有 NYT/HKET，後者有 OFAC/McKinsey 客製 adapter）。把兩個都改用 `diygod/rsshub:chromium-bundled` 官方 image 後 route 一致；`informative-ai-rss` 上的客製 adapter 隨之失效，OFAC / World Bank / Federal Register / McKinsey 改走官方 RSS。
  - **RSS List 維運模型**：Google Sheet 是 source of truth、Firestore 是鏡像。透過 Sheets API 直接寫 sheet，避免 Firestore 直寫被下次 sync 蓋掉。OAuth scope 從 readonly 升級成 read/write 一次性 re-auth。
  - **「下架」放 RSS Candidates worksheet**：不直接從 RSS List 刪，改在 status 欄標 `下架`，同時把 source 資訊複製到 `RSS Candidates` 分頁的 backlog 等之後 RSSHub adapter 修好可以 revive。
- 行為變更：
  - **`rss_ingest_service.ingest_rss_sources`**：split worker pool — zeabur.app URL 走 `DEFAULT_RSSHUB_WORKERS=2` 並發、其他維持 `DEFAULT_MAX_WORKERS=10`，兩個 ThreadPoolExecutor 同時跑。`DEFAULT_FEED_TIMEOUT_SECONDS=10 → 25`。Audit pass rate 從 72% → 86%。
  - **`rss_article_extraction_service.should_extract_article`**：簡化成單一規則 `len(summary) < RSS_SUFFICIENT_CHARS`（X1=400）。移除 `MIN_SUMMARY_FOR_SKIP / AGGREGATOR_PUBLISHERS / is_generic_title / is_major_or_black_swan` 等舊判斷分支——這些原本是 120 字門檻的補救，X1=400 一條規則涵蓋。
  - **`extract_article_lead`**：成功路徑新增 X2 分類，`len(lead) >= SCRAPE_USEFUL_CHARS(500)` 標 `status="success"`，否則標 `"thin"`。下游可用 status 判斷爬到的內容是否值得進 embedding。
  - **`rss_signal_processor_service` matching 迴圈**：新增 X3 gate `is_too_thin_for_new_signal(item)`（title+summary+article_lead < 200 字）。outcome 不是 `matched` 且觸發 gate 時 `continue`，不寫 signal、不增加 new_signal_count、計入新加的 `thin_dropped_count` stat。X3 不阻止 match 到既有 signal——薄 item 仍可加入 cluster，只是不准開新 cluster。
  - **`google_workspace_auth.GOOGLE_WORKSPACE_SCOPES`**：`spreadsheets.readonly` → `spreadsheets`，支援 Sheets API 寫入。
  - **RSS List sheet 變更**（共 36 處）：
    - URL 修正 11 處（Hugging Face/Forrester 兩個 URL 貼錯換正確、SCMP/McKinsey 完成 migration、SEC EDGAR 改具體 filing type、6 個 NYT 分類 URL 從空格命名改成駝峰命名）。
    - 10 條 status 改 `下架`（3 Reuters + OFAC + World Bank + 2 CISA + 3 CFTC）；同步寫到 `RSS Candidates` 分頁追蹤。
    - 18 條 RSS Candidates 復活並 promote 到 RSS List（Reuters × 10 + HKET × 8）。
    - 18 條全新 gap-filling source（China Daily × 2 + SCMP China + 海峽時報 × 2 + CNA Asia + 印度 ET/LiveMint + 曼谷郵報 + RAND/Diplomat/CFR + 自由財經 + 加密貨幣 × 4）。
    - 淨變化：RSS List fetchable 從 213 → 244（+31）。
- 影響檔案：
  - app/services/rss_ingest_service.py（worker split + timeout 25）
  - app/services/rss_article_extraction_service.py（X1/X2 閾值 + 簡化 should_extract_article）
  - app/services/rss_signal_matching_service.py（X3 常數 + `is_too_thin_for_new_signal` helper）
  - app/services/rss_signal_processor_service.py（X3 gate + `thin_dropped_count` stat）
  - app/clients/google_workspace_auth.py（OAuth scope 升級到 spreadsheets read/write）
  - tests/test_rss_ingest_service.py（timeout 預設 10 → 25）
  - Google Sheet `Informative.AI_RSS Management`（RSS List + RSS Candidates 分頁同步更新）
  - docs/AI-log.md
- 測試/驗證：
  - `.venv/bin/python -m unittest tests.test_rss_ingest_service tests.test_rss_briefing_service tests.test_signals_api` 通過 16 tests。
  - X1/X2/X3 smoke test：手動構造 4 個 RssItem（desc=0 / 250 / 500 / no_url）驗證 should_extract_article 跟 is_too_thin_for_new_signal 行為。
  - Audit 三輪：原始（72% pass，43 fail）→ 加 timeout 25 但 8 workers（73% pass，40 fail，沒幫助）→ 加 split pool 2 workers（87% pass，11 fail，證明問題在並發不在 timeout）→ split pool 10+2 workers（86% pass，13 fail，最終 production 設定）。
  - 488 item 抽樣爬蟲：13% RSS 自足 / 59% 爬蟲補強有效 / 15% 付費牆爬不到 / 11% feed 拉不到（多為 transient）。
- 部署 / 運維注意事項：
  - **Sheet sync 必須跑一次**才能讓 Firestore 拿到新增的 36 個 source 變更：`POST /sources/sheets/sync`。
  - **OAuth token 換新 scope**：`.venv/bin/python scripts/authorize_google_workspace.py` 已執行；token 寫進 `.secrets/google_oauth_token.json`，包含 `spreadsheets`（無 readonly）。
  - **Zeabur RSSHub 兩個實例都已改用 `diygod/rsshub:chromium-bundled` image**；NYT/OpenAI 等 puppeteer 需求的 route 在兩個實例都能用。
  - **n8n W2 Ingest_Log 注意觀察**：`new_item_count` 預期上升（多了 36 個 source）、`failed_source_count` 預期下降（並發/timeout 修正後）；`source_results` 看 zeabur 與其他的 fetch_duration_ms 差異。
  - **n8n W4 Signal_Process_Log 注意觀察**：新增 `thin_dropped_count` 欄位——這是 X3 gate 拒絕開新 signal 的 item 數，預期穩定在 10-30/天，主要來自 paywall source（NYT/WSJ/MarketWatch/OpenAI 等 desc 100-200 字）。
- 下一步：
  - **P0 sync sheet**（5 分鐘）：跑 `/sources/sheets/sync` 讓 Firestore 拿到新 source，之後跑一輪 ingest 觀察 `thin_dropped_count` 真實數字。
  - **P1 Plan A 拔 LLM canonicalization**（半天）：把 `rss_canonical_event_service.py` 整個拔掉，改成機械式 `extract_item_signals()`（NER + 字典 + metadata，0 LLM call）。`build_embedding_inputs` 改寫成不依賴 canonical_event 結構。bump `EMBEDDING_VERSION` 觸發一次全量 re-embed。預計影響：per-item LLM call 從 ~500/天 → 0、canonical 月成本從 $1.5 → $0、雙軌品質（LLM vs rule_fallback）統一。
  - **P2 `.gov` 低並發 pool**（30 分鐘）：複製 `RSSHUB_HOST_MARKER` 模式，把 `.gov` URL 限制到 2-3 workers。修剪樣顯示 BLS/FTC/CFTC 全部單獨打都活、並發時 403。
  - **P4 監控**：把 `thin_dropped_count` / `scrape_thin_count` / `rss_sufficient_skip_count` 寫進 Ingest_Log 與 Signal_Process_Log，建議週級 trend dashboard。

## 2026/05/13 11:30 - Claude 更新
- 更新者：Claude
- 進度：完成 W5（Verify + Judge）優化第一階段——確立三原則政策、修 cost 失真、加 guard-rails 觀測、寫永久 audit 工具。
- 目標：把 W5 重新分工成「Verify 只看證據、Judge 只看重要性、Guard rails 是短期補救＋觀察工具」。先做不改變行為的監控與 bug 修正，然後用實際資料決定下一步該動哪裡，避免憑感覺改規則。
- 設計決策：
  - **W5 三原則確立**：
    1. **Verify** 是純規則（cluster_status / topic_heat），由 source_count / publisher_count / independent_groups / market_levels 推出，**零 LLM**，作答「**有多少證據**」。
    2. **Judge** 是 LLM 評分（0-100 importance + impact_type），作答「**多重要**」。**不該被 cluster_status / source_count 影響打分**，因為「單源但極重要」（Reuters 獨家 Fed）和「多源但不重要」（30 家報蘋果小漲）都是合理場景。
    3. **Guard rails** 是短期止血——LLM 在某類稿系統性出包時的 regex cap。每條 cap 必須**可觀測**（counter）、**有死期**（季度 review）。**不是真相工具**，prompt 修不好才靠 cap。
  - **保留全部 4 條 cap 的決策**：4 天歷史審計顯示所有 cap 觸發率 0%（160 個判過的 signal，0 個被擋），但保留作為「解決方案庫」備用——cap 本身**不會吃 LLM cost**（regex 是純 CPU、跑在 LLM 之後），即使長期不觸發也沒有運維成本。發現 LLM 又對某類稿出包時，補一條 cap 是最便宜的補丁。
  - **Pricing bug 是優化前提**：歷史 cost 報告失真 ~28×（importance + business_impact 用 Pro 單價算 Flash 用量），不修就無法判斷後續優化效果。
  - **單一 source of truth 為 model**：先前 4 個 LLM 服務各自 hardcode `PROVIDER_PRICING`，model 換了 price 沒換 → 凡是 keyed on model 都有風險。新建 `app/services/llm_cost_utils.py` 集中管理 8 個 model 單價，所有服務 `compute_llm_cost(model, in, out)` 一條規則。
  - **Mode (b) 工作流確立**：使用者目前是「優化 + 偶爾 dev 測試 + 用歷史資料觀測」模式，**不上 production**。因此 audit script 設計成可吃歷史資料（含 retrospective replay 從 `signal.heat_vs_importance_note` 反推 guard 觸發），不需要等 production 累積。
- 行為變更：
  - **新增 `app/services/llm_cost_utils.py`**：`MODEL_PRICING` table（gemini-2.5-flash / gemini-2.5-pro / gemini-embedding-001 / text-embedding-004 / gpt-5-mini / gpt-5 / gpt-4o / gpt-4o-mini），`pricing_for_model()` + `compute_llm_cost(model, input_tokens, output_tokens)` 兩個 helper。fallback pricing 用 Pro 級別（寧可 over-report 不要 silent under-count）。
  - **`rss_importance_service.py` (Judge)**：
    - 移除 `PROVIDER_PRICING` 寫死表 → 改用 `compute_llm_cost`，per-model token 累計（同一 run 可混 provider 仍正確）。
    - `_apply_guard_rails` 新增 `triggered: list[str]` 紀錄哪幾條 cap 觸發，回填到 `payload["_guard_rails_triggered"]`。
    - 主迴圈累積 `guard_rails_triggered: dict[str, int]` 寫進 `RssJudgementRun`。
    - `judge_model` 改成「該 run 中用最多 token 的 model」而不是 `JUDGEMENT_MODEL_GEMINI` 推斷（更準）。
  - **`rss_business_impact_service.py` (W6)**：同樣的 pricing 改法，per-model token 累計。
  - **`rss_briefing_service.py` (W8)**：移除 `PROVIDER_PRICING`，改用 `compute_llm_cost(model_used, ...)`。原本 cost 就是對的（用 Pro），這次純粹是換成統一 utility。
  - **`rss_podcast_script_service.py` (W9)**：同上。
  - **`app/services/signal_v2_utils.py`**：新增 `importance_bucket(score) -> "critical" | "high" | "medium" | "noise"`。下游消費者建議改吃 bucket 而非 raw score，未來調整門檻時只改一處。
  - **`app/models/signal.py`**：`RssJudgementRun` 新增 `guard_rails_triggered: dict[str, int]` 欄位（4 條 rule 名稱）。
- 新增工具：
  - **`scripts/w5_principle_audit.py`**：永久 audit script（從 `/tmp` 搬入），跑 PYTHONPATH=. .venv/bin/python scripts/w5_principle_audit.py。對歷史資料三原則打分：
    - P1：`Pearson r(importance, source_count)`，<0.25 ✅、≥0.45 ❌
    - P2：四種 cluster_status 的 importance 中位數 spread，<15 ✅、>25 ❌；補充指標 single_source @ ≥70 比率（>5% healthy）。
    - P3：兩條資料路徑——(a) run-level counter（P1 部署後才有）+ (b) retrospective replay 從 `signal.heat_vs_importance_note` 正則解析 `[guard] ...` 標記，立刻可看歷史 4 條 cap 觸發率。
    - P0 cost 健康度：avg cost/signal，< $0.0008 視為 Flash pricing 正常、>= $0.005 視為 Pro pricing（fix 未生效）。
- 4 天歷史審計結果（mode-b baseline，160 個 judged signal）：
  - **P1 ✅ PASS**：r = 0.091（importance 跟 source_count 幾乎無關，Judge 沒偷看證據量）。
  - **P2 ❌ FAIL（但有 confounder）**：spread = 25 分（single=45 / partially=60 / regional=70），但 single_source @ ≥70 比率 14.3%（Judge 沒殺光單源）。判讀：主要是資料偏差（single_source 本來多是小事），不是 LLM bias。**不立即改 prompt**。
  - **P3 🗑️ 0% 全 KILL（但保留）**：market_wrap / single_corp / public_health / analysis 4 條 cap 過去 4 天 0 觸發。決策：**保留全部 4 條**，當作「解決方案庫」備用。Cap 是純 CPU（regex），不吃 LLM cost，留著未來 LLM 又出包時直接套用。
  - **P0 ❌ 歷史 cost 仍失真**：4 天回報 $2.62、avg $0.0164/signal（Pro 級）。預期：fix 之後新 run 的 cost 會掉到 ~$0.0003/signal（~28× 修正）。歷史 run 的 cost 數字不會回填，只 fix 從現在開始。
- 影響檔案：
  - app/services/llm_cost_utils.py（新建）
  - app/services/rss_importance_service.py
  - app/services/rss_business_impact_service.py
  - app/services/rss_briefing_service.py
  - app/services/rss_podcast_script_service.py
  - app/services/signal_v2_utils.py
  - app/models/signal.py
  - scripts/w5_principle_audit.py（新建）
  - docs/AI-log.md
- 測試/驗證：
  - `.venv/bin/python -m unittest discover -s tests` 通過 99 tests（與優化前一致）。
  - Smoke test pricing utility：confirms gemini-2.5-flash $0.225 vs gemini-2.5-pro $6.25 for 1000 input + 500 output，差 27.8×。
  - `scripts/w5_principle_audit.py` 跑在 Firestore 歷史資料：160 signals / 26 runs / 4 天，三原則打分如上。
- 下一步（mode-b 工作流）：
  - **每 1-2 週跑一次 `scripts/w5_principle_audit.py`** 累積判斷信心。
  - **觀察 P2 spread**：若樣本擴大到 1000+ signals 後 spread 仍 ≥ 25 且 single_source ≥70 率仍 ≥ 5%，再決定要不要改 prompt 拿掉 cluster_status。
  - **觀察 P3 cap 觸發**：若某條 cap 連續 30 天 0 觸發 → 可考慮砍掉；若觸發率突然 ≥ 20% → 改 prompt 不要靠 cap。
  - **W5 暫不再動 code**，等下次 dev 測試或 production data 累積到「資料說話」再決策。
  - **可選擴展（暫不做）**：把 audit script 概念套到 W4 / W6（W4 看 X1/X2/X3 觸發分布、W6 看 IMPACT_REASONING_EFFORT 是否 over-paying）。等 W5 跑出實效再說。

## 2026/05/13 13:00 - Claude 更新
- 更新者：Claude
- 進度：完成 W5 收尾整理——`publisher_tier` 上 signal 模型、entity 字典合併單一來源、guard-rail caps 全部搬進 settings、下游 importance 比較改用 bucket helper。本輪 W5 在 mode-b 階段所有可做的優化都收齊。
- 目標：把 W5 三原則政策落實到資料結構（publisher_tier 顯式存在 signal 上方便排查）+ 程式整潔度（單一字典 source of truth、可調 settings、bucket-based 比較），讓未來資料說話時調整門檻只動一處。
- 設計決策：
  - **publisher_tier 直接寫進 RssSignal**（不是動態計算）：好處是 Firestore 查詢 / dashboard 看得到、未來 quality_gate 加 `tier1 single-source pass` 邏輯時不用 join 拉所有 item。代價是新增一個欄位（既有 signal 預設空字串、自然過渡）。
  - **TIER1 publisher 清單擴大**：除了原本 12 家（Reuters / Bloomberg / AP / NYT / WSJ / FT / BBC / Nikkei / SCMP / 中央社 / HKET / Reuters Markets），新增 5 家（The Guardian / CNBC / Le Monde / Deutsche Welle / Nikkei（日經））——這些都是 our RSS list 的高頻來源，有 RSS 自足或 scrape success 紀錄。
  - **`signal_publisher_tier(publishers)` 採「best wins」語義**：任何 publisher 是 tier1 → 整 signal 標 tier1；全部是 aggregator → 整 signal 標 aggregator；其他情況 → "other"。理由：signal 是「事件聚合」，只要有一家權威來源報過就值得當 tier1 對待。
  - **`SYSTEMIC_ENTITIES` 從 MAJOR_ENTITY_PATTERNS 衍生**：移除 hardcoded `{Apple, Microsoft, ...}` 15 個 Title Case 清單，改成「`MAJOR_ENTITY_PATTERNS` 減去非企業實體（央行、AI 私人實驗室）」+ Saudi Aramco（沒在 MAJOR 但是 systemic 能源企業）。結果 17 個 entity 涵蓋 tech / finance / energy / asian_tech，跟 `is_major_or_black_swan` 用同一個底層字典，未來加新 entity 只需改 `MAJOR_ENTITY_PATTERNS`。
  - **Caps 進 settings.py 而不是 .env**：caps 是「半永久」設定（季度 review），不是部署時換的環境變數。寫進 `Settings` 類別讓他們有預設值、有 docstring、有 type；如果未來真的要熱調可以再加 `.env` override（pydantic-settings 自動支援）。
  - **`importance_bucket()` 接下游不是全面替換**：只取代「閾值比較」的場景（briefing high_count / story_thread refine / matching adjudication）。排序用的 raw score 比較（如 story_thread 的 sort key）保留，因為排序需要連續值。
- 行為變更：
  - **`app/services/signal_v2_utils.py`**：
    - 新增 `TIER1_PUBLISHERS`（17 個）、`AGGREGATOR_PUBLISHERS`（4 個）兩個 set，原本在 `rss_item_signals_service.py` 的搬過來作為 single source of truth。
    - 新增 `publisher_tier(publisher: str) -> str`：單 publisher 對 → "tier1" / "aggregator" / "other"。
    - 新增 `signal_publisher_tier(publishers: list[str]) -> str`：signal 多 publisher 採 best-wins 語義 → "tier1" / "other" / "aggregator" / ""。
  - **`app/services/rss_item_signals_service.py`**：移除本地的 `_publisher_tier` / `AGGREGATOR_PUBLISHERS` / `TIER1_PUBLISHERS`，改 import 共用版本。`extract_item_signals` 內 publisher_tier 計算結果不變。
  - **`app/models/signal.py`**：`RssSignal` 新增 `publisher_tier: str = ""` 欄位。`RssJudgementRun` 之前已加 `guard_rails_triggered`，這次不動。
  - **`app/services/rss_signal_matching_service.py`**：
    - `_new_signal_from_item` 新增 `publisher_tier=signal_publisher_tier(publishers)` 寫入欄位。
    - `_merge_item_into_signal` 在 publisher list 更新後重算 `signal.publisher_tier`（merge 進 tier1 publisher 會升級 tier、merge 進 aggregator 不會降級）。
    - `_should_adjudicate_match` 的 `(best_signal.importance_score or 0) >= 70` 改成 `importance_bucket(...) in {"critical", "high"}`。
  - **`app/services/rss_importance_service.py`**：
    - `SYSTEMIC_ENTITIES` 改成 derived 形式，從 `MAJOR_ENTITY_PATTERNS` 過濾 `_NON_CORPORATE_PATTERNS`（fed / federal reserve / ecb / boj / 央行 / 聯準會 / openai / anthropic）+ 加 saudi aramco。17 個 entity。
    - 4 條 cap 常數改成 `settings.JUDGE_CAP_*` 讀取（程式碼層面 `MARKET_WRAP_CAP = settings.JUDGE_CAP_MARKET_WRAP` etc.），值不變（45/65/65/60）。
  - **`app/services/rss_briefing_service.py`**：`high_count = sum(1 for s in signals if (s.importance_score or 0) >= 70)` 改成 `importance_bucket(s.importance_score) in {"critical", "high"}`。
  - **`app/services/rss_story_thread_service.py`**：`if (signal.importance_score or 0) >= 80` 改成 `if importance_bucket(signal.importance_score) == "critical"`。
  - **`app/core/config.py`**：新增 4 個 `JUDGE_CAP_*` 欄位 in `Settings`，預設值跟原本 hardcoded 一致（45 / 65 / 65 / 60），附 docstring 註明季度 review、保留作為觀察工具。
- 影響檔案：
  - app/core/config.py（新增 4 個 settings）
  - app/models/signal.py（RssSignal 加 publisher_tier）
  - app/services/signal_v2_utils.py（搬入 tier 字典 + 2 個 helper）
  - app/services/rss_item_signals_service.py（改 import 共用版本）
  - app/services/rss_signal_matching_service.py（寫 publisher_tier 到新/合併 signal + bucket helper）
  - app/services/rss_importance_service.py（SYSTEMIC_ENTITIES derived + caps from settings）
  - app/services/rss_briefing_service.py（bucket helper）
  - app/services/rss_story_thread_service.py（bucket helper）
  - docs/AI-log.md
- 測試/驗證：
  - `.venv/bin/python -m unittest discover -s tests` 通過 **99 tests**（與優化前一致）。
  - Smoke test publisher_tier：Reuters / BBC / Bloomberg / 中央社 → tier1；Yahoo奇摩 / MSN → aggregator；TVBS / 小 blog → other。signal_publisher_tier（混合）：含 Reuters → tier1（best wins）；全 aggregator → aggregator；空 list → ""。
  - Smoke test SYSTEMIC_ENTITIES：17 個，包含 alphabet / amazon / apple / asml / berkshire / exxonmobil / google / jpmorgan / meta / microsoft / nvidia / samsung / saudi aramco / tesla / tsmc / 三星 / 台積電。**不**包含 fed / ecb / openai。
  - Smoke test settings caps：4 個 cap 正確讀到 45 / 65 / 65 / 60。
  - Smoke test importance_bucket：95→critical、80→critical、75→high、65→medium、55→noise、None→noise。
- 行為對應的 mode-b 工作流：
  - **新建 signal** 起立刻有 `publisher_tier` 值，可在 Firestore console / signal API 直接看「這個 signal 來源權威度」。
  - **新 signal merge 進舊 signal** 時 tier 會重算（加入 tier1 publisher 會升級 → "tier1"，加入 aggregator 不會降級）。
  - **舊 signal 沒有 publisher_tier 欄位**會回傳空字串，下游若用此判斷需 default 處理（目前還沒地方在用，等之後 quality_gate 升級才會加）。
  - **季度 review caps 觸發率** 時，現在從 settings 直接看（不用翻 code），未來可改用 `.env` 動態調整（pydantic-settings 已支援）。
  - **`importance_bucket` 是未來改門檻的唯一單點**——若決定 critical 從 ≥80 改 ≥85，只動 `signal_v2_utils.py` 一處，下游 briefing / story_thread / matching 全部自動跟著走。
- Prompt audit 排程（定期審查 — 使用者明確列為「我們定期要做的審查」）：
  - **每月一次** 對下列 prompt 做系統性 review：
    - `app/prompts/importance_judgement_v1.txt`（Judge）
    - `app/prompts/editorial_briefing_v2.txt`（Briefing）
    - `app/prompts/business_impact_v1.txt`（W6）
    - `app/prompts/podcast_script_v1.txt`（Podcast）
  - **觸發條件**：每月初 + 每次發現 LLM 失誤模式（會反映在 guard_rails_triggered 統計）。
  - **檢查項目**：(a) 是否包含已不再需要的舊上下文；(b) reasoning_effort / temperature 是否還合理；(c) instruction 是否與下游 schema validator 對得齊；(d) prompt 長度 vs 實際 token usage（觀察 cache 命中率）。
  - **不在這輪做**：純優化階段，沒有 production 資料樣本還不夠多。等 mode (b) 累積足夠 dev test 案例再做。
- 下一步：
  - **延後到「資料說話」再動的事項**：
    - Quality gate 加 `tier1 single-source pass` 邏輯（需要先觀察單源高分率是否真的掉到 < 5% 才急）。
    - 改 prompt 拿掉 `cluster_status` / `source_count`（需要先觀察樣本 1000+ 後 spread 是否仍 ≥ 25）。
    - 砍某條 cap（需要連 30 天 0 觸發）。
  - **可選擴展（暫不做）**：把 audit script 概念套到 W4 / W6——這次不延伸，等 W5 跑出實效再說。
  - **W5 整體優化告一段落**，下一輪可進 W6 Business Impact（IMPACT_REASONING_EFFORT=high 是否 over-paying、impact prompt schema 是否還合理）或 W8 Briefing（thread context 注入 prompt——之前已分析過、未動工）。

## 2026/05/13 14:00 - Claude 更新
- 更新者：Claude
- 進度：完成 W6 Business Impact 三項優化——清乾淨 prompt 輸入（移除 W5 結果欄位）、降 reasoning_effort、加 LLM 輸出健康度監控。W6 從「重新做一次 Judge 才能 explain」改成「純 explainer」，符合 W5 三原則延伸。
- 目標：把 W6 的角色釐清成「對 W5 認定為重要的事件做下一步影響分析」，**不重新做 Verify / Judge 的工作**。同時觀察 LLM 是否在偷懶（list 沒填滿、counterfactual 空白），為未來 prompt audit 累積資料。
- 設計決策：
  - **Prompt input 拿掉 importance_score + cluster_status**：W5 原則延伸——W6 不該被 Judge 的分數或 Verify 的多源狀態影響「下手深度」。保留：`title / summary / impact_type / publisher / key_entities / regions`——這些都是「事件是什麼」的描述性欄位。`impact_type` 雖然也是 Judge 輸出但是**類別**（market/policy/tech…），不是分數，給 LLM 知道事件類型有助於分析方向，保留。
  - **降 IMPACT_REASONING_EFFORT high → medium**：W6 6 個輸出有 4 個是 list 抽取（純 lookup），2 個短句 ≤200 字。high effort 對純抽取明顯過頭。research plan 早就標 ⚠️ 設計可疑。預期省 30-40% output tokens（OpenAI 路徑、Gemini 不受影響因為 Gemini Flash 沒有 reasoning_effort 參數）。
  - **W6 monitoring 是「LLM 健檢」而非「guard rails」**：與 W5 guard_rails_triggered 不同——
    - W5 監控的是「我們的防護網有沒有啟動」（離散事件 counter，cap 觸發次數）
    - W6 監控的是「LLM 自己的輸出品質」（連續指標，平均 list 長度 / 空欄位率 / 字數）
    - W6 目前**沒有** guard rails，因為沒有歷史 LLM 失控紀錄。等 monitoring 累積資料看到「watch_points 長期 < 2 / counterfactual 30%+ 空白」這種異常，**那時再決定要改 prompt 還是加 cap**。
  - **保留 RssBusinessImpactRun 既有欄位不動**：新增 8 個 monitoring 欄位（avg_sectors / avg_assets / avg_regions / avg_watch_points / empty_counterfactual_count / empty_gap_note_count / avg_counterfactual_chars / avg_gap_note_chars），既有 cost / token / failed_count 全保留。
- 行為變更：
  - **`app/services/rss_business_impact_service.py::_render_prompt`**：input 從 8 個欄位減到 6 個，移除 `importance_score` / `cluster_status`。函數 docstring 標明這是 W5 三原則延伸。
  - **`app/prompts/business_impact_v1.txt`**：對應移除 `重要度分數: {importance_score}` 與 `跨來源狀態: {cluster_status}` 兩行。
  - **`app/core/config.py::IMPACT_REASONING_EFFORT`**：`"high"` → `"medium"`，附 inline comment 註明 2026-05-13 改、預期省 30-40% output tokens。
  - **`app/models/signal.py::RssBusinessImpactRun`**：新增 8 個 monitoring 欄位，預設值 0。模型 docstring 標明用於「W6 health-check checklist」review。
  - **`app/services/rss_business_impact_service.py::analyze_business_impact`**：每個成功 analyze 的 signal 累積 8 個 monitoring 統計值，run 結束時除以 analyzed 數量算平均，寫進 RssBusinessImpactRun。
- 影響檔案：
  - app/core/config.py（IMPACT_REASONING_EFFORT high→medium）
  - app/models/signal.py（RssBusinessImpactRun 加 8 個 monitoring 欄位）
  - app/services/rss_business_impact_service.py（清 prompt input + 累積 monitoring stats）
  - app/prompts/business_impact_v1.txt（移除 2 個欄位 placeholder）
  - tests/test_rss_business_impact_service.py（新增「prompt 不含 importance_score / cluster_status」測試）
  - docs/AI-log.md
- 測試/驗證：
  - `.venv/bin/python -m unittest discover -s tests` 通過 **100 tests**（多 1 個新測試：test_prompt_excludes_judge_and_verify_outputs）。
  - 既有 test_prompt_includes_fields 改名為 test_prompt_includes_descriptive_fields，斷言 title / key_entities / publisher 仍在 prompt 內。
- W6 健康度檢查清單（定期審查 — **使用者明確要求列為「之後需要注意、做反覆驗證」**）：
  - **檢查頻率**：每月初 + 每次發現 LLM 輸出異常 + 每次調 W6 prompt 之後 1 週。
  - **檢查指標**（從 `rss_business_impact_runs` collection 撈）：
    1. **`avg_sectors_per_signal`**：健康範圍 3.0-5.0（LLM 填滿 list）。< 2.5 → LLM 偷懶或 prompt 不清楚。
    2. **`avg_assets_per_signal`**：健康範圍 2.0-5.0（不是每個 signal 都有對應 assets）。< 1.5 → 可能影響類型偏 macro/policy 多。
    3. **`avg_regions_per_signal`**：健康範圍 2.0-5.0。< 1.5 → 區域分析不到位。
    4. **`avg_watch_points_per_signal`**：健康範圍 3.0-5.0。**LLM 最容易偷懶的欄位**。< 2.5 → 改 prompt 強化「列具體可追蹤事件 / 數據」要求。
    5. **`empty_counterfactual_count / analyzed_signal_count`**：健康 < 10%。> 30% → LLM 對反方論點放棄，改 prompt 或加 retry。
    6. **`empty_gap_note_count / analyzed_signal_count`**：健康 < 10%。> 30% → 同上。
    7. **`avg_counterfactual_chars`**：健康 30-200 字。< 20 → 一句話交差。> 180 → 接近上限可能被截斷。
    8. **`avg_gap_note_chars`**：健康 30-200 字。
  - **觸發行動的決策矩陣**：
    - 1-2 個指標微異常 → 觀察一個月看是否回穩
    - 同一指標連 4 週異常 → 改 prompt 該欄位
    - 多個指標同時異常（≥3 個）→ reasoning_effort 太低（從 medium 升 high）或 model 換 Pro
    - 全部正常但 cost 超預算 → 反向：reasoning_effort medium → minimal、或 model Flash 換更小的
  - **與 W5 體檢的關係**：W5 看 guard_rails_triggered（攔截 LLM 出錯次數）、W6 看輸出品質（LLM 自我表現）。**兩個一起跑才看得到完整 prompt 健康度**。
- 觀測腳本（暫不寫）：
  - W6 體檢目前**沒有像 `scripts/w5_principle_audit.py` 那樣的專用 script**。原因：mode-b 階段沒有 production 累積資料，跑 dev test 一次只會有 1 個 run。
  - **未來如果累積 ≥ 7 天 W6 run**，可寫 `scripts/w6_health_check.py` 把 8 個指標跑出來、按上方決策矩陣自動標 PASS/FAIL。
- 下一步：
  - **W6 本輪優化告一段落**——三項任務都做完、tests 通過、體檢 checklist 文件化。
  - **延後到「資料說話」再動的事項**：
    - 寫 `scripts/w6_health_check.py`（需要先累積 dev test 資料 ≥ 7 個 run）。
    - 加 W6 guard rails（需要先觀察 monitoring 異常模式）。
    - 改 W6 prompt 結構（需要先看哪幾個欄位指標異常）。
  - **可選下一輪**：
    - W8 Briefing thread context 注入 prompt（之前已分析過、未動工）——這是「斷頭」最明顯的一段，補上之後 podcast 才能真的「呼應背景、不重複」。
    - W7 thread cosine 門檻調整（30 天 thread match 用 0.76 可能太嚴）。

## 2026/05/15 07:58 - Claude 更新
- 更新者：Claude
- 進度：完成 W7 Thread Phase Tree + read-only viewer 第一版（解 thread 內部沒有結構、W4 same_thread 證據被丟、W5 importance 滲透 W7 排序三個問題）。
- 設計脈絡：
  - 對應使用者需求「想看故事**發展到哪一階段**、**怎麼發展**、**新的軸是什麼**」。
  - 之前 W7 的 thread 是平鋪 signal 包，沒有「軸 / 階段」這層抽象——briefing/podcast 只能流水帳，無法說「IPO 衝突今天有新進展」。
  - 計劃書放在 `~/.claude/plans/recursive-coalescing-dragon.md`（含 Codex plan 整合對照）。
- 新概念：**Phase**（thread 內部的敘事軸 / 階段）
  - 一條 thread 一週 2–5 個 phase；phase 有自己的 status（emerging / active / dormant / resolved）、parent_phase_id、centroid。
  - signals 不再只掛 thread，而是掛在 phase 之下；新軸是第一級事件（status=emerging + parent_phase_id 指出從哪分出來）。
- 行為變更（按執行順序）：
  - **W4 同 prompt、不加成本**：`_apply_adjudication_to_signal()` 把 same_event / same_thread / different_event 的 decision / confidence / rationale / candidate_thread_id 寫到 signal（之前都被丟掉）。W7 直接消費。
  - **W7 candidate sort 改用 composite priority**：取代 `(importance_score, cluster_size, match_score)`，新 key `_story_priority_key` 順序為 `(W4 evidence > recency > signal_status > publisher_tier > importance_bucket)`。importance 從主導變 tie-breaker bucket。
  - **W7 lazy backfill**：thread 第一次被 W7 碰到時自動建一個 seed phase（title=thread.title, signal_ids=thread.signal_ids），無 LLM 成本，無一次性 migration。
  - **W7 phase 分派三層**：
    1. W4 evidence shortcut（adjudication_decision in {same_event, same_thread} → 配最近 phase，不打 LLM）
    2. Cosine pre-filter（vs phase.event_centroid，≥ 0.82 → 直接掛，不打 LLM）
    3. LLM batch（每條 thread 內模糊 signals 一次 Flash call）
  - **5-decision 詞彙**（取代簡單 phase_id | NEW）：
    - `continues_core` — 延續既有 phase
    - `new_axis` — 開新軸，parent_phase_id 指出 fork 點，status=emerging
    - `background_repeat` — 重複舊內容，掛回去但 `signal.is_background_repeat=true`、不前進 phase
    - `different_thread` — 疑似 thread 掛錯，flag for review（rationale=`thread_mismatch_suspected:...`）
    - `duplicate_suspected` — 疑似 W4 漏抓的重複，flag（rationale=`duplicate_suspected:...`）
  - **Phase status transitions**：emerging→active 在 signal_count ≥ 2；active→dormant 在 7 天無新 signal；resolved 只由 LLM 明示。
  - **新 viewer**（FastAPI 內 serve）：`GET /viewer/` Cytoscape.js phase tree（pinned 3.30.2 CDN）。左側 thread 列表（podcast 3+ 天沒覆蓋會 dim、mismatch flag 會 badge），中間 phase 樹（color=status, size=signal_count, edges=parent→child），右側 panel 顯示 phase 細節 + signals + W4 chip。「show W5 influence」toggle 可選看 importance 對 node opacity 的影響（**設計上 importance NOT 預設影響任何視覺權重——刻意避免 importance leak**）。
- 影響檔案：
  - **新增**：
    - app/api/routes_threads.py（GET /api/threads, GET /api/threads/{id}）
    - app/static/viewer/index.html
    - app/static/viewer/viewer.js
    - app/static/viewer/viewer.css
    - tests/test_rss_story_thread_phases.py（14 tests）
    - tests/test_threads_api.py（4 tests，含 viewer.html 200 check）
    - tests/test_signal_matching_adjudication_persistence.py（3 tests）
  - **修改**：
    - app/models/signal.py
      - 新增 `RssThreadPhase` model（19 欄位，含 today_delta / continuation_prompt_hint / do_not_repeat_points 預留給 W8/W9 之後消費）
      - `RssSignal` 新增 `phase_id`、`is_background_repeat`、4 個 W4 adjudication 欄位
      - `RssStoryThread` 新增 `phases_initialized_at`
    - app/services/rss_signal_matching_service.py
      - 新增 `_apply_adjudication_to_signal()` helper
      - 三條 adjudication 路徑（same_event / same_thread / different_event）都呼叫 helper
    - app/services/rss_story_thread_service.py
      - 新增 `_story_priority_key`、`_bootstrap_seed_phase_if_needed`、`_assign_phases_for_thread`、`_route_phase_decision`、`_assign_phase_status`、`_llm_assign_phases`、`_create_phase`、`_apply_signal_to_phase`、`_closest_phase_by_centroid`、`_best_phase_by_event_cosine`、`_most_recent_active_phase`
      - `_consolidate_daily_inner` 加入 phase pass（在既有 thread 配對之後、upsert 之前）；return dict 增加 9 個 phase 觀測 counter
    - app/clients/firestore_client.py
      - 新增 `upsert_thread_phases`、`list_phases_for_thread`、`list_phases_for_threads`（用於 viewer 批次 read）、`get_story_thread_by_id`、`list_signals_by_ids`
    - app/core/config.py
      - 新增 `PHASE_ASSIGNMENT_MODEL_GEMINI=gemini-2.5-flash`、`PHASE_COSINE_AUTO_THRESHOLD=0.82`、`PHASE_DORMANT_AFTER_DAYS=7`
    - app/main.py
      - 註冊 routes_threads router
      - mount /viewer 到 app/static/viewer/（StaticFiles, html=True）
    - tests/test_signal_intelligence_v2.py
      - `FakeStoryFirestore` 加上 `list_phases_for_threads` / `list_phases_for_thread` / `upsert_thread_phases` stubs（保既有 2 個 thread tests 綠燈）
    - docs/AI-log.md
- 設計取捨（為何這樣不那樣）：
  - **Phase-as-node 而非 Signal-as-node**：Codex 草案用 1 signal 1 node 加上 `development_axes: list[str]`，但 axes 沒 lifecycle、一週後 50 個 signal 變雜訊樹。Phase-as-node 把「軸」升為一級物件，signals 是證據。
  - **獨立 `rss_thread_phases` collection 而非塞進 thread doc**：Firestore 文件 1MB 上限，熱門 thread 累積 phase + signal_ids 會撐爆。獨立 collection 也讓 viewer 批次讀更便宜。
  - **Flash 不上 Pro**：thread-level 判斷搭 batched context，Flash 夠用；保留 `phase_llm_invalid_id_count` 觀測——若品質差再升。
  - **Cosine pre-filter 0.82 + W4 evidence shortcut**：避免每個 signal 都打 LLM。預估 30–60 個 importance≥60 signals 中 70%+ 走 heuristic 路徑，每天剩 10–30 LLM calls（每 thread 1 次）。
  - **Lazy backfill 而非一次性 migration**：W7 第一次碰到的 thread 自動建種子 phase。零 API 成本、無遷移風險、之後自然分支。
  - **Viewer 預設 size=signal_count, NOT importance**：刻意避免 W5 leak 進視覺。importance 透過 toggle 顯示為 opacity——使用者要看才看。
  - **Read-only viewer**：v1 不做 merge / move / delete。phase 錯了讓它 dormant、新 phase 自然出現；不引入 mutating endpoint 與 auth 複雜度。
- 觀測新欄位（從 W7 response / Consolidate_Log 撈）：
  - `phases_upserted` — 本次寫入 phase 數
  - `phases_created` — 本次新開的 phase（含 new_axis 與 fallback auto-create）
  - `phases_advanced` — emerging→active 數
  - `phase_heuristic_assignments` — cosine ≥ 0.82 的 signal 數（省 LLM 的）
  - `phase_w4_evidence_assignments` — W4 same_thread shortcut 命中數（W4 ROI 觀測）
  - `phase_llm_calls` — 實際 LLM batch call 數（≈ 有模糊 signal 的 thread 數）
  - `phase_llm_invalid_id_count` — LLM hallucinate phase_id 次數（Flash 品質紅燈）
  - `background_repeat_count` — 被標 background_repeat 的 signal 數
  - `thread_mismatch_flagged_count` — 被疑似 thread 掛錯的 signal 數（W7 對 W4 的反向回饋）
  - `duplicate_suspected_count` — 疑似 W4 漏抓重複的 signal 數
- 測試/驗證：
  - `.venv/bin/python -m unittest discover -s tests` → **121 tests 全綠**（既有 100 tests + 新增 21 tests，無回退）。
  - `.venv/bin/python -c "from app.main import app; ..."` → 啟動成功，路由含 `/api/threads`、`/api/threads/{thread_id}`、`/viewer`。
  - 既有 `test_consolidation_*` 兩個 thread service 測試在加完 stub 後仍通過——確認 phase pass 不破壞舊行為。
- W7 健康度檢查清單（之後跑進 production 後留意）：
  - **檢查頻率**：每週看一次 `phase_*` counter。
  - **觸發行動**：
    - `phase_llm_invalid_id_count / phase_llm_calls > 5%` → Flash 不夠，升 Pro（改 `PHASE_ASSIGNMENT_MODEL_GEMINI`）
    - `phase_w4_evidence_assignments` 長期為 0 → W4 adjudication 觸發率太低，回頭看 W4 trigger 條件
    - `thread_mismatch_flagged_count` 持續高 → W7 thread matching 0.76 門檻太鬆，或 thread centroid 太黏
    - `duplicate_suspected_count` 持續高 → W4 漏抓太多，回頭看 hard gate / cosine 門檻
    - `phases_created` 連續 0 → 沒有任何新軸被偵測，可能 LLM prompt 過度保守，或 cosine 0.82 太嚴
  - **沒有像 W5/W6 那樣的專用 audit script**——等累積 ≥ 7 天 W7 run 後再寫 `scripts/w7_phase_audit.py`。
- 對齊現有約定：
  - 沿用 `start_workflow_run` / `complete_workflow_run` idempotency（既有 W7 已包），phase pass 在 wrap 內，retry 同 run_bucket 不會重打。
  - 沿用 `signal_v2_utils.cosine_similarity / decay_centroid / utc_now_iso / short_hash`，centroid 衰減用同一個 `CENTROID_DECAY=0.85`（不另開設定，避免漂移）。
  - 沿用 `gemini_client.generate_json` 同 retry / 錯誤處理。
  - 既有 W7 refine 邏輯**保留不動**——它在 phase pass 之前跑，跟 phase 互不干擾。
- 下一步（**v1 未做、刻意延後**）：
  - W8 briefing / W9 podcast 還是讀 thread-level `today_delta` 與 `continuation_prompt_hint`——phase-level 的同名欄位已預留 schema 但未串到 prompt。等 phase 品質驗證一週後再接。
  - 不對 `duplicate_suspected` 做自動 merge——v1 只 flag。等人工檢查 1–2 週決定 auto 規則。
  - viewer 編輯（merge / move / mark-resolved）——phase 錯了讓它 dormant、新 phase 自然出現即可。
  - 等累積 production 資料後考慮：phase fork 是否常常該回 W4 重判（同層 cross-validation）。
  - rss_ai_research_plan.md 同步更新 §7、§3、§4、§8、§13、Glossary。

## 2026/05/15 09:55 - Claude 更新
- 更新者：Claude
- 進度：修 Codex code review 指出的 3 個 P1 真 bug + 1 個更隱蔽的相關 bug。Phase tree 上線後 12 小時內發現的問題，全部在進 production 前修掉。
- 修復項目：
  - **P1.2 — phase 狀態與 parent 不會被持久化**：`_assign_phases_for_thread` 最後只回傳 `touched` phases；status sweep 雖然會跑全部 phase 但 dormant 轉換不在 touched，所以下次 W7 跑又看到 active、永遠 dormant 不了。同樣 `new_axis` mutate 的 parent.child_phase_ids 也只在記憶體有效。**修法**：(a) status 轉換實際發生時 → `touched.add(phase.phase_id)`；(b) `_route_phase_decision(... touched)` 把 touched 接進去，new_axis 內加 `touched.add(parent.phase_id)`。
  - **P1.3 — phase LLM token 完全不記**：`_llm_assign_phases` 用 `payload, _, _ = gemini_client.generate_json(...)` 把 token usage 丟掉，新增的 phase 成本對外完全不可見。**修法**：函數簽章改 return `tuple[dict, int, int]`；caller 把 input/output tokens 加進 `phase_stats`；`_consolidate_daily_inner` return dict 新增 `phase_llm_input_tokens` / `phase_llm_output_tokens`。預先存在的 `llm_cost_utils.py` Gemini 價格 bug 不在這次範圍。
  - **P2（Codex 提）+ 我自己挖出的更深問題 — W4 shortcut 沒檢查 candidate_thread_id**：原本 shortcut 只看 `signal.adjudication_decision in {same_event, same_thread}` 就觸發，完全忽略 W4 是針對「哪一條 thread」做的判斷。場景：W4 認為 signal 屬於 thread A 的 phase，但 W7 的 thread matching 把它分到 thread B（W7 用 thread centroid、W4 用 signal centroid，兩者可能不一致）→ shortcut 仍觸發，把 signal 塞進 thread B 裡 cosine 最近的 phase，靜默錯掛。Codex 只指出「best_signal 沒 thread_id 時 metadata 沒用」，但更嚴重的是「即使有 thread_id，也可能不是當前 thread」。**修法**：shortcut 加 guard `signal.adjudication_candidate_thread_id == thread.thread_id`，不符就 fall through 到 cosine / LLM 路徑。順便解決 Codex 提的 None case（None ≠ 任何 thread_id，所以一樣 fall through）。
  - **P1.1（Codex 提）暫不動**：「W7 thread matching 沒真正升級——`different_thread` 只 flag 不重新分派」是 v1 計劃裡明寫的範圍。Codex 對事實的描述正確（觀測 ≠ 解決），但這是刻意取捨。建議先觀察 1–2 週 `thread_mismatch_flagged_count`，再決定是否做自動再分派。
- 影響檔案：
  - app/services/rss_story_thread_service.py
    - `_assign_phases_for_thread`：status sweep 加 `if before != phase.status: touched.add(...)`；LLM batch 接 in/out tokens 進 stats
    - `_route_phase_decision`：新增 `touched: set[str]` 參數；`new_axis` 內 `touched.add(parent.phase_id)`
    - `_llm_assign_phases`：簽章改回 `tuple[dict, int, int]`，返回 token usage
    - W4 evidence shortcut 加 `signal.adjudication_candidate_thread_id == thread.thread_id` guard
    - `_consolidate_daily_inner` return dict 新增 `phase_llm_input_tokens` / `phase_llm_output_tokens`
  - tests/test_rss_story_thread_phases.py — 新增 6 tests（3 個 fix 各對應 1–3 個 case）：
    - `TestPersistenceFixes.test_dormant_transition_returned_for_upsert`
    - `TestPersistenceFixes.test_new_axis_parent_added_to_returned_list`
    - `TestPhaseLLMTokenAccounting.test_llm_tokens_recorded_into_stats`
    - `TestW4EvidenceShortcutGuard.test_shortcut_fires_when_candidate_thread_matches`
    - `TestW4EvidenceShortcutGuard.test_shortcut_skipped_when_candidate_thread_differs`
    - `TestW4EvidenceShortcutGuard.test_shortcut_skipped_when_candidate_thread_id_is_none`
  - docs/AI-log.md
- 測試/驗證：
  - `.venv/bin/python -m unittest tests.test_rss_story_thread_phases -v` → 20/20 pass（14 既有 + 6 新）
  - `.venv/bin/python -m unittest discover -s tests` → **127/127 pass**（前一次 121 + 6 新；既有 thread / matching / API tests 全綠，無回退）
- Codex review 對應表：
  - P1.2 ✅ 修了
  - P1.3 ✅ 修了（新代碼部分；llm_cost_utils.py 預先存在 bug 範圍外）
  - P2 ✅ 修了，且發現比 Codex 描述更廣的問題（不只 None case，連 mismatched thread_id case 也是 bug）
  - P1.1 ⏸️ 觀察期；不算 bug，是 v1 範圍取捨
- 下一步：
  - 觀察 1–2 週 production W7 run，看 `phase_w4_evidence_assignments` / `thread_mismatch_flagged_count` / `phase_llm_input_tokens` 三個指標。
  - 如果 W4 shortcut 加 guard 後觸發率掉到接近 0，要回頭看是不是 W4 同時要把 `same_thread` decision 寫到 best_signal（讓未來其他 signal 能對到）——目前 W4 只寫到「新」signal 上。
  - 等 W4 thread mismatch 數據累積夠 → 評估 P1.1 是否要做（自動 thread 再分派）。

## 2026/05/15 13:35 - Claude 更新
- 更新者：Claude
- 進度：完成 W8 Daily Briefing 第一輪優化——把之前所有 W7 phase tree / thread / W4 adjudication 的成果**真正接到 briefing prompt**，並補上 retry-on-validation-failure。這是「斷頭」最明顯的一段（W6 收尾時自己標記過）。
- 設計脈絡：
  - W7 上線後寫好 `thread.known_background` / `thread.do_not_repeat_points` / `thread.continuation_prompt_hint` / phase tree / `signal.is_background_repeat` / `signal.adjudication_decision`，**但 W8 完全不讀**。等於 W7 算的東西丟掉一半。
  - W6 收尾的 next steps 已寫：「W8 Briefing thread context 注入 prompt——這是『斷頭』最明顯的一段，補上之後 podcast 才能真的『呼應背景、不重複』」。這次動工就是兌現。
  - W8 是 Pro 模型一天一次的最貴 call（≈$1.5/天），prompt 多餵 2–4× tokens 但月費只多 ~$15——可接受，換的是 podcast 真的有故事連續性。
- 行為變更：
  - **Signals 按 thread 分組餵 LLM**（之前是平鋪 80 個 signal 的 JSON array，LLM 要自己 re-discover thread 結構）。新結構：
    ```
    thread_groups: [
      {
        thread: {title, status, known_background, do_not_repeat_points, continuation_prompt_hint, today_delta, last_covered_in_podcast_at, ...},
        phases: [{phase_id, title, status, signal_count, parent_phase_id, novelty_reason, ...}],
        signals: [...同 thread 內的訊號 by importance desc],
      },
      ...
    ]
    ungrouped_signals: [...沒有 thread_id 的孤兒訊號]
    ```
    thread groups 排序：今天有非 background_repeat 訊號的優先，其次 max importance。
  - **`signal.is_background_repeat == true` 在 prompt 中有明確旗標**，prompt 規則告訴 LLM「**不要單獨開 section**，最多在既有 section 用一句話帶過」。`background_repeat_count` 在 prompt header 寫明確的數字。
  - **`adjudication_decision` 也帶進 prompt**：`different_thread` 要 LLM 謹慎、`duplicate_suspected` 不單獨開 section。
  - **Phase status 在 prompt 中可見**：`emerging` 標記新軸（今日真新進展、優先寫）、全 `dormant` 跳過。
  - **`do_not_repeat_points` 顯示在 thread context 裡**，prompt 規則明示「列出的內容禁止再寫」。
  - **`continuation_prompt_hint` 直接借用語感**，prompt 規則建議 section 開頭可直接用。
  - **retry-on-validation-failure**：`_generate_with_retry()` wrap `_call_briefing_model + _validate_briefing_payload`，第一次 raise ValueError 時：(a) 把錯誤摘要塞進 `retry_feedback` placeholder、(b) 重新 render prompt、(c) 再 call 一次。token 計入累積。兩次都失敗才 raise。**Pro 偶爾少欄位的 case 從整天沒 briefing 變成自動修復。**
- 影響檔案：
  - **修改**：
    - `app/services/rss_briefing_service.py`
      - 新增 `_build_thread_groups()` / `_thread_context()` / `_phase_summaries()`：從 Firestore 抓 thread + phase，按 thread 分組
      - `_signal_to_compact()` 加 `phase_id` / `is_background_repeat` / `adjudication_decision`
      - `_render_prompt()` 簽章加 `retry_feedback`，產出新 placeholder（`thread_groups_json` / `ungrouped_signals_json` / `thread_count` / `ungrouped_count` / `background_repeat_count` / `retry_feedback`）
      - 新增 `_generate_with_retry()`：1 次 retry，feedback 餵 LLM
      - `generate_daily_briefing()` 改用 `_generate_with_retry()`；token 累積跨 attempt
    - `app/prompts/editorial_briefing_v2.txt`
      - 完整重寫「連續性處理」段——8 條規則由 thread / phase 結構驅動（之前是 free-form「對比今昨」）
      - 輸入區塊改為 `thread_groups_json` + `ungrouped_signals_json` 兩塊，header 帶 thread 數 / ungrouped 數 / background_repeat 數
      - 頂部加 `{retry_feedback}` placeholder（第一次空字串，retry 時帶錯誤摘要）
    - `app/clients/firestore_client.py`
      - 新增 `list_story_threads_by_ids(thread_ids)` 批次 read（Firestore "in" 30/chunk）
    - `tests/test_rss_briefing_service.py`
      - `FakeFirestoreClient` 加 `list_story_threads_by_ids` / `list_phases_for_threads` stubs
      - 新增 5 tests：
        - `TestThreadContextInjection.test_thread_context_injected_into_prompt`
        - `TestThreadContextInjection.test_background_repeat_signal_count_surfaced`
        - `TestThreadContextInjection.test_orphan_signal_without_thread_goes_to_ungrouped`
        - `TestRetryOnValidationFailure.test_retry_succeeds_after_first_invalid_payload`
        - `TestRetryOnValidationFailure.test_two_failures_raises`
    - `docs/AI-log.md`
- 設計取捨：
  - **餵更多 tokens 而非過濾**：第一直覺是把 `is_background_repeat=true` 的 signal 從 candidate pool 過濾掉，但這樣 LLM 看不到「有重複報導」這個事實。決定**全送、明確旗標、規則告訴 LLM 怎麼處理**——LLM 可以決定要不要在 section 帶一句「同主題後續報導」。
  - **保留 ungrouped bucket**：完全沒 thread_id 的訊號（剛產生、還沒進 W7）放在獨立陣列，prompt 規則告訴 LLM「全新主題、完整鋪陳」。不強制分組——強制會誤導 LLM。
  - **retry feedback 用文字而非結構**：第二次 prompt 開頭加「⚠️ 上一次嘗試失敗：missing overview」這種人話，比塞 JSON schema 給 LLM 更有效。
  - **不換 model on retry**：兩次都用同一個 model（Pro 或 OpenAI）。換 model 變數太多；目前先觀察單 model 兩次嘗試的成功率，若仍常失敗再加 fallback。
  - **不改 candidate selection（importance ≥ 60、limit 80）**：這次只動 prompt 注入；selection 邏輯改變影響面更大，留下一輪。
- 觀測指標（未來該看）：
  - `briefing.input_tokens` — thread context 接入後預期 +20% ~+50%；超過 +100% 要回頭看 thread_context 字數截斷夠不夠
  - `briefing.output_tokens` — 應該大致持平或微降（LLM 不用 re-discover thread）
  - 第二次 attempt 觸發率（暫時只在 log warning 看）——若 production 一週都 0 次，retry 是純保險不傷成本
  - 人工 sample：podcast 是否真的有「延續性」語感（檢查 is_continuation: true 的 section 是否真的只寫 delta、沒重講背景）
- 對齊現有約定：
  - 沿用 `_call_briefing_model` 既有 provider switch（OpenAI / Gemini）
  - 沿用 `_validate_briefing_payload` 既有 schema 驗證
  - 沿用 `firestore_client.list_phases_for_threads`（W7 已加）與 `signal_v2_utils.importance_bucket`
  - prompt 4 大主題 + 順序 + 寫作原則完全保留——只動連續性段與輸入區塊
- 測試/驗證：
  - `.venv/bin/python -m unittest tests.test_rss_briefing_service -v` → 10/10 pass（5 既有 + 5 新）
  - `.venv/bin/python -m unittest discover -s tests` → **132/132 pass**（127 → 132，無回退）
- 下一步（**v1 未做、待下一輪**）：
  - **W9 podcast script**：同樣的 thread context 注入要在 podcast prompt 也做一次（podcast script 是 podcast 真的講出來的語言，比 briefing 更需要避免重講）
  - **`adjudication_decision == "duplicate_suspected"` 的 hard filter**：v1 還是給 LLM 看、讓它判；觀察一週若 LLM 都老實不單獨開 section 就移到 hard filter
  - **selection 邏輯重看**：目前 importance ≥ 60 + limit 80 沒考慮 thread 平衡（一條熱門 thread 可能佔 20 個 signal），future 可以做「per-thread cap」確保多元
  - **W4 把 same_thread decision 寫到 best_signal**：上次 P2 修完發現 W4 只把 decision 寫到「新」signal 上，best_signal（已存在的）不會被回寫。如果想讓未來的 signal 也能用上這條 evidence，要回 W4 加。低優先，等觀測數據說話。
  - rss_ai_research_plan.md 同步更新 §8。

## 2026/05/15 23:26 - Claude 更新
- 更新者：Claude
- 進度：修 Codex 對 W8 第一輪的兩個 P 級 review。一個是欄位對齊 bug、一個是觀測缺失。
- 修復項目：
  - **P1（Codex 提）— 欄位對齊 bug：W7 phase flags 寫在 `adjudication_rationale` 文字內，但 W8 prompt 規則寫的是 `adjudication_decision == "different_thread" / "duplicate_suspected"`。**
    - W4 的 `adjudication_decision` 欄位只有 `same_event / same_thread / different_event` 三種值——**從來不會是 `different_thread` 或 `duplicate_suspected`**。
    - W7 的 phase decisions（`different_thread` / `duplicate_suspected`）寫在 `signal.adjudication_rationale` 字串開頭（`thread_mismatch_suspected: ...` / `duplicate_suspected:...`）。
    - 結果：之前 prompt 兩條規則靜默失效，W8 LLM 收不到 W7 的這些訊號。
    - **修法**：
      - `_signal_to_compact()` 加 `_phase_flags_from_rationale()` helper，從 rationale prefix 派生 `thread_mismatch_suspected: bool` / `duplicate_suspected: bool` 兩個顯式 boolean
      - compact 同時輸出 `adjudication_rationale`（截斷 200 字）讓 LLM 看上下文
      - prompt 規則 7、8 改用新 boolean 欄位名，並加註解說明 `adjudication_decision`（W4）與 phase flags（W7）的差別
  - **P2（Codex 提）— retry_count 算出但沒持久化或回傳**：
    - `_generate_with_retry()` 回傳 retry_count，但 `generate_daily_briefing` 拿到後沒用——production 完全看不到 retry 觸發率，沒辦法驗證上輪 W8 改動聲明的「retry 是純保險」假設。
    - **修法**：
      - `validated["signal_pool_health"]["briefing_retry_count"] = retry_count` → 寫進 Firestore 持久化（可日後 retroactive 分析）
      - `result["briefing_retry_count"] = retry_count` → 寫進 API response（n8n 可記到 Briefing_Log）
- 影響檔案：
  - **修改**：
    - `app/services/rss_briefing_service.py`
      - 新增 `_phase_flags_from_rationale(rationale) -> dict[str, bool]`
      - `_signal_to_compact` 加 4 個欄位：`adjudication_rationale`、`thread_mismatch_suspected`、`duplicate_suspected`，`adjudication_decision` 加註解標明這是 W4 欄位
      - `generate_daily_briefing` 加 2 行：`signal_pool_health["briefing_retry_count"] = retry_count` 與 `result["briefing_retry_count"] = retry_count`
    - `app/prompts/editorial_briefing_v2.txt`
      - 規則 7 改 `thread_mismatch_suspected == true`（W7 phase 判斷）
      - 規則 8 改 `duplicate_suspected == true`（W7 phase 判斷）+ 提示 LLM 看 `adjudication_rationale` 找原始 signal id
      - 加 `> 註：` 段落明示 W4 `adjudication_decision` 與 W7 phase flags 的差別
    - `tests/test_rss_briefing_service.py`
      - 新增 `TestPhaseFlagDerivation`（4 tests）：thread_mismatch / duplicate / W4-only rationale / 完整 prompt 可見
      - 新增 `TestRetryCountObservability`（2 tests）：retry_count=0 first-call success / retry_count=1 first-call fail
    - `docs/AI-log.md`
- 設計取捨：
  - **derived booleans vs 改 schema**：本來可以加 `RssSignal.thread_mismatch_suspected` 真實欄位，但 (a) rationale 改了 boolean 會 stale (b) W7 已經寫好 rationale 不想雙寫 → **compute-on-read 最穩**
  - **同時保留 `adjudication_decision` 欄位給 LLM**：因為 W4 的 `same_thread` / `same_event` 仍然是有用 signal（強化 `is_continuation` 判斷），prompt 註解說明用法
  - **retry_count 寫兩份（result + signal_pool_health）**：result 給 n8n 即時看；signal_pool_health 在 Firestore 永久保存——retroactive 分析需要
- 對齊現有約定：
  - 沿用既有 `adjudication_rationale` 文字，無需動 W7 寫入路徑
  - 沿用 `signal_pool_health` dict 為 free-form metadata 容器（既有 `total_judged` / `main_themes` 等也是這樣）
- 測試/驗證：
  - `.venv/bin/python -m unittest tests.test_rss_briefing_service -v` → **16/16 pass**（10 → 16，+6 新）
  - `.venv/bin/python -m unittest discover -s tests` → **138/138 pass**（132 → 138，無回退）
- Codex review 對應表：
  - P1 ✅ 修了，並且把 prompt 註解強化 `adjudication_decision` vs phase flags 區別
  - P2 ✅ 修了，retry_count 進 result + signal_pool_health 兩份
- 觀測指標（修完後可以開始追的）：
  - `signal_pool_health.briefing_retry_count`：1 週若都 0 → retry 是純保險（符合假設）；若常 1 → LLM 品質有問題、回頭看 prompt
  - `compact["thread_mismatch_suspected"] / duplicate_suspected = true` 的 signal 數：之前根本沒進 prompt，現在開始 LLM 才會真的處理；觀察一週看 LLM 是否真的遵守規則 7、8
- 下一步維持上次 W8 entry 的 next steps（W9 podcast script、selection 平衡、`duplicate_suspected` hard filter 待觀察）。

## 2026/05/15 23:58 - Claude 更新
- 更新者：Claude
- 進度：完成 W9 Podcast Script 第一輪優化。比 W8 更深一層——除了同樣注入 thread / phase context，**還載入「昨日實際播出的 podcast script」**作為重複防止的真正基準。這是 W9 獨有、比 W8 更嚴重的問題。
- 設計脈絡：
  - W8 上一輪修完後，AI-log 標記下一步：「W9 同樣的 thread context 注入要做一次（podcast 是真的講出來的語言，比 briefing 更需要避免重講）」。
  - 探索 W9 service 後發現**比 W8 更慘**：W9 連「昨日 podcast script」都沒載入，只看「昨日 briefing 摘要」——但聽眾追蹤的是「昨天 podcast 講了什麼」，不是「昨天 briefing 寫了什麼」。Briefing 寫 10 個 section、podcast 只挑 3–5 個 deep dive，W9 完全不知道哪些已經播過。
  - 修法照 W8 同模式 + 一個 W9 獨有步驟：(a) 載入昨日 podcast script、(b) thread + phase context 注入、(c) phase flags 派生、(d) retry-on-validation-failure。
- 行為變更：
  - **新增 `_yesterday_podcast_summary(today_date)`**：從 `rss_podcast_scripts` 抓 briefing_date 嚴格小於 today 的最新一篇，輸出 episode_title + themes_covered + themes_skipped + 各 segment 標題與前 200 字。**這是 prompt 中重複防止的真正基準**。
  - **新增 `_build_thread_groups_for_briefing(briefing)`**：從 briefing 的 referenced_signal_ids（top_changes + sections）反查 signals → 反查 threads → 反查 phases，按 thread 分組，shape 與 W8 完全一樣。
  - **新增 `_signal_for_podcast(signal)`**：podcast-specific compact 形式，含 W7 phase flags（`thread_mismatch_suspected` / `duplicate_suspected`）。
  - **`_render_prompt(briefing, retry_feedback="")` 改寫**：6 個新 placeholder（`yesterday_podcast_summary` / `thread_groups_json` / `ungrouped_signals_json` / `thread_count` / `ungrouped_count` / `background_repeat_count` / `retry_feedback`）。
  - **新增 `_generate_script_with_retry(briefing)`**：1 次 retry，feedback 餵錯誤摘要回 LLM；token 跨 attempt 累積；retry_count 寫進 `validated["validation_warnings"]` 持久化（沿用既有 free-form 文字欄位，不動 schema）+ `result["script_retry_count"]` 給 API response。
  - **`generate_daily_podcast_script` 改用 retry helper**。
  - **共用 helper 抽出**：W8 的 `_phase_flags_from_rationale` 移到 `signal_v2_utils.phase_flags_from_rationale`，W8/W9 共用，避免重複。
- Prompt 大改寫（[podcast_script_v1.txt](app/prompts/podcast_script_v1.txt)）：
  - **新增「跨日連續性」段落（8 條規則）**——由 thread / phase 結構驅動，podcast 語感版本（口語）。第 1 條最關鍵：「聽眾追蹤的是『昨天 podcast 講了什麼』，不是『昨天 briefing 寫了什麼』」。
  - **明示優先序**：當 `yesterday_podcast_summary` 與 `briefing.is_continuation` 衝突時 → **以 podcast 摘要為準**。
  - **輸入區塊重組**：5 塊（today briefing / yesterday podcast 摘要 / thread_groups / ungrouped / yesterday briefing 摘要——後者降為次要參考）。
  - 頂部加 `{retry_feedback}` placeholder。
- 影響檔案：
  - **修改**：
    - `app/services/signal_v2_utils.py` — 加 `phase_flags_from_rationale(rationale) -> dict[str, bool]` 共用 helper
    - `app/services/rss_briefing_service.py` — import 共用 helper、刪掉本地 `_phase_flags_from_rationale`
    - `app/services/rss_podcast_script_service.py`
      - import 共用 helper
      - 新增 `_yesterday_podcast_summary` / `_build_thread_groups_for_briefing` / `_thread_context_for_podcast` / `_phase_summaries_for_podcast` / `_signal_for_podcast` / `_generate_script_with_retry`
      - `_render_prompt` 簽章改 `(briefing, retry_feedback="")`，產出 6 個新 placeholder
      - `generate_daily_podcast_script` 改用 retry helper、retry_count 寫進 warnings + result
    - `app/prompts/podcast_script_v1.txt`
      - 新增頂部 `{retry_feedback}`
      - 「跨日連續性」段重寫成 8 條 thread / phase 結構規則（podcast 語感）
      - 「輸入資料」段改為 5 塊（多了 yesterday podcast / thread_groups / ungrouped）
    - `tests/test_rss_podcast_script_service.py` — 新增 `FakeFirestore` + 8 tests（thread injection / phase flags / background_repeat count / yesterday podcast loading / 同日跳過 / 完整 prompt / retry 成功 / retry 失敗）
    - `docs/AI-log.md`
- 設計取捨：
  - **「昨日 podcast」優先於「昨日 briefing」**——這是 W9 獨有最重要的設計決定。Briefing 是計劃，podcast 是實際輸出，**重複判斷必須以實際輸出為基準**。
  - **complete script 不放進 prompt**——只放 segment 標題 + 前 200 字。理由：(a) 完整 script ≈ 7000 字，餵進 prompt 會吃掉大量 token (b) LLM 不需要 verbatim，知道「主題與切入角度」就夠判斷重複。
  - **retry_count 寫進 `validation_warnings` 而非新欄位**——這個 list 已經是 free-form 文字容器，加一個 `script_retry_count=N` 字串最省事，不用改 RssPodcastScript schema。
  - **不引入 selection 邏輯（briefing 怎麼選 signal）改變**——W9 完全照 briefing 的 referenced_signal_ids 反查，不自己挑。把 W9 維持為「翻譯 + 重組」角色，不做雙重 editorial decision。
  - **共用 helper 移到 signal_v2_utils 而非 service 互相 import**——避免 W8/W9 service-level 互相依賴；helper 純 string parse、放工具層最自然。
- 對齊現有約定：
  - 沿用 W8 已建好的 `firestore_client.list_signals_by_ids` / `list_story_threads_by_ids` / `list_phases_for_threads`（無新加 Firestore 函數）
  - 沿用 `list_recent_podcast_scripts(limit=5)`（W7 podcast service 已存在）
  - 沿用 `_call_script_model` / `_validate_script_payload` 既有路徑
  - retry pattern 與 W8 一模一樣（同樣 `for attempt in range(2)` / `last_error` / `retry_feedback` 結構）
- 測試/驗證：
  - `.venv/bin/python -m unittest tests.test_rss_podcast_script_service -v` → **11/11 pass**（3 既有 + 8 新）
  - `.venv/bin/python -m unittest tests.test_rss_briefing_service` → 16/16 pass（共用 helper refactor 不破壞 W8）
  - `.venv/bin/python -m unittest discover -s tests` → **146/146 pass**（138 → 146，無回退）
- 觀測指標（修完後可以開始追的）：
  - `validation_warnings` 內 `script_retry_count=N` 出現次數：1 週若 0 → retry 純保險；若常 1 → prompt 品質問題
  - 人工 sample：podcast 是否真的不重複講昨天講過的東西（找昨日 themes_covered 裡的主題，看今日 script 對該主題開頭是否用「延續⋯⋯今天的新變化是」語感、有沒有重講背景）
  - 新可觀測：podcast input_tokens 預期 +30–50%（thread context + 昨日 podcast）；output_tokens 應持平或微降
- W7→W8→W9 三層連續性現況：
  - W7 寫 thread / phase 結構與 do_not_repeat_points → ✅ done
  - W8 讀 W7 結構，prompt 規則 8 條，retry → ✅ done（5/15 上輪）
  - W9 讀 W7 結構 + W8 已標好的 is_continuation + 昨日實際 podcast，prompt 規則 8 條 + 「昨日 podcast 優先於 briefing」明示，retry → ✅ done（本輪）
  - **整條 pipeline 從原始 RSS item 到 podcast 朗讀，故事連續性的訊號不再被任何一層丟掉**。
- 下一步：
  - **觀察 1–2 週**：W7 phase counter / W8 retry_count + thread_mismatch / W9 retry_count + 人工 sample podcast 重複度
  - **selection 平衡**（W8 提過、未動）：briefing 80 signal 限制沒考慮 thread 平衡，可能一條熱門 thread 佔 20 個 signal 擠掉小主題
  - **`duplicate_suspected` 自動 merge**：累積 1–2 週人工觀察後決定要不要做 hard filter
  - **W4 把 same_thread decision 寫到 best_signal**：上輪 P2 修完後留的 follow-up，低優先
  - rss_ai_research_plan.md §9 同步更新

## 2026/05/16 00:13 - Claude 更新
- 更新者：Claude
- 進度：修 Codex 對 W9 第一輪的兩個 P 級 review。一個是**全系統**的成本報表 bug、一個是 W9 lookup 邊界 case。
- 修復項目：
  - **P1（Codex 提）— `compute_llm_cost` 1000× 放大 bug**：
    - `llm_cost_utils.py` 把公開單價 `1.25`（這實際是 USD/1M tokens）寫成 `1.25 / 1000`，再乘上 raw token count → 等於把所有 cost 報告放大 1000 倍。
    - 實測：Pro 20k input + 8k output 之前報 $105，正確應該是 ~$0.105。
    - **同個 file docstring 還寫「per 1k tokens」與實際算法不符**——文檔誤導。
    - **這影響 W5 / W6 / W8 / W9 全部成本報表**——不只是這次 W9 改動。research plan §5 之前估 $98/月可能整體都被高估、或在我前面驗證 W9 prompt token 增加時做出錯誤判斷。
    - **修法**：
      - 重寫 `MODEL_PRICING` 用 verbatim 公開單價（USD per 1M tokens），不在表中做數學
      - 加 `PRICE_DIVISOR = 1_000_000` 常數
      - `compute_llm_cost` 改 `(input_tokens / PRICE_DIVISOR) * p["input"] + ...`
      - docstring 大幅改寫，明標歷史 bug
      - 新增 `tests/test_llm_cost_utils.py`（7 tests）——含 Codex 給的 20k+8k=$0.105 case 作為 regression 永久封印
  - **P2（Codex 提）— `_yesterday_podcast_summary` lookup 兩個邊界**：
    - **同日 reruns 擠掉昨日**：`list_recent_podcast_scripts(limit=5)` 按 `generated_at` desc 排序，今日手動 rerun ≥ 5 次 → 5 個 slot 全是今日 doc，昨日掉出窗口 → fallback 「無 podcast 紀錄」。我**之前 todo list 寫了「add get_latest_podcast_script_before helper」、結果沒實作就 mark complete**，直接踩這個坑。
    - **跳播日誤標**：若昨日無 podcast 但前天有，舊 code 仍把前天標為「昨日 podcast」。
    - **修法**：
      - `firestore_client.get_latest_podcast_script_before(briefing_date)`：用 `where("briefing_date", "<", date)` + `order_by("briefing_date" desc)`，再用 `generated_at` 對同日 reruns 二次排序取最新
      - service 函數改名 `_yesterday_podcast_summary` → `_previous_podcast_summary`（保留舊名 alias 給內部 call）
      - prompt placeholder 改名 `yesterday_podcast_summary` → `previous_podcast_summary`
      - 文案全面改「昨日」→「上一集」並加註「可能是昨日、也可能跨過跳播日，依 `上一集日期` 為準」
      - LLM 規則 1 改寫對「上一集 vs 昨日 briefing」優先序更明確
- 影響檔案：
  - **修改**：
    - `app/services/llm_cost_utils.py` — 整個 PRICING table 重寫、`PRICE_DIVISOR` 常數、`compute_llm_cost` 改用正確單位、docstring 重寫
    - `app/clients/firestore_client.py` — 新增 `get_latest_podcast_script_before(briefing_date)` 方法
    - `app/services/rss_podcast_script_service.py` — `_yesterday_podcast_summary` 改名 `_previous_podcast_summary` + 用新 firestore helper、保留 alias、輸出文案改「上一集日期」
    - `app/prompts/podcast_script_v1.txt` — 5 處文案改「昨日 podcast」→「上一集 podcast」、placeholder 改名、規則 1 描述更精確
    - `tests/test_rss_podcast_script_service.py` — `FakeFirestore` 加 `get_latest_podcast_script_before`、3 個既有 test 改用 `_previous_podcast_summary`、新增 2 個 P2 regression（5 同日 rerun 不擠掉昨日 / 多版本昨日取 generated_at 最新）
  - **新增**：
    - `tests/test_llm_cost_utils.py` — 7 tests，封印 P1 bug（含 Codex 給的具體 20k+8k case）
    - `docs/AI-log.md`
- 設計取捨：
  - **PRICING table 用 verbatim 公開單價 (per 1M)**：之前 `1.25 / 1000` 是試圖「per token」但算錯。新方案保留 `1.25` 原貌，由 `PRICE_DIVISOR` 全集中處理單位轉換——讓「對齊公開文件」變成 zero math。
  - **公開文件可能寫 per 1k 或 per 1M**：Anthropic / OpenAI / Google 都用 per 1M 了，docstring 與 PRICING 都統一 per 1M。
  - **`_previous_podcast_summary` vs `_yesterday_podcast_summary`**：保留舊名 alias `_yesterday_podcast_summary = _previous_podcast_summary` 避免 internal callers 突然斷掉；新 production code 用新名。
  - **「上一集」vs「昨日」用詞**：誠實——lookup 是「最近一次播出」，不保證昨日。Production 一週可能跳一兩天（系統故障、手動暫停）。Prompt 寫「上一集（可能是昨日、也可能跨過跳播日）」比「昨日」精確；LLM 看到 `上一集日期` 自己判斷時間距離。
  - **`get_latest_podcast_script_before` `limit=5` 而非 `limit=1`**：因為同 briefing_date 可能多個 doc（同日 reruns），`limit=5` 給足空間在 Python 端做二次排序拿真正最新；同日重跑 ≥ 5 次的 prior date 屬於極端情況，先觀察再說。
- 對齊現有約定：
  - 沿用 Firestore 既有 `where(filter=FieldFilter(...))` + `order_by` + `limit` 模式
  - 沿用 service-level helper underscore 命名
  - 沿用 alias 保留向後相容（與其他 service 處理方式一致）
- 測試/驗證：
  - `.venv/bin/python -m unittest tests.test_llm_cost_utils -v` → **7/7 pass**
  - `.venv/bin/python -m unittest tests.test_rss_podcast_script_service -v` → **13/13 pass**（11 既有 + 2 P2 regression）
  - `.venv/bin/python -m unittest discover -s tests` → **155/155 pass**（146 → 155，+9 new，無回退）
- Codex review 對應表：
  - P1 ✅ 修了，並加 test 永久封印；同時揭露歷史 cost 報表全部失真（W5/W6/W8/W9 之前都被放大 1000×）
  - P2 ✅ 修了，並順便修我自己 todo list 上次撒謊（「helper 已加」其實沒加）；prompt 文案也對齊現實
- 影響範圍與後續觀測：
  - **舊資料的 `cost_usd` 全部 ×1000 偏高**：`rss_briefings` / `rss_podcast_scripts` / `rss_judgement_runs` / `rss_business_impact_runs` 之前寫的 `cost_usd` 欄位都被放大。**未來 retroactive 報表要除 1000**，或者 GCP billing 才是真實值。**月費實際** ≈ 之前估算的 1/1000 + Pro 那一部分 = 應該 < $5/月（不是 research plan 估的 $98）。要不要回頭改 research plan §5 待你決定。
  - W9 prompt 多 30–50% token 的成本判斷之前失真，現在回到合理量級；觀察 1–2 週看實際 input_tokens 變化。
- 下一步：維持上輪 next steps；新增「retroactive 修舊 cost_usd 資料」與「research plan §5 月費估算重做」兩個待決策項目。

## 2026/05/16 09:05 - Claude 更新
- 更新者：Claude
- 進度：完成 log_summary 觀測層 + n8n setup doc 的 self-review，修 4 個發現的問題（2 P1 + 2 P2 + N3 helper tests）。
- 修復項目：
  - **P1.1 — W4 `[cost]` 行靜默漏掉 Pro adjudication 成本**：跟 Codex 上輪 W7 P1.3 同形 bug 又重演一次。`match_item_to_signal` 已 return `adjudication_input_tokens` / `adjudication_output_tokens`，但 W4 processor 完全沒 aggregate 進 run total，`[cost]` 行只報 embedding（便宜的部分）、漏掉 Pro adjudication（W4 真正的成本大頭）。**修法**：(a) processor loop 新增三個 counter（`adjudication_call_count` / `adjudication_input_tokens` / `adjudication_output_tokens`）；(b) result dict 新增 4 欄（前三 + `adjudication_cost_usd` + `total_cost_usd`）；(c) `_compose_signal_process_log_summary` `[cost]` 行改為 `embedding $x + adjudication $y (N 次 Pro call, ...) ，總成本 $z`；(d) 新增 regression test `test_adjudication_tokens_aggregated_into_cost`，mock review-band item + adjudication = same_event，斷言 `adjudication_cost_usd > 0` 與 `[cost]` 行含 "adjudication"。
  - **P1.2 — `n8n_setup.md` W2 `since_hours: 24` 與 research plan §1 `since_hours=2` 矛盾**：實作 default 是 24，但設計意圖是 2；用 24 等於每 30 分鐘抓 24 小時、99% items 被 dedupe 拒絕、白燒 Firestore reads。**修法**：n8n_setup.md 改 `since_hours: 2`，並加 inline 說明設計理由。
  - **P2.1 — `n8n_setup.md` `primary_count_1 / primary_count_2` 沒 per-W mapping**：之前只有 W9 在尾段提到取值；其他 7 個 W 完全沒寫，n8n 實作者要靠猜。**修法**：在 doc 加完整 mapping table（`Per-W Sheet Column Mapping`），明寫每個 W 的 duration / input_tokens / output_tokens / cost_usd / primary_count_1 / primary_count_2 取值路徑。同時提醒 W4 必須用 `total_cost_usd`（含 P1.1 修的 adjudication）而非 `embedding_cost_usd`。
  - **P2.2 — `n8n_setup.md` error branch 處理沒寫清楚**：原文只說「寫 status=failed」，但其他 6 個 service raise 後 n8n 拿到的是 HTTP 5xx、body 通常不含 `log_summary`；實作者沒 reference 不知道怎麼處理。**修法**：加 `Failure / Error Branch` 段落，含 (a) 明示「只有 W9 run-daily 在 raise 前寫 failure_summary」這個事實；(b) n8n Function node 範例 code（normalize HTTP 5xx → log_summary）；(c) 兩個取結構化 failure 的方案：被動（n8n 從 `workflow_runs` 撈，需要該 service 有走 `start_workflow_run`——已驗證 W4/W5_judge/W6/W7/W8/W9 都符合，只 W2/W5_verify 沒包）vs 主動（複製 W9 模式到其他 service）；建議先採方式 1。
  - **N3 — helper tests 偏薄**：上輪 cost util 1000× bug 證明簡單 helper 也會炸。**修法**：在 `tests/test_log_summary_utils.py` 加 5 個 test：`cost_text` 含 0 / None / 0.105（1000× bug regression）/ 1.0 / 0.000001 / garbage、`seconds_text` 三個 threshold case + garbage、`token_text` 正常 + None + garbage、`MAX_LOG_LINES` truncation 確認超過 6 行會截到 6。
- 影響檔案：
  - `app/services/rss_signal_processor_service.py`
    - 新增 import `from app.services.llm_cost_utils import compute_llm_cost`
    - loop 新增 3 個 adjudication counter
    - result dict 新增 4 欄（adjudication_call_count / adjudication_input_tokens / adjudication_output_tokens / adjudication_cost_usd / total_cost_usd）
    - `_compose_signal_process_log_summary` `[cost]` 行重寫
  - `tests/test_signal_intelligence_v2.py` — 新增 `test_adjudication_tokens_aggregated_into_cost`
  - `tests/test_log_summary_utils.py` — 新增 5 個 test
  - `docs/n8n_setup.md` — W2 since_hours 改 2；新增 `Per-W Sheet Column Mapping` table；新增 `Failure / Error Branch` 段落
  - `docs/AI-log.md`
- 設計取捨：
  - **W4 cost 加總而非 per-call 細項**：log_summary `[cost]` 一行字，給 n8n / 人類看「W4 今天總共花多少」即可。每 call adjudication 細項已經寫到 signal 上（meta dict），未來分析自己 query Firestore。
  - **`total_cost_usd` 取代 `embedding_cost_usd` 成為 doc-recommended cost 欄位**：保留舊 `embedding_cost_usd` 欄不刪，避免破壞既有 dashboard 假設；新文件全部指向 `total_cost_usd`。
  - **不複製 failure_summary pattern 到所有 service**：v1 走方式 1（n8n 從 workflow_runs 撈），複雜度低、改動小、夠用。等 production 觀察 1 週若發現 W4/W5/W6 結構化失敗摘要常被需要再升級。
- 對齊現有約定：
  - 沿用 `compute_llm_cost(model, input_tokens, output_tokens)` 統一成本計算；P1.1 用 `settings.MATCH_ADJUDICATION_MODEL_GEMINI` 為 model 名（與 service 實際呼叫一致）
  - 沿用 result dict + log_summary 雙軌（數字欄給未來自動化、log_summary 給人類即時看）
  - 沿用 doc Markdown table 風格與既有 §1 / §3 一致
- 測試/驗證：
  - `.venv/bin/python -m unittest tests.test_signal_intelligence_v2.TestSignalProcessorService.test_adjudication_tokens_aggregated_into_cost` → ok
  - `.venv/bin/python -m unittest tests.test_log_summary_utils -v` → 9/9 pass（4 既有 + 5 新）
  - `.venv/bin/python -m unittest discover -s tests` → **167/167 pass**（161 → 167，+6 new，無回退）
- Self-review 對應表：
  - P1.1 ✅ 修了——並再次提醒：上輪 Codex 在 W7 抓到 `_, _ = gemini_client.generate_json(...)` 丟 token 的 bug，這次 W4 又是同形 bug（不同位置）。**這是系統性 review pattern**：所有 LLM call 結果一定要查 token 是否進 run total。
  - P1.2 ✅ 修了——doc 對齊 research plan
  - P2.1 ✅ 修了——n8n 實作前可照表設、不用猜
  - P2.2 ✅ 修了——含 n8n Function node 範例 code，可直接複製
  - N1 / N2（tagged 靜默降為 ok / MAX_LOG_LINES 不優先 [warn]）→ 仍未做，影響低，留下一輪
- 後續可選：
  - **建立 systematic LLM-call audit script**：grep 所有 `gemini_client.generate_json(` / `openai_client.generate_json(` 呼叫，檢查回傳 tuple 的 token 是否被某個 stats / counter 接住。一次 script 把整個 pipeline 掃過。
  - 維持上輪 next steps（selection 平衡、duplicate_suspected hard filter、舊 cost 資料 migration、§5 月費估算重做）

## 2026/05/16 10:15 - Codex 更新
- 更新者：Codex
- 進度：完成「動態模型路由 + 單次 A/B test override」實作，讓 Zeabur 上不用 redeploy 也能切 W4–W9 模型，並支援 n8n 單次實驗 payload。
- 核心能力：
  - **全域 runtime config**：新增 `GET /admin/model-routing` 與 `PATCH /admin/model-routing`，寫入 Firestore `runtime_config/model_routing`。Zeabur 要設 `MODEL_ROUTING_RUNTIME_ENABLED=true` 後重啟 service 才啟用 Firestore runtime read/write；本機預設關閉，避免 unit test 誤打真實 Firestore。
  - **單次 workflow override**：W4/W5/W6/W7/W8/W9 endpoint payload 可帶 `model_overrides`，只影響該次 run，優先序最高。
  - **優先序固定**：`request.model_overrides` → Firestore `runtime_config/model_routing` → Zeabur env variables → `app/core/config.py` defaults。
  - **response 可觀測**：支援 override 的 workflow response 會回 `model_routing`，包含 route key、provider、model、reasoning_effort、source，方便 n8n / Sheet 記錄 A/B 組別。
- 支援 route key：
  - `w4_canonicalization`：W4 legacy canonical helper，Gemini only
  - `w4_match_adjudication`：W4 item → signal 模糊區 adjudication，Gemini only
  - `w5_judgement`：W5 importance score，Gemini / OpenAI
  - `w6_business_impact`：W6 business impact，Gemini / OpenAI
  - `w7_thread_refine`：W7 Pro thread memory refine，Gemini only
  - `w7_phase_assignment`：W7 phase assignment，Gemini only
  - `w8_briefing`：W8 daily briefing，Gemini / OpenAI
  - `w9_podcast_script`：W9 podcast script，Gemini / OpenAI
- 影響檔案：
  - **新增**：
    - `app/services/model_routing_service.py` — route spec、resolver、Firestore runtime config、request override validation、60 秒 cache
    - `app/api/routes_admin.py` — `GET/PATCH /admin/model-routing`
    - `app/api/model_routing_payloads.py` — API request 共用 `ModelRouteOverride`
    - `tests/test_model_routing_service.py` — resolver / validation / merge tests
    - `tests/test_admin_model_routing_api.py` — admin API auth / patch / invalid route tests
  - **修改**：
    - `app/main.py` — mount admin router
    - `app/clients/firestore_client.py` — 新增 `get_runtime_config` / `set_runtime_config`
    - `app/api/routes_signals.py` / `routes_briefings.py` / `routes_podcasts.py` — request 加 `model_overrides` 並傳入 service
    - `app/services/rss_signal_matching_service.py` / `rss_signal_processor_service.py` — W4 adjudication 走 model routing，成本用實際 route model
    - `app/services/rss_canonical_event_service.py` — legacy canonical helper 改走 model routing
    - `app/services/rss_importance_service.py` — W5 判分改走 route resolver，支援 Gemini/OpenAI per-run override
    - `app/services/rss_business_impact_service.py` — W6 改走 route resolver，支援 Gemini/OpenAI per-run override
    - `app/services/rss_story_thread_service.py` — W7 refine / phase assignment 改走 route resolver
    - `app/services/rss_briefing_service.py` — W8 briefing 改走 route resolver
    - `app/services/rss_podcast_script_service.py` / `rss_podcast_run_service.py` — W9 script / run-daily 傳遞 override 並回傳 `model_routing`
    - `docs/n8n_setup.md` — 新增 `Model Routing / A-B Test` 段落、payload 範例、run_bucket 命名提醒
    - `tests/test_signals_api.py` / `tests/test_podcasts_api.py` — 補 API 傳遞 override regression
- 使用範例：
  - 全域改模型：
    ```json
    PATCH /admin/model-routing
    {
      "note": "W8/W9 AB test",
      "routes": {
        "w8_briefing": {
          "provider": "openai",
          "model": "gpt-5",
          "reasoning_effort": "medium"
        }
      }
    }
    ```
  - 單次 A/B test：
    ```json
    {
      "run_bucket": "DAILY_2026_05_16_w8_openai_B",
      "model_overrides": {
        "w8_briefing": {
          "provider": "openai",
          "model": "gpt-5"
        }
      }
    }
    ```
- 設計取捨：
  - **本機預設不讀 Firestore runtime config**：避免測試與本地開發卡在 Google credentials / network；production Zeabur 用 `MODEL_ROUTING_RUNTIME_ENABLED=true` 明確打開。
  - **Gemini-only route 不允許 OpenAI override**：W4 canonical / W4 match / W7 refine / W7 phase 目前 service 只接 Gemini client，若硬塞 OpenAI 會回 400，避免假裝支援。
  - **A/B test 必須使用不同 `run_bucket`**：workflow idempotency 仍用 `workflow + run_bucket`；同 bucket 第二次會被視為 duplicate，不會重跑昂貴 LLM call。
  - **不改演算法，只改模型控制面**：W4/W7 matching、phase routing、W8/W9 prompt 邏輯都維持原樣。
- 測試/驗證：
  - `.venv/bin/python -m unittest tests.test_model_routing_service tests.test_admin_model_routing_api` → **6/6 pass**
  - `.venv/bin/python -m unittest tests.test_rss_importance_service tests.test_rss_business_impact_service` → **25/25 pass**
  - `.venv/bin/python -m unittest tests.test_rss_briefing_service tests.test_rss_podcast_script_service` → **30/30 pass**
  - `.venv/bin/python -m unittest tests.test_signal_intelligence_v2 tests.test_rss_story_thread_phases tests.test_signal_matching_adjudication_persistence` → **39/39 pass**
  - `.venv/bin/python scripts/audit_llm_token_capture.py` → **[ok] no LLM token-capture violations found**
  - `.venv/bin/python -m unittest discover -s tests` → **176/176 pass**
- 後續建議：
  - 在 Zeabur 設 `MODEL_ROUTING_RUNTIME_ENABLED=true` 後，用 `GET /admin/model-routing` 確認 `runtime_config.enabled=true`。
  - n8n A/B test 建議先從 W8 / W9 開始：同一天用不同 `run_bucket` 跑 A/B，Sheet 記錄 `model_routing`、`cost_usd`、retry_count、人工品質分數。
  - 下一輪可以加一張 `Model_AB_Log` Sheet schema，專門記錄 A/B 組別、模型、成本、人工評分與勝出原因。

## 2026/05/18 10:20 - Codex 更新
- 更新者：Codex
- 進度：完成 W4 n8n production bring-up 與穩定化。這輪主要處理三個 production 現象：`inhomogeneous shape` vector crash、Firestore `Transaction too big`、以及 n8n 成功/失敗 log 分支混寫。
- 問題定位：
  - **P0 — malformed vector 導致 W4 500**：n8n W4 一開始回 `setting an array element with a sequence... shape was (37,) + inhomogeneous part`。根因是 `rss_items` 或 `rss_signals` 內某些 embedding / centroid 欄位不是乾淨的一維 `list[float]`，`cosine_similarity_batch()` 建 numpy matrix 時炸掉。已在上一個 commit 修：`coerce_numeric_vector()` / `is_numeric_vector()`，batch cosine 遇壞 vector 回 0 similarity，W4 cached embedding 也會驗證，不再沿用壞 vector。
  - **P0 — Firestore transaction too big**：`limit_items=20` 仍回 `400 Transaction too big. Decrease transaction size.`。根因是 W4 每筆 item 會寫 4 組 768-dim vector（event/entity/impact/context embedding），`rss_items` v2 update 或 `rss_signals` upsert 以 50 筆一 batch commit 時，Firestore request size / index mutation 過大。修法：`MULTI_VECTOR_BATCH_WRITE_LIMIT = 1`，multi-vector docs 一筆一 commit；write 數量與成本不變，只增加 RPC 次數。單舊 embedding batch 調為 25。
  - **P1 — W4 每筆重建 embedding client**：Zeabur log 顯示每處理一筆 item 都 `Initialized Gemini Embedding Client`。修法：`rss_signal_processor_service._process_new_items_inner()` lazy 建立一次 `shared_embedding_client`，同一個 W4 run 共用。
  - **P1 — Federal Register unblock 頁污染 article_lead**：Zeabur log 顯示 federalregister.gov 302 到 `unblock.federalregister.gov` 並回 200。原邏輯可能把 anti-bot/unblock 頁當文章 lead 存入。修法：`rss_article_extraction_service._is_block_page_response()` 偵測 final host / 常見 block phrase，標成 `failed` 並保留原 `article_lead` / RSS summary。
  - **P1 — n8n log 雙寫 success + failed**：n8n HTTP 失敗時仍走 success append，Sheet 出現 `success/0/空 run_bucket` 加上一行 failed。修法在 n8n：HTTP Request 開 `Continue On Fail=true`，後接 IF，以 `log_summary_version == 1` 判斷 success；true / false 各自 normalize 後再 append，同一次只寫一行。
- Commit / push：
  - `70b86af Stabilize W4 vector writes` 已 push 到 `rss-status-200-fetchable`。
  - 主要檔案：`app/clients/firestore_client.py`、`app/services/rss_signal_processor_service.py`、`app/services/rss_article_extraction_service.py`。
  - 新增 tests：`tests/test_firestore_client_batching.py`、`tests/test_rss_article_extraction_service.py`。
- n8n W4 最終路線：
  - Endpoint 必須是 `POST /signals/process-new-items`，不是 legacy `/signals/cluster`。
  - `Build W4 Payload` 正式排程使用 UTC 30 分鐘 floor bucket，例如 `2026_05_18T0000Z`。手動測試才用 `manual_w4_selective_50_<timestamp>`。
  - HTTP body 透過 `{{ JSON.stringify($json.body) }}` 傳入；不要在 raw JSON 字串內寫 `"run_bucket": "={{ $json.run_bucket }}"`，那會被當 literal，生成 `signal_process______json_run_bucket___`。
  - IF 建議條件：`{{ $json.log_summary_version }}` is equal to `{{ 1 }}`。
  - Sheet 欄位以 `status` 為準；`fin` 可省略，若已有欄位則 success/skipped = `Y`，failed = `N`。
- 目前 W4 production 建議參數：
  ```json
  {
    "since_hours": 24,
    "limit_items": 50,
    "max_workers": 5,
    "article_extraction": "selective",
    "canonicalize": "selective",
    "embed": true,
    "match": true,
    "run_bucket": "UTC_30_MIN_FLOOR"
  }
  ```
  - `limit_items=50` 是目前日常建議；`250` 暫時只作手動 backlog catch-up，不作剛上線的排程預設。
  - `article_extraction=selective` 是這輪優化目的，應保持開啟；`off` 只用於故障定位。
- Production / n8n 驗證結果：
  - Manual smoke `limit_items=3`：processed 3/3，wrote 3 signals，cost `$0.000042`，證明 API / auth / run_bucket 正常。
  - W4 `limit_items=50`, `article_extraction=off`：processed 50/50，embedded 50，wrote 19 signals，`thin_dropped_count=25`，duration `199s`，cost `$0.001488`。
  - W4 `limit_items=50`, `article_extraction=selective`：processed 22/22，`article_extracted_count=11`，wrote 12 signals，`thin_dropped_count=6`，duration `165.7s`，cost `$0.007473`。Selective 有效降低 thin drop 比例（約 50% → 27%），但會讓更多 item 進 review band，W4 adjudication 成本略升，仍屬可接受。
- 設計取捨：
  - **multi-vector 一筆一 commit** 是止血策略：Firestore write 數不變，費用不因 batch 拆小而上升；缺點是 RPC 次數增加、W4 duration 稍長。長期應在 Firestore 關掉 vector 欄位 single-field index 後再把 batch 拉回 10/25。
  - **run_bucket idempotency 不看 request_hash 決定是否重跑**：同 bucket 即使 body 從 `off` 改 `selective`，也會 `skipped_duplicate=true` 回上次結果。這是刻意保護昂貴步驟；測不同 body 必須換 manual bucket。
  - **W4 先穩定 24h 再進 W5/W6**：先看 `failed=0`、`duration_ms` 多數 < 300000、`thin_dropped_count / processed_item_count < 40%`、單次 `cost_usd` 大多 < `$0.02`。
- 後續待辦：
  - Firestore Console 建議加 single-field index exemption：
    - `rss_items.embedding`
    - `rss_items.event_embedding`
    - `rss_items.entity_embedding`
    - `rss_items.impact_embedding`
    - `rss_items.context_embedding`
    - `rss_signals.event_centroid`
    - `rss_signals.entity_centroid`
    - `rss_signals.impact_centroid`
    - `rss_signals.context_centroid`
  - W4 穩定 24h 後，再打開 W5 Verify/Judge；不要同時啟動多個 W4 schedule 搶同一批 pending item。

## 2026/05/18 10:55 - Codex 更新
- 更新者：Codex
- 進度：完成 W5 Verify/Judge n8n bring-up 規劃、payload/log mapping 驗證與 production 小流量 smoke test。
- 背景：W4 已穩定到 `limit_items=50` + `article_extraction=selective`，開始準備 W5 workflow。先讀 `docs/AI-log.md` 最新 W4 記錄與 `docs/n8n_setup.md`，再對照 `app/api/routes_signals.py`、`rss_verification_service.py`、`rss_importance_service.py` 的實際 schema。
- API payload 驗證：
  - W5 Verify：`POST /signals/verify` 接受 `{ "since_hours": int, "force": bool }`；不支援 `run_bucket`，也不走 `workflow_runs` idempotency。
  - W5 Judge：`POST /signals/judge` 接受 `{ "since_hours": int, "max_workers": int, "force": bool, "max_signals_per_run": int, "quality_gate": "supported_or_promoted", "run_bucket": string, "model_overrides": optional }`；會寫 `workflow_runs/signal_judge_<run_bucket>`，retry 同 bucket 會回 `skipped_duplicate=true`。
  - Production 正式建議仍維持：Verify `{ "since_hours": 24, "force": false }`；Judge `{ "since_hours": 4, "max_workers": 5, "force": false, "max_signals_per_run": 200, "quality_gate": "supported_or_promoted", "run_bucket": "UTC_HOUR_FLOOR" }`。
- n8n log mapping：
  - 已在 `docs/n8n_setup.md` 新增 `W5 n8n Implementation Notes`，含 Build W5 Payload、Verify/Judge HTTP node 設定、IF 條件、成功 normalize code、extra columns、error branch 注意事項。
  - Verify row：`workflow=W5_verify`，`primary_count_1=verified_signal_count`，`primary_count_2=skipped_already_verified_count`，tokens/cost 為 0，`workflow_run_id` 留空。
  - Judge row：`workflow=W5_judge`，`primary_count_1=judged_signal_count`，`primary_count_2=failed_signal_count`，tokens/cost 使用 `total_input_tokens` / `total_output_tokens` / `total_cost_usd`，`workflow_run_id=response.workflow_run_id`。
- Production smoke test：
  - 先讀 `/signals/recent?hours=6&limit=5`，確認近 6 小時有 W4 新 signal 且多數尚未 verified/judged。
  - Verify smoke body `{ "since_hours": 6, "force": false }`：`total_signal_count=32`、`verified_signal_count=32`、`skipped_already_verified_count=0`；status 分布 `single_source=29, partially_supported=2, regional_only=1`；heat 分布 `low=29, medium=3`；`duration_ms=36256`；`log_summary_version=1`。
  - Judge smoke body `{ "since_hours": 6, "max_workers": 1, "force": false, "max_signals_per_run": 3, "quality_gate": "supported_or_promoted", "run_bucket": "manual_w5_judge_smoke_20260518T0045Z" }`：`candidate_signal_count=3`、`judged_signal_count=3`、`failed_signal_count=0`、`skipped_quality_gate_count=22`、`avg_score=40.0`、score buckets `40-59=2, <40=1`、tokens `5787/5426`、`total_cost_usd=0.012299`、`judge_model=gpt-5-mini`、`duration_ms=65555`。
  - Duplicate smoke：同一個 Judge `run_bucket` 重打，回 `skipped_duplicate=true`、`workflow_status=completed`、`[skip] W5 Judge run_bucket ... 已完成或正在執行`，確認 retry 不會重跑 LLM。
- 注意事項：
  - Production 目前 `model_routing.w5_judgement.source=env` 且模型是 `gpt-5-mini`，不是較早文件預設的 Gemini Flash。若要改回 Gemini，需要用 Zeabur env 或 `/admin/model-routing` runtime config 調整。
  - Verify 近 6 小時 32 筆耗時 36.3s，正式 24 小時第一次跑可能更久；n8n Verify timeout 建議至少 180s。
  - Judge smoke 顯示 quality gate 有效：25 個 verified 後只有 3 個進模型，22 個 low-value singleton 被擋。

## 2026/05/18 11:25 - Codex 更新
- 更新者：Codex
- 進度：開始協助 production 上線環境 setup，完成 preflight 與 Google Sheet log 分頁準備。
- Preflight：
  - Repo 目前有未提交變更：`docs/AI-log.md`、`docs/n8n_setup.md` 是 W5 文件；`.claude/settings.json` 是既有變更，未觸碰。
  - n8n `/rest/settings` 已確認 timezone 為 `Australia/Brisbane`，先前 `Asia/Taipei` 問題已消失。
  - `/admin/model-routing` 已確認 `runtime_config.enabled=true`；effective routes 目前由 env 決定：W5 `gpt-5-mini/medium`、W6 `gpt-5-mini/high`、W8/W9 `gpt-5/medium`。注意 W6 env 仍是 high，與先前降到 medium 的成本優化方向不一致，等 W6 上線前再調。
- Google Sheet `Informative.AI_RSS Management`：
  - 原有分頁：`RSS List`、`RSS Candidates`、`Sync_Log`、`Ingest_Log`、`Clustering_Log`、`Judgement_Log`、`BusinessImpact_Log`、`Briefing_Log` 等。
  - 新增 log 分頁：`Verify_Log`、`Signal_Process_Log`、`Impact_Log`。
  - 已寫入標準 header：
    - `Verify_Log`：標準 log 欄位 + `total_signal_count`、`status_distribution`、`heat_distribution`。
    - `Signal_Process_Log`：標準 log 欄位 + W4 v2 metrics（candidate/processed/embedded/article/thin/adjudication）。
    - `Impact_Log`：標準 log 欄位 + W6 monitoring 欄位。
  - `Judgement_Log` 保留既有 128 列 legacy 資料與舊欄位，並追加 W5 v2 所需欄位（`logged_at`、`timestamp_brisbane`、`workflow`、`run_bucket`、`status`、`input_tokens`、`output_tokens`、`cost_usd`、`primary_count_1`、`primary_count_2`、`workflow_run_id`、`log_summary`、`error_message`、`skipped_quality_gate_count`、`judge_model`、`model_routing`、`guard_rails_triggered`）。
- 下一步：
  - 在 n8n 建立 `W5 Verify + Judge` workflow，先用 duplicate-safe manual bucket 測 HTTP + Sheets 寫入，再替換成正式 hourly payload 並啟用 schedule。

## 2026/05/18 16:20 - Codex 更新
- 更新者：Codex
- 進度：完成 n8n W5 workflow 手動 smoke 寫入與 `Judgement_Log` 表格重整。
- n8n 手動測試：
  - `Verify_Log` 成功寫入 1 行：`workflow=W5_verify`、`status=success`、`run_bucket=manual_w5_judge_smoke_20260518T0045Z`、`primary_count_1=0`、`primary_count_2=32`。
  - `Judgement_Log` 成功寫入 1 行：`workflow=W5_judge`、`status=skipped_duplicate`、`workflow_run_id=signal_judge_manual_w5_judge_smoke_20260518T0045Z`、`primary_count_1=3`、`primary_count_2=0`。
- Google Sheet 整理：
  - 使用者確認舊 `Judgement_Log` legacy 資料不需要保留後，已將 `Judgement_Log` 重置為 v2-only 表格。
  - 目前 `Judgement_Log` 只有 26 個欄位：`logged_at`、`timestamp_brisbane`、`workflow`、`run_bucket`、`status`、`duration_ms`、`input_tokens`、`output_tokens`、`cost_usd`、`primary_count_1`、`primary_count_2`、`workflow_run_id`、`log_summary`、`error_message`、`candidate_signal_count`、`skipped_already_judged_count`、`skipped_unverified_count`、`skipped_quality_gate_count`、`avg_score`、score buckets、`judge_model`、`model_routing`、`guard_rails_triggered`。
  - 已保留一筆 smoke row 作為 n8n 欄位驗證樣本；舊 legacy 欄位與舊資料已清除。
- 下一步：
  - 在 n8n 的 `Append row: Judgement_Log` node 重新 refresh fields，確認只看到 v2 欄位。
  - 將 `Build W5 Payload` 從 fixed smoke bucket 改成正式 hourly bucket，先 manual run 一次 production-like workflow，再 activate schedule。

## 2026/05/18 16:30 - Codex 更新
- 更新者：Codex
- 進度：完成 W5 production-like manual run，確認正式 hourly bucket 與 Sheet 寫入。
- n8n workflow 狀態：
  - `Build W5 Payload` 已改為正式 UTC hourly bucket，例如 `2026_05_18T0600Z`。
  - `HTTP Request: Judge` 已改為 `{{ JSON.stringify($("Build W5 Payload").first().json.judge_body) }}`，不再使用 fixed smoke body。
- production-like manual run 結果：
  - `Verify_Log` 新增 row：`run_bucket=2026_05_18T0600Z`、`status=success`、`total_signal_count=35`、`verified_signal_count=3`、`skipped_already_verified_count=32`、`status_distribution={"single_source":3}`、`heat_distribution={"low":3}`、`duration_ms=6964`。
  - `Judgement_Log` 新增 row：`run_bucket=2026_05_18T0600Z`、`status=success`、`workflow_run_id=signal_judge_2026_05_18T0600Z`、`candidate_signal_count=0`、`judged_signal_count=0`、`failed_signal_count=0`、tokens `0/0`、cost `$0`、`judge_model=gpt-5-mini`、`duration_ms=1648`。
  - `model_routing` 再次確認 W5 目前為 env `openai/gpt-5-mini/medium`。
- 判讀：
  - W5 workflow 可以安全 activate；這次 0 candidate 是正常結果，表示 quality gate / already judged 狀態沒有額外候選需要送 LLM。
  - 每小時正式排程建議先保持 W5 只開 Verify/Judge，不急著同時打開 W6，觀察 24h 後再接 W6。

## 2026/05/18 16:40 - Codex 更新
- 更新者：Codex
- 進度：開始 W6 Business Impact 上線準備，完成 API/schema preflight、`Impact_Log` 整理、direct production smoke。
- API/schema：
  - Endpoint：`POST /signals/business-impact`
  - Payload 接受：`since_hours`、`min_score`、`max_workers`、`force`、`max_signals_per_run`、`run_bucket`、`model_overrides`。
  - W6 會從近 N 小時 `importance_score >= min_score` 且尚未 `impact_judged_at` 的 signal 中挑候選；正式設定仍建議 `min_score=60`，smoke 可用 `50` 驗證模型路徑。
- Model routing：
  - production env 目前 `w6_business_impact=openai/gpt-5-mini/high`，但本機/文件優化方向是 `medium`。
  - 決策：W6 n8n payload 先帶 request-level `model_overrides`，強制 `gpt-5-mini/medium`；這比馬上改 Zeabur env 安全，也能在 response `model_routing.source=request` 直接觀測。
- Google Sheet：
  - `Impact_Log` 已重置為 W6 v2-only header，共 27 欄：標準 log 欄位 + `candidate_signal_count`、skip counters、`impact_model`、4 個平均 list 長度、2 個空欄位 count、`avg_counterfactual_chars`、`avg_gap_note_chars`、`model_routing`。
- Direct API smoke：
  - Body：`since_hours=24`、`min_score=50`、`max_workers=1`、`max_signals_per_run=1`、`run_bucket=manual_w6_impact_smoke_20260518T0635Z`、`model_overrides.w6_business_impact={openai,gpt-5-mini,medium}`。
  - Result：`candidate_signal_count=1`、`analyzed_signal_count=1`、`failed_signal_count=0`、tokens `473/2005`、cost `$0.004128`、duration `22.8s`、`impact_model=gpt-5-mini`、`model_routing.source=request`。
  - Health metrics：`avg_sectors=5.0`、`avg_assets=4.0`、`avg_regions=4.0`、`avg_watch_points=5.0`、`empty_counterfactual=0`、`empty_gap_note=0`、`avg_counterfactual_chars=30.0`、`avg_gap_note_chars=25.0`。
  - Duplicate smoke 同 bucket 回 `skipped_duplicate=true`，確認 retry 不會重跑 LLM。
- 文件：
  - `docs/n8n_setup.md` 已新增 `W6 n8n Implementation Notes`，含 Build W6 Payload、Normalize Success/Error、Impact_Log mapping、smoke 結果。
- 下一步：
  - 在 n8n 建立 `W6 Business Impact` workflow，先用 duplicate-safe smoke bucket 手動寫入 `Impact_Log`，再改正式 hourly payload 做 production-like manual run。

## 2026/05/18 17:05 - Codex 更新
- 更新者：Codex
- 進度：完成 W6 n8n workflow smoke 寫入與 production-like manual run。
- n8n smoke 寫入：
  - `Impact_Log` 已成功寫入 duplicate-safe smoke row：`run_bucket=manual_w6_impact_smoke_20260518T0635Z`、`status=skipped_duplicate`、`primary_count_1=1`、`primary_count_2=0`、`workflow_run_id=business_impact_manual_w6_impact_smoke_20260518T0635Z`。
  - 欄位落點已讀回確認：`model_routing` 記錄為 request override `openai/gpt-5-mini/medium`。
- production-like manual run：
  - `Build W6 Payload` 已改正式 hourly bucket，例如 `2026_05_18T0700Z`。
  - 正式 body：`since_hours=24`、`min_score=60`、`max_workers=5`、`force=false`、`max_signals_per_run=100`、`run_bucket=UTC_HOUR_FLOOR`，並保留 `model_overrides.w6_business_impact={provider:openai, model:gpt-5-mini, reasoning_effort:medium}`。
  - `Impact_Log` 新增 row：`run_bucket=2026_05_18T0700Z`、`status=success`、`candidate_signal_count=0`、`analyzed_signal_count=0`、`failed_signal_count=0`、tokens `0/0`、cost `$0`、`workflow_run_id=business_impact_2026_05_18T0700Z`、`duration_ms=4892`。
  - `model_routing.source=request`，確認 production-like W6 不受 env `high` 影響。
- 判讀：
  - W6 workflow 可以安全 activate；目前 0 candidate 是正常結果，因為近 24h 尚無 `importance_score >= 60` 且未分析的 signal。
  - 上線後先看 `candidate_signal_count` 是否跟 W5 高分 signal 對齊；若連續 24h 都是 0，要回頭看 W5 quality gate / score threshold，而不是 W6 本身。

## 2026/05/18 17:15 - Codex 更新
- 更新者：Codex
- 進度：開始 W7 Daily Consolidation 上線準備，完成 API/schema preflight、`Consolidate_Log` 建立、direct production smoke。
- API/schema：
  - Endpoint：`POST /signals/consolidate-daily`
  - Payload 接受：`since_hours`、`story_lookback_days`、`max_threads`、`run_bucket`、`model_overrides`。
  - W7 會寫 `rss_story_threads`、`rss_thread_phases`，並更新 signal 的 `thread_id`、`today_delta`、`novelty_score`、`last_consolidated_at` 等欄位；因此 smoke 使用 `max_threads=1` 控制寫入範圍。
- Google Sheet：
  - 新增 `Consolidate_Log`，重置為 W7 v2-only header，共 39 欄：標準 log 欄位 + thread counters、refine token/cost、phase counters、samples、`model_routing`。
- Direct API smoke：
  - Body：`since_hours=24`、`story_lookback_days=30`、`max_threads=1`、`run_bucket=manual_w7_consolidate_smoke_20260518T0710Z`。
  - Result：`signals_considered=1`、`threads_updated=1`、`threads_created=1`、`today_delta_count=1`、`phases_upserted=1`、`phase_heuristic_assignments=1`、`phase_llm_calls=0`、`model_refined_count=0`、phase/refine cost `$0`、`duration_ms=9210`。
  - Samples：thread/phase 都是 `W.H.O. Declares Ebola Outbreak a Global Health Emergency`。
  - Duplicate smoke 同 bucket 回 `skipped_duplicate=true`，確認 retry 不會重跑 consolidation。
- 文件：
  - `docs/n8n_setup.md` 已新增 `W7 n8n Implementation Notes`，含 Build W7 Payload、Normalize Success/Error、Consolidate_Log mapping、smoke 結果。
- 下一步：
  - 在 n8n 建立 `W7 Daily Consolidation` workflow，先用 duplicate-safe smoke bucket 手動寫入 `Consolidate_Log`，再改正式 daily payload 做 production-like manual run。

## 2026/05/18 17:35 - Codex 更新
- 更新者：Codex
- 進度：完成 W7 Daily Consolidation n8n production-like manual run，確認正式 daily payload、Sheet 寫入與 warning 可觀測。
- production-like manual run：
  - `run_bucket=DAILY_2026_05_18`
  - `status=success`
  - `workflow_run_id=daily_consolidation_DAILY_2026_05_18`
  - `duration_ms=311231`，約 311.2 秒。
  - `signals_considered=35`、`threads_updated=7`、`threads_created=4`、`today_delta_count=35`。
  - `model_refined_count=10`，refine tokens `3889/4358`，refine cost `$0.048441`。
  - `phases_upserted=7`、`phases_created=0`、`phases_advanced=1`。
  - `phase_heuristic_assignments=33`、`phase_w4_evidence_assignments=0`、`phase_llm_calls=1`、phase tokens `513/144`、phase cost `$0.000082`。
  - `thread_mismatch_flagged_count=1`，sample：`sigv2_20260517_ad55ddddb4`。
  - Total observed cost：`$0.048523`。
- 判讀：
  - W7 workflow 可進入 daily schedule；production-like 不是空跑，已實際整理 35 個 signals 與 7 個 threads。
  - 因 W7 實跑耗時約 5 分鐘，n8n HTTP Request timeout 建議設 `900000` ms，排程建議 daily，不要 hourly。
  - `thread_mismatch_flagged_count=1` 是可觀測 warning，先保留，不阻擋上線；後續觀察是否重複出現在同一類 signal。

## 2026/05/18 17:55 - Codex 更新
- 更新者：Codex
- 進度：開始 W8 Daily Briefing 上線準備，完成 API/schema preflight、`Briefing_Log` 重整、direct production smoke。
- API/schema：
  - Endpoint：`POST /briefings/generate`
  - Payload 接受：`briefing_date`、`score_threshold`、`max_sections`、`max_signals_input`、`write_google_doc`、`run_bucket`、`model_overrides`。
  - W8 會讀近 24h `importance_score >= score_threshold` 的 signal，並注入 W7 thread / phase context；validation 失敗時最多 retry 1 次。
- Preflight：
  - 近 24h briefing candidates：`score_threshold >= 60` 為 0，因此 2026-05-18 正式 W8 會走 no-candidate path，預期成本 `$0`。
  - Production response 確認 W8 model routing 目前為 env `openai/gpt-5/medium`；本機 default 仍是 Gemini，但以上線 response 為準。
- Google Sheet：
  - 舊 `Briefing_Log` 保留為 `Briefing_Log_Legacy_20260518`。
  - 新 `Briefing_Log` 已重建為 W8 v2-only header，共 32 欄：標準 log 欄位 + briefing id/date、section/top_change/category counts、四大分類 section counts、retry count、Google Doc URL、model、`model_routing`、`signal_pool_health`。
- Direct API smoke：
  - Body：`score_threshold=95`、`max_sections=1`、`max_signals_input=5`、`write_google_doc=false`、`run_bucket=manual_w8_briefing_smoke_20260518T0750Z`。
  - Result：`selected_signal_count=0`、`total_input_signals=0`、tokens `0/0`、cost `$0`、duration `4.3s`、`google_doc_url=null`。
  - Duplicate smoke 同 bucket 回 `skipped_duplicate=true`，確認 retry 不會重跑 briefing。
- 文件：
  - `docs/n8n_setup.md` 已新增 `W8 n8n Implementation Notes`，含 Build W8 Payload、Normalize Success/Error、Briefing_Log mapping、smoke 結果。
- 下一步：
  - 在 n8n 建立 `W8 Daily Briefing` workflow，先用 duplicate-safe smoke bucket 手動寫入 `Briefing_Log`，再改正式 daily payload 做 production-like manual run。

## 2026/05/18 18:12 - Codex 更新
- 更新者：Codex
- 進度：完成 W8 Daily Briefing n8n smoke row 與 production-like manual run。
- n8n smoke 寫入：
  - `Briefing_Log` 成功寫入 smoke row：`run_bucket=manual_w8_briefing_smoke_20260518T0750Z`、`status=skipped_duplicate`、`workflow_run_id=briefing_generate_manual_w8_briefing_smoke_20260518T0750Z`、`selected_signal_count=0`、tokens `0/0`、cost `$0`。
  - 欄位落點已讀回確認：`model_routing` 與 `signal_pool_health` 都是 JSON 字串，沒有 n8n literal expression。
- production-like manual run：
  - `Build W8 Payload` 已改正式 daily bucket：`DAILY_2026_05_18`。
  - 正式 body：`score_threshold=60`、`max_sections=10`、`max_signals_input=80`、`write_google_doc=true`、`run_bucket=DAILY_2026_05_18`。
  - `Briefing_Log` 新增 row：`status=success`、`workflow_run_id=briefing_generate_DAILY_2026_05_18`、`briefing_id=brief_20260518_0551ec`、`briefing_date=2026-05-18`、`selected_signal_count=0`、`total_input_signals=0`、tokens `0/0`、cost `$0`、`duration_ms=4041`。
  - `google_doc_url` 為空，符合 no-candidate path；`model=gpt-5`、`model_routing.source=env`。
- 判讀：
  - W8 workflow 可以安全 activate；今天 0 candidate 是正常結果，不代表 workflow 失敗。
  - 若未來 W8 有 candidate，會打 `gpt-5/medium` 並寫 Google Doc；需觀察 `briefing_retry_count`、`section_count`、`top_change_count` 和 `google_doc_url`。

## 2026/05/18 18:35 - Codex 更新
- 更新者：Codex
- 進度：開始 W9 Daily Podcast 上線準備，完成 API/schema preflight、`Podcast_Log` 建立、no-content direct smoke。
- API/schema：
  - Endpoint：`POST /podcasts/run-daily`
  - Payload 接受：`briefing_id`、`write_google_doc`、`force_audio`、`force_package`、`run_bucket`、`model_overrides`。
  - W9 `run-daily` 會依序執行 podcast script、TTS audio、publish package，且內部自動拆成 `<run_bucket>_script`、`<run_bucket>_audio`、`<run_bucket>_package` 三個子桶。
- Preflight：
  - 最新 briefing 是 `brief_20260518_0551ec`，`selected_signal_count=0`、無 sections/top_changes。
  - 目前 production 尚無 `rss_podcast_scripts`。
  - 因今天 W8 是 no-candidate path，W9 正式 daily run 會在 script step 因 `briefing has no content` 擋下，預期成本 `$0`；這是安全保護，不是 workflow 壞掉。
- Google Sheet：
  - 新增 `Podcast_Log`，共 36 欄：標準 log 欄位 + run/script/episode/package ids、`failed_step`、script word/retry/model/cost/doc、audio URL/GCS/duration/size/TTS、source URL count、episode title、`model_routing`。
- Direct API no-content smoke：
  - Body：`write_google_doc=false`、`force_audio=false`、`force_package=false`、`run_bucket=manual_w9_podcast_no_content_smoke_20260518T0820Z`。
  - Result：HTTP 500，detail：`briefing brief_20260518_0551ec has no content`。
  - 後端 `workflow_runs/podcast_run_daily_manual_w9_podcast_no_content_smoke_20260518T0820Z` 已記錄：`status=failed`、`failed_step=script`、`cost_usd=0`、`duration_ms=4527`、`model_routing=openai/gpt-5/medium`。
- 文件：
  - `docs/n8n_setup.md` 已新增 `W9 n8n Implementation Notes`，含 Build W9 Payload、Normalize Success/Error、Podcast_Log mapping、no-content smoke 結果。
- 下一步：
  - 在 n8n 建立 `W9 Daily Podcast` workflow，先用 no-content smoke bucket 手動驗證 error branch 寫入 `Podcast_Log`；成功生成音訊的 full run 等 W8 有非空 briefing 後再跑。

## 2026/05/18 23:50 - Codex 更新
- 更新者：Codex
- 進度：完成 W9 Daily Podcast n8n no-content smoke row 與 production-like manual run。
- n8n smoke 寫入：
  - `Podcast_Log` 成功寫入 no-content smoke row：`run_bucket=manual_w9_podcast_no_content_smoke_20260518T0820Z`、`status=failed`、`failed_step=script`、`cost_usd=0`、`workflow_run_id=podcast_run_daily_manual_w9_podcast_no_content_smoke_20260518T0820Z`。
  - 欄位落點已讀回確認：沒有 n8n literal expression；`failed_step=script` 正確。
- production-like manual run：
  - `Build W9 Payload` 已改正式 daily bucket：`DAILY_2026_05_18`。
  - 正式 body：`write_google_doc=true`、`force_audio=false`、`force_package=false`、`run_bucket=DAILY_2026_05_18`。
  - `Podcast_Log` 新增 row：`status=failed`、`failed_step=script`、`cost_usd=0`、`workflow_run_id=podcast_run_daily_DAILY_2026_05_18`、error：`briefing brief_20260518_0551ec has no content`。
  - 後端 `workflow_runs/podcast_run_daily_DAILY_2026_05_18` 已記錄結構化 failure summary：`duration_ms=5166`、`failed_step=script`、`cost_usd=0`、`model_routing=openai/gpt-5/medium`。
- 判讀：
  - W9 workflow error branch 已驗證，可以安全 activate；今天失敗是預期 no-content guard，不是 workflow 壞掉。
  - 後續第一個有內容 briefing 的日子，W9 會第一次跑 full path：script → TTS → publish package；那天需要人工抽查 audio URL、Google Doc、source URL count、script word count。
  - 目前 n8n error row 的 `duration_ms` / `model_routing` 仍是 fallback 值（0 / `{}`），若要更完整可加 Firestore read `workflow_runs/<workflow_run_id>` 補 summary；不阻擋上線。

## 2026/05/19 00:05 - Codex 更新
- 更新者：Codex
- 進度：整理 Google Sheet `Informative.AI_RSS Management`，刪除不再記錄的舊分頁，並檢查晚間 workflow logs。
- Sheet cleanup：
  - 已刪除 4 張不再記錄的舊報表 / 一次性研究分頁：`Daily_Report`、`RSS Probe Research`、`RSS Gap Analysis`、`RSS Migration Audit`。
  - 已將 spreadsheet timezone 從 `Asia/Taipei` 改為 `Australia/Brisbane`，與 n8n / briefing timezone 對齊。
  - 保留 `Clustering_Log`：雖然是 legacy 名稱，但晚間仍有 W4 寫入，暫時不能刪。
- 晚間 logs 觀察：
  - W2 `Ingest_Log`：23:01 / 23:31 都有 success，新增 86 / 107 items；但每次 success 後又追加一筆 `failed HTTP 500: unknown error`。疑似 W2 n8n 有多一條 error branch 被錯接，或有另一個舊 W2 workflow 同時啟用。
  - W4：每小時 :10 寫入 `Clustering_Log`，但 `Signal_Process_Log` 仍沒有資料。log_summary 顯示 endpoint/service 是 W4 signal_process，但 n8n Sheets target 還是舊 `Clustering_Log`，且近幾輪都處理 `0/0` item。需檢查 W4 workflow 的 Google Sheets node target 與 payload。
  - W5：23:30 同一 hourly bucket 寫入 3 組 Verify/Judge；Judge 只有第一筆 success，後兩筆 duplicate skip，成本為 0。疑似 schedule/手動/舊 workflow 重複觸發，會污染表但不花 LLM。
  - W6：19:45–23:45 每小時 success，candidate 0、cost 0，正常。
  - W7：daily production-like success，仍保留 1 個 thread mismatch warning：`sigv2_20260517_ad55ddddb4`。
  - W8：daily success，selected 0、cost 0，no-candidate path 正常。
  - W9：daily failed at `script`，原因 `briefing ... has no content`，cost 0；這是 no-content guard，非事故。
- 關注事項：
  1. 先修 W2 雙寫 failed row。
  2. 再修 W4 寫入目標：應寫 `Signal_Process_Log`，不是 `Clustering_Log`；並確認 W4 為何在 W2 新增 item 後仍處理 `0/0`。
  3. W5 保留一個 hourly trigger 即可，避免同 bucket 一小時寫三次。
  4. 可把 W9 no-content error 在 n8n normalize 成 `skipped_no_content`，避免日後 dashboard 把正常空日視為紅燈。

## 2026/05/19 00:37 - Codex 更新
- 更新者：Codex
- 進度：定位並修復 W4 `0/0` 的根因，補上 regression tests，並更新 n8n 操作文件。
- 現象：
  - W4 Google Sheets target 已改到 `Signal_Process_Log`，不再寫入 `Clustering_Log`。
  - Manual run `manual_w4_limit100_20260518T141428Z` 成功：candidate/processed `41/41`、寫入 `29` signals、抽文 `32`、thin dropped `3`、adjudication `19` 次、cost `$0.043307`、duration `520.8s`。
  - 接著正式 bucket `2026_05_18T1430Z` 仍回 `0/0`；同時 W2 在 `14:31:31Z` 才完成新增 `110` items，而 W4 row 是 `14:31:23Z`，代表 schedule 太貼近 W2。
- 根因：
  - `app/clients/firestore_client.py::list_rss_items_pending_v2_processing()` 原本對 Firestore 先 `.limit(limit)`，再在 Python 過濾 `v2_processed_at + event_embedding_hash` 已完成項目。
  - 當最近前 50/100 筆剛好都已處理時，W4 會誤判沒有 pending；實測舊邏輯下 `since_hours=24`：`limit50=0`、`limit100=0`、`limit150=55`、`limit250=195`。
- 修法：
  - Firestore query 改成依 `first_seen_at` / `published_at` newest-first，先掃較大的 `scan_limit = min(max(limit * 10, 500), 5000)`，再過濾已處理項目，最後只回傳 requested `limit`。
  - 保留既有 schema，不新增 Firestore migration；長期若要更乾淨可加 `v2_processing_status` / `v2_pending` 欄位後直接 query pending。
- 驗證：
  - Local patched check：`since_hours=24 limit50 pending=50`、`limit100 pending=100`。
  - `.venv/bin/python -m unittest tests.test_firestore_client_batching` → **4/4 pass**。
- n8n 設定：
  - 修復部署後正式 W4 回到 `{ "since_hours": 24, "limit_items": 50, "article_extraction": "selective", "canonicalize": "selective" }`。
  - W4 schedule 建議改成 W2 後 10-15 分鐘，例如 W2 `:00/:30`，W4 `:12/:42` 或 `:15/:45`；避免 W4 在 W2 還沒寫完時先跑。
  - 若 backend fix 尚未部署，短期 workaround 是 `since_hours=1` + `limit_items=50`，但這只是避開舊 query bug，不是長期設定。

## 2026/05/19 07:40 - Codex 更新
- 更新者：Codex
- 進度：檢查 overnight logs，確認 W2/W4/W5/W6/W7/W8 已大致穩定，並定位 W9 full-path 第一個 audio-stage failure。
- Overnight logs：
  - W2：`15:15Z` 後 12 筆全為 `success`，不再雙寫 failed row。
  - W4：已不再 `0/0`，多數正式 bucket 處理 `50/50`；`2026_05_18T1600Z` 有 1 筆 transient SSL `bad record mac`，後續 bucket 正常。
  - W5：Verify/Judge 每小時基本各一筆；`2026_05_18T1500Z` 還有 1 筆修正前 duplicate skip，之後乾淨。
  - W6：有候選才花錢，0 candidate runs cost 為 0。
  - W7：`DAILY_2026_05_19` success，整合 173 signals 到 7 threads。
  - W8：`DAILY_2026_05_19` success，選入 `32/71` signals，輸出 `14` sections / `6` top changes，cost `$0.20829`。
- W4 吞吐量觀察：
  - W4 每小時 `limit_items=50` 跑得動，但 W2 每 30 分鐘新增量高，pending 仍累積：近 1 小時約 212、近 6 小時約 831、近 24 小時超過 1000。
  - 建議下一步把 W4 schedule 改為每 30 分鐘（W2 後 10-15 分鐘，例如 `:15/:45`），先不調高 `limit_items`。
- W9 full-path failure：
  - `Podcast_Log` row：`run_bucket=DAILY_2026_05_19`、`status=failed`、error：`400 Audio encoding MP3 is currently unsupported. Temporarily, only LINEAR16 audio encodings are supported for Long Audio Synthesis.`
  - 判讀：W9 已成功越過 no-content guard 並進入 audio stage，失敗點是 backend TTS encoding，不是 n8n 接線。
- 修法：
  - `rss_podcast_audio_service._audio_object_path()` 改 `.mp3` → `.wav`。
  - `synthesize_long_audio.audio_config.audio_encoding` 改 `MP3` → `LINEAR16`。
  - `tests/test_rss_podcast_audio_service.py` 補 assertion：Long Audio request 必須用 `LINEAR16` 且 output GCS URI 為 `.wav`。
- 驗證：
  - `.venv/bin/python -m unittest tests.test_rss_podcast_audio_service tests.test_rss_publish_package_service tests.test_rss_podcast_script_service tests.test_podcasts_api` → **22/22 pass**。
- 後續：
  - deploy 後用 fresh manual W9 bucket 重跑 full path，或等下一個 daily bucket；不需要改 n8n payload。

## 2026/05/19 07:55 - Codex 更新
- 更新者：Codex
- 進度：修復 W8 Google Doc failure 靜默問題，讓下次 production 能直接看到未寫 Doc 的真因。
- 問題定位：
  - `DAILY_2026_05_19` 的 W8 是 fresh run（`skipped_duplicate=false`），已成功產生 briefing：`selected_signal_count=32`、`google_doc_id=None`、`google_doc_url=None`。
  - 根因不是 n8n payload；`write_google_doc=true` 與 HTTP body mapping 皆正確。
  - 後端 `write_briefing_to_doc()` 失敗時原本直接 return `(None, None)`，`generate_daily_briefing()` 也會 catch exception 後繼續 success，導致 Sheet 只看到「未寫 Google Doc」，看不到 credential / permission / Docs API 真因。
- 修法：
  - `RssBriefing` 新增 `google_doc_error` 欄位。
  - `write_briefing_to_doc()` 改回傳 `(google_doc_id, google_doc_url, google_doc_error)`；Docs client 未初始化、缺 `documentId`、Docs API exception 都會帶出錯誤字串。
  - W8 result / Firestore summary 會保存 `google_doc_error`；`log_summary` 若未寫 Doc 且有 error，會輸出 `[warn] Google Doc 未寫：...`。
  - `docs/n8n_setup.md` 的 W8 Normalize Success 建議把 `error_message` 映射為 `r.google_doc_error || ""`。
- 驗證：
  - `.venv/bin/python -m unittest tests.test_rss_briefing_service tests.test_briefings_api` → **20/20 pass**。

## 2026/05/19 08:10 - Codex 更新
- 更新者：Codex
- 進度：修復 W9 第二層 TTS voice failure。
- 問題定位：
  - `DAILY_2026_05_19` 重跑後已越過先前的 LINEAR16 encoding 問題，新的失敗點是 Google TTS 回傳 `400 Voice 'cmn-TW-Chirp3-HD-Charon' does not exist`。
  - 官方 voice list 中 `cmn-TW` 有效聲線為 `cmn-TW-Standard-A/B/C` 與 `cmn-TW-Wavenet-A/B/C`；`Chirp3-HD-Charon` 屬於 `cmn-CN`，不是 `cmn-TW`。
- 修法：
  - `PODCAST_TTS_VOICE` default 改為 `cmn-TW-Wavenet-B`。
  - W9 audio 文件同步更新為 `LINEAR16` + `.wav` + `cmn-TW-Wavenet-B`。
- 後續：
  - Zeabur 若有顯式設定舊 env `PODCAST_TTS_VOICE=cmn-TW-Chirp3-HD-Charon`，需改為 `cmn-TW-Wavenet-B` 或移除該 env 讓 code default 生效。
  - Redeploy 後用同一個 `DAILY_2026_05_19` bucket 重跑 W9，應會 reuse script 並只重試 audio/package。

## 2026/05/19 08:35 - Codex 更新
- 更新者：Codex
- 進度：W9 full path 已成功，補齊 podcast Google Doc failure observability。
- Production 結果：
  - `DAILY_2026_05_19` W9 成功：script `6418` 字、audio `1200s`、GCS `.wav`、`tts_voice=cmn-TW-Wavenet-B`、package 完成、成本 `$0.16997`。
  - 仍需觀察：`script_google_doc_url` 為空，主流程不受影響，但文件備份未寫。
- 修法：
  - `RssPodcastScript` 新增 `google_doc_error` 欄位。
  - `write_podcast_script_to_doc()` 改回傳 `(google_doc_id, google_doc_url, google_doc_error)`，與 W8 briefing doc writer 對齊。
  - W9 script log 若未寫 Doc 且有錯誤，會輸出 `[warn] 未寫 podcast Google Doc：...`。
  - `docs/n8n_setup.md` 的 W9 Normalize Success 建議把 `error_message` 映射為 `script.google_doc_error || ""`。
- 驗證：
  - `.venv/bin/python -m unittest tests.test_rss_podcast_audio_service tests.test_rss_publish_package_service tests.test_rss_podcast_script_service tests.test_podcast_doc_writer tests.test_podcasts_api` → **24/24 pass**。
