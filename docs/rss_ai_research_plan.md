# RSSHub Source Pipeline v1 + AI Research Layer v2 Plan

## Summary

This document defines the next Signal Brief source pipeline. RSS v1 is an implementation target: it creates a stable market-signal observation layer from Google Sheet managed RSS sources. AI Research Layer v2 comes after the RSS pipeline is stable and is responsible for cross-verification, importance judgement, business-impact reasoning, gap research, and primary-source enrichment.

RSS does not directly represent news importance. The Google Sheet status only represents whether RSSHub or a feed can be read successfully.

## Current Google Sheet

Apps Script already checks RSS health every 12 hours and writes status and detection logs back to Google Sheet.

The current source registry columns are:

- `ID`
- `市場等級`
- `資料來源`
- `類別`
- `分類`
- `中文名稱`
- `精簡說明（可看到的新聞內容）`
- `RSS URL`
- `狀態`
- `上次偵測時間`

Rules:

- `狀態` only means whether the RSS feed is readable.
- `上次偵測時間` only means when Apps Script last checked the feed.
- These two fields must not be used as news importance scores.
- Source stability does not mean a source or an item is more important.

## RSS Pipeline v1

RSS v1 adds these implemented capabilities:

1. Google Sheet sync
   - FastAPI reads the Google Sheet source registry.
   - Sources are synced into Firestore `rss_sources`.
   - Sync uses Firestore batch writes.
   - Rows without `RSS URL` are skipped.
   - Only rows from the `RSS List` sheet whose `狀態` value is exactly `✅ OK (200)` are fetchable for ingest.
   - Non-OK feeds keep metadata but do not block the sync.
   - Sources removed from the Sheet are marked non-fetchable in Firestore.

2. RSS ingest
   - n8n should trigger ingest every 15-30 minutes.
   - Daily-only ingest is not enough because many RSS feeds expose a limited item window.
   - Ingest reads fetchable sources from Firestore and writes items into `rss_items`.
   - Ingest fetches feeds concurrently with `httpx`, with a default 10-second per-feed timeout.
   - Ingest filters items by `published_at` when available, falling back to `first_seen_at`.
   - Each run writes a `rss_ingest_runs` record.
   - Each run records per-source status, duration, fetch duration, write duration, item count, skipped old item count, new/update count, and errors.
   - Each source's latest ingest metadata is written back to `rss_sources`.

3. RSS item storage
   - Each item stores source metadata, title, URL, GUID, summary, publish time, first seen time, last seen time, and content hash.
   - Dedupe uses `source_id + guid/url/content_hash`.
   - Item writes use batch read/write to preserve new/update counts without per-item round trips.

4. RSS observation
   - The API can return recent RSS items, source health, and a 24-hour signal observation report.
   - Reports include source coverage, freshness, per-source item counts, top title terms, and possible duplicate topics.
   - Observation reports describe discussion direction only.
   - Observation reports intentionally do not produce investment recommendations or final importance ranking.

## n8n Role

n8n is the orchestration layer. It should not make editorial, ranking, verification, or business-impact decisions.

Recommended workflows:

- Every 12 hours, after Apps Script updates the Google Sheet, call `POST /sources/sheets/sync`.
- Every 15-30 minutes, call `POST /sources/rss/ingest`.
- Daily, call `GET /sources/rss/signal-report?since_hours=24`.
- The existing daily briefing flow can still be triggered separately with `start`, `poll`, and `approve`.

## APIs

RSS v1 exposes:

- `POST /sources/sheets/sync`
  - Syncs Google Sheet sources into Firestore.
  - Requires `X-Admin-Token`.

- `POST /sources/rss/ingest`
  - Fetches RSS items and stores them in Firestore.
  - Requires `X-Admin-Token`.
  - Optional body: `limit_sources`, `include_unhealthy`, `max_workers`, `timeout_seconds`, `since_hours`.

- `GET /sources/rss/health`
  - Returns source health summary.

- `GET /sources/rss/items?since_hours=24`
  - Returns recently collected RSS items.

