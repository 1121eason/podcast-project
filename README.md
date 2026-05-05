# Signal Brief MVP

本專案是一個基於 FastAPI 與 Google AI (Gemini) 的每日高訊號情資發佈包系統，MVP 受眾為投資人、商務決策者與創業經營者。

系統會先產生 Google Doc briefing 草稿並停在人工審稿狀態；審稿完成後呼叫 approve endpoint，才會讀回 Google Doc 最新內容、產生 Podcast 音訊與手動上傳用發佈包。

預期規劃部署於 GCP Cloud Run，利用 Cloud Scheduler 每日定時觸發 `/jobs/daily-briefing/start` 與 `/jobs/{job_id}/poll` 端點。

## 目錄結構
- `app/api/`: FastAPI 路由 (啟動 Job, Polling)
- `app/clients/`: 第三方服務封裝 (Firestore, Google Docs, Drive, Gemini, Secret Manager)
- `app/core/`: 核心設定
- `app/models/`: Pydantic 資料結構
- `app/prompts/`: AI 提示詞
- `app/services/`: 業務流程 (Research Kickoff, Polling, Docs Writer, Approval, Script, Audio, Publish Package)

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
curl -X POST http://localhost:8000/jobs/daily-briefing/start \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: your-admin-token" \
  -d '{"run_date": "2026-03-25"}'
```

輪詢處理研究結果並產生待審稿 Google Doc：
```bash
curl -X POST http://localhost:8000/jobs/briefing_2026_03_25/poll \
  -H "X-Admin-Token: your-admin-token"
```

人工審稿 Google Doc 後，核准並產生音訊與發佈包：
```bash
curl -X POST http://localhost:8000/jobs/briefing_2026_03_25/approve \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: your-admin-token" \
  -d '{"approved_by": "editor"}'
```

取得手動上傳 Podcast 平台用的發佈包：
```bash
curl http://localhost:8000/jobs/briefing_2026_03_25/publish-package
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
部署完成後，可至 GCP Cloud Scheduler 建立每日清晨定時 POST 至 `/jobs/daily-briefing/start` 與後續 `/jobs/{job_id}/poll` 的工作排程。會產生成本或改變狀態的 endpoint 需提供 `X-Admin-Token`。

## 錯誤處理與重試 (Idempotency)
系統透過 Firestore 的 `jobs` Collection 確保 `job_id` 的唯一性，防止重複產出，確保每日只產出一份報告。執行進度、Google Doc、音訊、審稿資訊與發佈包皆會被即時存入表中。

## 營運與品質控管
新聞來源、整體流程與品質確認方式請見 [docs/operating_model.md](docs/operating_model.md)。
