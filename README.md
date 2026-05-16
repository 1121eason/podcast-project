# Signal Brief MVP

更新紀錄：2026/05/11 Claude 更新（補上 Signal Intelligence v2 端點與運維注意事項）

本專案是一個基於 FastAPI 與 Google AI (Gemini) 的每日高訊號情資發佈包系統，MVP 受眾為投資人、商務決策者與創業經營者。

Phase 5 之後，系統會以全自動觀察流程產生 Podcast 文稿、選配 Google Doc 備份稿、Google TTS MP3 音訊與手動上架用發佈包。Google Doc 只作為檢視與備份，不是人工審稿關卡。

預期規劃部署於 GCP Cloud Run，利用 Cloud Scheduler 每日定時觸發 `/briefings/generate` 與 `/podcasts/run-daily` 端點。

## 目錄結構
- `app/api/`: FastAPI 路由 (啟動 Job, Polling)
- `app/clients/`: 第三方服務封裝 (Firestore, Google Docs, Drive, Gemini, Secret Manager)
- `app/core/`: 核心設定
- `app/models/`: Pydantic 資料結構
- `app/prompts/`: AI 提示詞
- `app/services/`: 業務流程 (RSS ingest, signals, briefing, podcast script, audio, publish package)

## 環境準備與設定
系統相依多項 GCP 服務。設定檔分成兩層：

- `.env`: 專案共用預設值，可從 `.env.example` 複製。
- `.env.local`: 本機私密設定、secret、絕對路徑，可從 `.env.local.example` 複製。

系統會先讀 `.env`，再用 `.env.local` 覆蓋。

```bash
cp .env.example .env
cp .env.local.example .env.local
```

請把 service account JSON 移出 repo，再更新 `.env.local` 的絕對路徑：

```bash
mkdir -p ~/.config/signal-brief
mv podcast-project-491300-af5203fc737b.json ~/.config/signal-brief/service-account.json
```

`.env.local` 需要至少設定：

```env
GOOGLE_APPLICATION_CREDENTIALS="/Users/eason/.config/signal-brief/service-account.json"
ADMIN_TOKEN="your-local-admin-token"
GCS_AUDIO_BUCKET="your-podcast-audio-bucket"
```

> **注意：** 執行此系統需要對應的 Google Cloud Service Account 憑證 (`GOOGLE_APPLICATION_CREDENTIALS`) 並開啟 Docs, Drive, Firestore, Text-to-Speech 及 Gemini API 權限。

若使用個人 Google 帳號產生 Google Docs/Drive 檔案，請使用 `GOOGLE_WORKSPACE_AUTH_MODE="oauth"`。Firestore、Vertex AI 與 Text-to-Speech 仍可使用 service account；Google Docs/Drive 會使用 OAuth 登入的個人帳號。

首次 OAuth 授權：
```bash
pip install -r requirements.txt
python3 scripts/authorize_google_workspace.py
```
授權完成後會產生 `.secrets/google_oauth_token.json`。之後重啟專案會自動讀取與 refresh token，不需要每次登入。

### Google Drive / Docs 權限建議
如果你有 Google Workspace，建議本機開發與 Cloud Run 使用 Service Account + Shared Drive，不依賴 `gcloud auth application-default login`，避免每次重新登入。

1. 在 Google Drive 建立一個 Shared Drive，例如 `Signal Brief Output`。
2. 將 Service Account email 加入該 Shared Drive，權限至少給 Content manager。
3. 在 Shared Drive 內建立輸出資料夾，將資料夾 ID 填入 `DRIVE_OUTPUT_FOLDER_ID`。
4. `.env.local` 固定設定 `GOOGLE_APPLICATION_CREDENTIALS` 指向 service account JSON 的本機絕對路徑。

系統會在有設定 `DRIVE_OUTPUT_FOLDER_ID` 時，透過 Drive API 在該資料夾建立 Google Doc，並支援 Shared Drive 的 `supportsAllDrives` 參數。

如果你使用個人 Google 帳號與 OAuth，`DRIVE_OUTPUT_FOLDER_ID` 可以留空，Google Doc 會建立在 OAuth 使用者的 My Drive 根目錄；也可以填入該使用者 My Drive 裡的資料夾 ID。