- `GET /sources/rss/signal-report?since_hours=24`
  - Returns a market-signal observation report.

## Setup Notes

- Set `GOOGLE_SHEET_ID` to the spreadsheet ID from the Google Sheet URL.
- Keep `GOOGLE_SHEET_RANGE` as `'RSS List'!A:J`.
- RSS ingest only fetches rows where column I / `狀態` is exactly `✅ OK (200)`.
- Google Workspace OAuth now needs the Sheets readonly scope. After pulling this version, rerun `python3 scripts/authorize_google_workspace.py` so the local token includes Google Sheets access.

## Firestore Collections

RSS v1 uses:

- `rss_sources`
  - Source metadata from Google Sheet.
  - Includes feed health information from Apps Script.
  - Includes latest ingest status, duration, item counts, and consecutive failure count.

- `rss_items`
  - Collected RSS items.
  - Stores first and last seen timestamps for dedupe and observation.

- `rss_ingest_runs`
  - Ingest run metadata, counts, and error summaries.

## AI Research Layer v2

AI Research Layer v2 is introduced after RSS v1 is stable. RSS remains a market-signal input, not the final decision engine.

AI research responsibilities:

- Cross-verification
- Importance judgement
- Business-impact reasoning
- Gap research
- Primary-source enrichment

Methodology:

1. Signal clustering
   - Groups RSS items into the same event, policy signal, or industry trend.

2. Cross-verification
   - Checks whether clusters are supported by multiple sources.
   - Produces `confirmed`, `partially_supported`, `single_source`, or `needs_manual_review`.

3. Primary-source enrichment
   - For high-importance candidates, looks for official sources, company releases, regulator documents, exchange filings, earnings materials, or statistics.

4. Importance judgement
   - Judges business and investment decision value.
   - RSS frequency can be an observation signal, but not an importance score.

5. Business-impact reasoning
   - Explains affected groups, business implication, impacted industries/regions/assets, and next watch points.

6. Gap research
   - Flags missing primary sources, missing opposing views, missing data support, and source bias.

## AI Model Strategy

The default v2 stack stays with Google because the current MVP already uses Gemini, Google Docs, Drive, and Firestore.

- `gemini-2.5-flash`
  - RSS cleanup
  - Classification
  - Initial clustering
  - Large-volume low-cost processing

- `gemini-2.5-pro`
  - Cross-verification
  - Importance judgement
  - Business-impact reasoning
  - Briefing generation

Prompt modules:

- `signal_clustering_v1`
- `verification_v1`
- `importance_judgement_v1`
- `business_impact_v1`
- `editorial_briefing_v2`

OpenAI / Gemini A/B tests can be added later, but they are not required for RSS v1.

## Output Locations

- Firestore
  - RSS items
  - Source metadata
  - Ingest logs
  - Future AI research output

- Google Doc
  - Human review briefing
  - Research Notes
  - Source gaps
  - Confidence and verification status

- Publish Package
  - Public upload material
  - Source links
  - Audio URL
  - Doc URL
  - Quality report

- Google Sheet
  - RSS source registry and health status only
  - No AI importance judgement

## Test Plan

- Google Sheet row parsing.
- RSS source sync.
- RSS item dedupe.
- Broken feed does not block the whole ingest run.
- Recent RSS item query.
- `X-Admin-Token` auth on mutating endpoints.
- RSS status does not influence news importance.
- High-frequency RSS clusters do not automatically become high importance.
- Single-source events are marked `single_source` or downgraded in confidence in AI v2.
- High-importance events without primary sources are marked `needs_manual_review` in AI v2.

## Assumptions

- Apps Script owns RSS health checks and updates `狀態` and `上次偵測時間`.
- Google Sheet columns remain unchanged for RSS v1.
- RSS v1 implements the data pipeline and observation report first.
- AI Research Layer v2 is introduced after RSS v1 is stable.
- The existing Google Doc review and approve/audio/publish package flow remains unchanged.
