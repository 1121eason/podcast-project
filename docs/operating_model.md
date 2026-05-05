# Signal Brief Operating Model

## 1. 新聞來源目前怎麼產生

目前 MVP 沒有獨立的 RSS crawler、News API 或人工來源清單。

來源流程是：

1. `research_v1.txt` 要求 Gemini 產出投資/商務決策用研究包。
2. `ResearchOutputSchema` 強制每個 `top_developments` 都包含 `sources`。
3. Gemini 回傳 JSON，系統做 schema validation。
4. `publish_package_service` 從 `top_developments[].sources` 與 `source_categories` 收集、去重，放進 `publish_package.source_links`。

因此目前的來源是「模型研究輸出的一部分」，不是「系統先抓取並驗證過的來源」。這能快速跑 MVP，但來源可能有三個風險：

- URL 可能不存在或指到不精準頁面。
- 來源可能不足以支持文中的判斷。
- 模型可能遺漏更權威的一手來源。

V2 建議把來源改成顯式 pipeline：

1. 先定義 source universe：官方公告、央行/監管機構、公司 IR、主要財經媒體、國際通訊社、產業研究。
2. 系統先抓候選事件與來源。
3. 模型只負責排序、摘要與商務含義。
4. 發佈前檢查每個事件至少有 2 個來源，其中高風險事件至少 1 個一手來源。

## 2. 目前整體流程

1. `POST /jobs/daily-briefing/start`
   - 建立 Firestore job。
   - 載入 `research_v1.txt`。
   - Gemini 產生結構化研究 JSON。
   - job 進入 `normalizing`。

2. `POST /jobs/{job_id}/poll`
   - 將研究 JSON 正規化並驗證 schema。
   - 用 `editorial_v1.txt` 產生 Google Doc briefing 草稿。
   - 寫入 Google Doc。
   - job 停在 `pending_review`。

3. 人工審稿
   - 編輯 Google Doc。
   - 檢查事件選擇、事實、語氣、來源、商務含義。

4. `POST /jobs/{job_id}/approve`
   - 讀回審稿後 Google Doc。
   - 用 `podcast_v1.txt` 產生 podcast script。
   - Text-to-Speech 產生 MP3。
   - 上傳 Drive。
   - 產生 `publish_package`。
   - job 進入 `completed`。

## 3. 品質如何確認

MVP 採「機器檢查 + 人工審稿」。

機器檢查在 `publish_package.quality_report`：

- 是否有審稿後 briefing。
- 是否有 podcast script。
- 是否至少 3 個 high-signal developments。
- 是否至少 5 個 unique source links。
- 每個事件是否都有 sources。
- 每個事件是否都有 business implication。
- 每個事件是否都有合法 confidence level。

人工審稿 checklist：

- 事件是否真的影響投資、商務策略、供應鏈、市場進入或競爭格局。
- 標題是否沒有誇大。
- 內容是否避免投資建議化。
- 每個事件是否能回答「為什麼現在重要」。
- 來源是否可打開，且足以支持關鍵敘述。
- 低信心事件是否有明確標記或被降級。
- Podcast script 是否適合口播，不只是照念條列。

發佈門檻：

- `quality_report.status` 最好是 `pass`。
- 若是 `needs_review`，人工審稿者必須確認 warnings 可接受。
- 任何來源無法打開、重大事實不確定、或內容像投資建議時，不發佈。