## 執行與測試

### 本機測試
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```
測試 API：
```bash
curl -X POST http://localhost:8000/briefings/generate \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: your-admin-token" \
  -d '{"briefing_date": "2026-03-25", "write_google_doc": true}'
```

產生 Phase 5 Podcast 文稿、音訊與發佈包：
```bash
curl -X POST http://localhost:8000/podcasts/run-daily \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: your-admin-token" \
  -d '{"briefing_id": null, "write_google_doc": true, "force_audio": false, "force_package": false}'
```

取得手動上傳 Podcast 平台用的發佈包：
```bash
curl http://localhost:8000/podcasts/{script_id}/publish-package
```

### 部署至 Cloud Run
```bash
gcloud builds submit --tag gcr.io/YOUR_PROJECT/daily-briefing-podcast
gcloud run deploy daily-briefing-podcast \
  --image gcr.io/YOUR_PROJECT/daily-briefing-podcast \
  --platform managed \
  --region us-central1 \
  --no-allow-unauthenticated
```
部署完成後，可至 GCP Cloud Scheduler 建立每日清晨定時 POST 至 `/briefings/generate` 與 `/podcasts/run-daily` 的工作排程。會產生成本或改變狀態的 endpoint 需提供 `X-Admin-Token`。

## Signal Intelligence v2 端點

Phase 2 的全量 4h 重分群已被 incremental 流程取代。詳見 [docs/rss_ai_research_plan.md](docs/rss_ai_research_plan.md) 的「Signal Intelligence v2」段落。常用端點：

```bash
# 增量處理新 RSS items (extraction + canonicalize + multi-vector embed + hybrid match)
curl -X POST http://localhost:8000/signals/process-new-items \
  -H "Content-Type: application/json" -H "X-Admin-Token: $ADMIN_TOKEN" \
  -d '{"since_hours": 6, "limit_items": 250, "max_workers": 5,
       "article_extraction": "selective", "canonicalize": "selective",
       "embed": true, "match": true, "run_bucket": "UTC_30_MIN_FLOOR"}'

# 將 signal 接到 30 天 story thread，更新 today_delta / continuation hint
curl -X POST http://localhost:8000/signals/consolidate-daily \
  -H "Content-Type: application/json" -H "X-Admin-Token: $ADMIN_TOKEN" \
  -d '{"since_hours": 36, "story_lookback_days": 30, "max_threads": 200,
       "run_bucket": "DAILY_2026_05_11"}'

# Run-daily orchestrator (script + audio + publish package)
curl -X POST http://localhost:8000/podcasts/run-daily \
  -H "Content-Type: application/json" -H "X-Admin-Token: $ADMIN_TOKEN" \
  -d '{"briefing_id": null, "write_google_doc": true,
       "run_bucket": "DAILY_2026_05_11"}'
```

`run_bucket` 是 n8n 排程桶（建議 `UTC_30_MIN_FLOOR` / `UTC_HOUR_FLOOR` / `DAILY_YYYY_MM_DD`），用來防止 retry 重跑昂貴流程。

## 錯誤處理與重試 (Idempotency)
所有昂貴 endpoint（`/signals/process-new-items`、`/signals/consolidate-daily`、`/signals/judge`、`/signals/business-impact`、`/briefings/generate`、`/podcasts/generate-script`、`/podcasts/run-daily`、子步驟 `synthesize_podcast_audio` / `create_publish_package`）都接到 `workflow_runs/{workflow_name}_{run_bucket}` doc，重複呼叫同一個 bucket 會直接回傳上次成功結果，不會重打模型或 TTS。Podcast episode 與 publish package 使用 deterministic ID（`episode_{script_id}`、`package_{script_id}`），方便重試時更新同一份音訊/發佈包紀錄。Podcast run、script、episode、publish package 皆會寫入 Firestore 供觀察與追蹤。

## 營運與品質控管
新聞來源、整體流程與品質確認方式請見 [docs/operating_model.md](docs/operating_model.md)。
