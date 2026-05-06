# Signal Brief Pipeline Plan

This document captures the full pipeline from RSS source registry to editorial briefing. It is the single source of truth for phases, current status, and what is queued.

## Phase Overview

| Phase | Scope | Status |
|---|---|---|
| 1 | RSS pipeline v1 — sync, ingest, observation report | Done, in production |
| 2 | Signal clustering — embeddings + Agglomerative clustering | Done, in production |
| 3 | Cross-verification + importance judgement | Code done, prompt iterating, backfill in progress |
| 4 | Business impact reasoning + editorial briefing | Outline |
| 5 | Integration with existing daily briefing flow | Outline |
| 6 | Tier 1 source expansion (immediate, RSS adds) | Adopted, do alongside Phase 3–5 |
| 7 | Tier 2 collection (watchlist, RSSHub routes, X / Reddit) | Outline, after Phase 4 |
| 8 | Tier 3 collection (active research, structured APIs, alt data) | Outline, after Phase 5 |
| 9 | Tier 4 paid data (Bloomberg, Refinitiv, etc.) | Deferred until paying customers |

Each phase must satisfy its completion criteria before the next phase starts. Backlog items can run alongside.

---

## Phase 1 — RSS Pipeline v1 (Done)

### Capabilities

1. Google Sheet sync
   - FastAPI reads the Google Sheet source registry.
   - Sources are synced into Firestore `rss_sources` via batch writes.
   - Only rows from `RSS List` whose `狀態` is `✅ OK (200)` are fetchable for ingest.
   - Sources removed from the Sheet are marked non-fetchable in Firestore.

2. RSS ingest
   - n8n triggers ingest every 30 minutes (W2).
   - Ingest fetches feeds concurrently with `httpx`, default 10-second per-feed timeout.
   - Items filtered by `published_at`, falling back to `first_seen_at`.
   - Each run writes a `rss_ingest_runs` record with per-source status and counts.

3. RSS item storage
   - Each item stores source metadata, title, URL, GUID, summary, publish time, first/last seen time, content hash.
   - Dedupe on `source_id + guid/url/content_hash`.
   - Item writes use batch read/write for new vs update counts.

4. RSS observation
   - APIs return recent items, source health, and a 24h signal observation report.
   - Reports include source coverage, freshness, per-source counts, top title terms, possible duplicate topics.
   - Observation reports do not produce investment recommendations or final importance ranking.

### Production Status

| Metric | Value |
|---|---|
| FastAPI service | `https://informative-ai.zeabur.app` (Zeabur) |
| n8n service | `https://easonnn.zeabur.app` (Zeabur, 2C / 4GB Tencent Singapore) |
| GitHub repo | `https://github.com/1121eason/podcast-project` |
| Source pool | 262 |
| Fetchable | 127 (after Apps Script re-check on 2026-05-06) |
| Ingest cycle | Every 30 minutes |
| Avg new items / 30min | 40–80 |
| Source coverage ratio | ~65–70% |

### n8n Workflows

- **W1 Sheet Sync** — every 12h → `POST /sources/sheets/sync` → Google Sheet `Sync_Log` tab
- **W2 RSS Ingest** — every 30m → `POST /sources/rss/ingest` → `Ingest_Log` tab
- **W3 Daily Report** — daily 08:00 → `GET /sources/rss/signal-report` → `Daily_Report` tab

### APIs

- `POST /sources/sheets/sync` (admin token)
- `POST /sources/rss/ingest` (admin token, body: `limit_sources`, `max_workers`, `timeout_seconds`, `since_hours`)
- `GET /sources/rss/health`
- `GET /sources/rss/items?since_hours=24`
- `GET /sources/rss/signal-report?since_hours=24`

### Firestore Collections

- `rss_sources` — source metadata + per-source ingest status
- `rss_items` — collected RSS items with first/last seen timestamps
- `rss_ingest_runs` — ingest run metadata, counts, per-source results

### Outstanding Phase 1 Hygiene (non-blocking)

- Rotate three secrets that were exposed during this build conversation: GCP service account key, OAuth client secret, ADMIN_TOKEN.
- Silent source pruning — sources with zero output for one week should be marked non-fetchable in the Sheet.
- Flaky source pruning — ~14 sources that recovered in Apps Script health check but consistently fail at ingest time.

---

## Phase 2 — Signal Clustering (Done)

### Goal

Group RSS items that describe the same event into one signal cluster.

```
~3000 items / day → ~200 signal clusters / day
```

### Capabilities

1. Embedding generation
   - Vertex AI `text-embedding-004` (768 dims).
   - Lazy embedding: items get embedded on first cluster run, then cached in `rss_items.embedding`.
   - Cost: ~$0.00003 per item, ~$3/month at current volume.

2. Clustering
   - `AgglomerativeClustering` with cosine distance, threshold 0.15, `linkage='average'`.
   - Each cluster picks the centroid-nearest item as representative.
   - Window: last 4 hours.
   - Cluster aggregates publishers, desks, market_levels, categories.

3. Schedule (sliding window)
   - W4 runs every 1 hour with `window_hours=4`.
   - Each item gets re-clustered up to 4 times before exiting the window — final `signal_id` is from the latest run.
   - Overlap is acceptable since embedding is cached and Firestore writes are cheap.

### Production Status

| Metric | Value |
|---|---|
| Avg multi-source ratio | 21–24% (target ≥20%) |
| Avg duration / run | 23–25s |
| Avg cluster count / run | 460 |
| Avg multi-source clusters / run | ~100 |
| Embedding cost (after warm-up) | ~$0/run (cache hit rate near 100%) |

### Code Layout

- `app/clients/embedding_client.py` — Vertex embedding wrapper, batch 100, retry x3, max 2048 chars per text
- `app/services/rss_embedding_service.py` — HTML strip, batch embed, cache writeback
- `app/services/rss_clustering_service.py` — pull items, cluster, write signals + clustering run
- `app/api/routes_signals.py` — `/signals/cluster`, `/signals/embed`, `/signals/recent`, `/signals/{id}`, `/signals/runs/clustering`
- `app/models/signal.py` — `RssSignal`, `RssClusteringRun`
- `app/models/rss.py` — `RssItem` extended with `embedding`, `embedding_model`, `embedded_at`, `signal_id`

### Firestore Collections (added)

- `rss_signals` — clusters with representative + members
- `rss_clustering_runs` — clustering run metadata

### n8n Workflow 4

- W4 Clustering — every 1h → `POST /signals/cluster {"window_hours": 4}` → `Clustering_Log` tab

### Settings

- `VERTEX_LOCATION=us-central1`
- `EMBEDDING_MODEL=text-embedding-004`
- `CLUSTERING_DISTANCE_THRESHOLD=0.15`

### Verification Acceptance (target, monitor for one week)

- multi-source cluster ratio ≥ 20% rolling 6-run average
- 30-cluster manual sample → ≥ 24 correct (80% precision)
- 0 run failures
- avg duration < 30s

---

## Phase 3 — Cross-verification + Importance Judgement (Designed)

### Goal

For each cluster from Phase 2, attach:

1. `cluster_status` — rule-based: `single_source` | `partially_supported` | `confirmed` | `regional_only`
2. `topic_heat` — rule-based: `low` | `medium` | `high` | `viral`
3. `importance_score` — LLM-based, 0–100
4. `impact_type` — LLM-based: `market` | `policy` | `corporate` | `tech` | `industry` | `macro` | `noise`
5. `key_entities`, `regions`, `reasoning`, `heat_vs_importance_note` — LLM-based

The two dimensions are kept orthogonal: viral topics (e.g. celebrity divorces) can score low importance; single-source scoops (e.g. a WSJ exclusive) can score high.

### Cross-verification Rules

Publishers are grouped into independent ecosystems (`western_finance`, `western_general`, `us_business`, `us_tech`, `tw_finance`, `tw_general`, `europe_general`, `asia_finance`). Cross-verification counts independent groups, not raw publisher count.

```
single_source         : sources == 1
confirmed             : sources >= 3 AND independent_groups >= 3
confirmed             : sources >= 3 AND "Global" in markets AND independent_groups >= 2
regional_only         : sources >= 3 AND single market and not Global
partially_supported   : everything else with sources >= 2
```

### Topic Heat Rules

```
viral   : sources >= 5 AND publishers >= 4
high    : sources >= 3 AND publishers >= 3
medium  : sources >= 2
low     : sources == 1
```

### Importance Prompt Strategy

Prompt explicitly says "many reports does not equal important" and provides `topic_heat` as reference, not a driver. Output requires a `heat_vs_importance_note` whenever the LLM diverges from heat.

Model: `gemini-2.5-pro`.

### Cost Estimate

- ~$0.001625 per signal (500 input + 100 output tokens)
- 200 signals / day → ~$0.32 / day → ~$10 / month
- Decision: judge all clusters including `single_source` (filters real noise from real exclusives)

### APIs (planned)

- `POST /signals/verify` — rule-based, fast
- `POST /signals/judge` — LLM, batched
- `GET /signals/top?since_hours=24&min_score=60`
- `GET /signals/by-status?status=confirmed&since_hours=24`
- `GET /signals/runs/judgement?since_hours=48`

### n8n Workflow 5 (planned)

- W5 Judge — every 1h at :30 → `POST /signals/verify` → `POST /signals/judge {"since_hours": 4}` → `Judgement_Log` tab

### Acceptance (target, after one week of operation)

| Metric | Target |
|---|---|
| Score >= 80 share | 1–8% |
| Score >= 60 share | 5–20% |
| Noise share | < 30% |
| Failed-judgement rate | < 5% |
| Avg judge duration / signal | < 8s |
| Daily cost | < $0.50 |
| 20-sample of score >= 80, manual sample agree "important" | >= 16 / 20 |
| 20-sample of score < 20, manual sample agree "noise" | >= 18 / 20 |

### Open Decisions

These three are pending before development starts:

1. Judge all clusters or only non-single_source. **Recommended: all.**
2. W4 at :00 / W5 at :30 cadence. **Recommended.**
3. Run a one-time backfill on existing un-judged signals at first deploy. **Recommended.**

---

## Phase 4 — Business Impact + Editorial Briefing (Outline)

### Goal

Convert score >= 60 signals into reader-ready briefing copy.

### Components

1. Business impact reasoning per high-importance signal:
   - `impacted_sectors`, `impacted_assets`, `regions`, `watch_points`
   - `counterfactual` (opposing view)
   - `gap` (what primary source / data is missing)

2. Daily editorial briefing generator:
   - 1 overview paragraph
   - 5–10 signal sections (~200 words each)
   - Each section: what happened, why it matters, who is affected, next watch point
   - Closing: today's signal pool health summary

### Models

- `gemini-2.5-pro` for impact reasoning + briefing generation
- Prompt module: `business_impact_v1`, `editorial_briefing_v2`

### Acceptance

- One full daily briefing generated end-to-end without manual intervention
- Operator (you) edits less than 30% of generated text on average
- Generated briefing references at least 5 source URLs per section

---

## Phase 5 — Integration with Daily Briefing Flow (Outline)

### Goal

Route Phase 4 output into the existing Google Doc draft → human review → approve → audio → publish package pipeline.

### Plan

- `/jobs/daily-briefing/start` reads Phase 4 editorial briefing instead of running `research_v1`.
- `polling_service` becomes a no-op or a simple wait for human approval.
- `docs_writer_service` writes the Phase 4 output into a Google Doc.
- Existing `approve` → `audio` → `publish_package` flow stays unchanged.

No new code modules. Service-layer rewiring only.

---

## Information Collection Strategy

This section captures the long-horizon plan for what data we collect, why, and how. The current system (Phase 1+2) only sees what its 127 RSS sources publish; everything beyond that is a known blind spot. The strategy is layered into four tiers by cost / effort / value, and supplemented with a governance layer.

### Current State Inventory

127 fetchable RSS sources roughly distributed as:
- Western finance (Reuters / Bloomberg / WSJ / FT / CNBC / MarketWatch): ~30%
- Western general (NYT / BBC / Guardian / AP): ~15%
- Taiwan finance (鉅亨 / MoneyDJ / 經濟日報 / Digitimes): ~25%
- Taiwan general (中央社 / 天下 / Yahoo奇摩): ~10%
- Asia finance (Nikkei / 香港經濟日報 / RTHK): ~10%
- Europe general (Le Monde / Economist): ~5%
- Other: ~5%

Known blind spots:
- Official primary sources (Fed, SEC, TWSE, 公開資訊觀測站): media lag 30 min – 6 hours.
- Government regulation original text.
- Industry hard data (monthly revenue, BLS jobs, ISM PMI, semiconductor shipments).
- Tech / research (arXiv, CVE, framework releases).
- Breaking events that surface on Twitter / Reddit / HN before media coverage.
- Cross-domain weak signals (e.g. Indonesia nickel policy → EV battery supply chain → Tesla).
- Paid-only data (Bloomberg Terminal, Refinitiv, alternative data).

---

## Phase 6 — Tier 1: Immediate Source Expansion (Adopted, Option A)

Cost 0, effort low, value high. Stay inside the existing RSS pipeline. Two paths: add official RSS / Atom feeds directly to the Google Sheet, or use the self-hosted RSSHub (`easonn.zeabur.app`) to convert non-RSS sites into feeds.

### T1.1 Official primary sources

| Source | Feed URL or note | Why |
|---|---|---|
| Federal Reserve | `federalreserve.gov/feeds/press_all.xml` | Most important global central bank decisions |
| ECB Press Releases | RSS via ECB site | Eurozone monetary policy |
| SEC EDGAR | `sec.gov/cgi-bin/browse-edgar?action=getcurrent&output=atom` | US public-company 8-K / 10-Q in real time |
| 公開資訊觀測站 | RSSHub adapter | Taiwan public-company filings |
| TWSE 重大訊息 | RSSHub adapter | Taiwan stock exchange disclosures |
| White House Briefing Room | `whitehouse.gov/briefing-room/feed/` | US executive policy original text |
| EU Commission Press | `ec.europa.eu/commission/presscorner/api/rss` | EU regulation |
| BLS news releases | `bls.gov/feed/news_release/all_nr.rss` | US employment / inflation data |

### T1.2 Tech and research

| Source | URL | Use |
|---|---|---|
| Hacker News top | `news.ycombinator.com/rss` | Tech-community attention signal |
| arXiv cs.AI | `export.arxiv.org/rss/cs.AI` | New AI papers |
| arXiv cs.CR | `export.arxiv.org/rss/cs.CR` | Security research |
| GitHub trending | RSSHub adapter | New popular projects |
| The Verge | `theverge.com/rss/index.xml` | Consumer tech |
| Ars Technica | `arstechnica.com/feed/` | Deeper tech coverage |

### T1.3 Source pool hygiene

- Remove 14 flaky sources (recovered in Apps Script health check but consistently fail at ingest).
- Mark silent sources (zero output for one week) as non-fetchable.
- Net effect: fetchable count drops from 127 to ~110, but signal quality rises.

### Tier 1 cost

$0 dollars, half a day of operator effort, ~25 new high-value sources, ~17 source removals. Net source quality up.

---

## Phase 7 — Tier 2: Mid-term Collection (1–2 weeks of dev each)

These add new mechanisms, not just sources. Pick up after Phase 4 ships.

### T2.1 Watchlist (explicit must-answer questions)

A list of questions the system must answer or flag every day. Examples:

- Did TSMC release monthly revenue today?
- Are there any Fed / ECB / BoJ public speeches this week?
- What was last Thursday's Initial Jobless Claims?
- Is FOMC scheduled today?
- Which S&P 500 companies report earnings this week?
- Did Apple / NVIDIA / TSMC release any major announcements today?
- Did the EU AI Act publish a new amendment?

Each watchlist item is a tuple of `(source_type, source_url, expected_pattern, response_schema)`. A scheduler runs every 1–4 hours, hits the source, extracts a structured response, and writes to `watchlist_responses`. "No update" is also a recorded response.

Output: a daily "Watchlist Daily" report listing each question and its current answer (or absence thereof).

Estimated dev: 1–2 weeks. LLM cost: ~$5/month.

### T2.2 Self-hosted RSSHub route extensions

Convert sites that don't publish RSS into feeds. Targets:
- 公開資訊觀測站 (Taiwan public filings)
- 台灣經濟部 / 金管會 / 央行
- 香港交易所 disclosures
- 中國證監會 announcements

Each route ~1–2 hours dev. Operator effort 5–10 hours total.

### T2.3 Twitter / X account watch

Lock onto specific accounts: official handles (@federalreserve, @SECGov, @Treasury, @ECB), policy figures (@Yellen, @realDonaldTrump), key journalists (@DealBook, @WSJecon, @FTAlphaville), top PMs / analysts (curated 5–10).

Options:
- Paid X API: $100+/month, reliable.
- Free: nitter mirrors converted to RSS via RSSHub.

Decision deferred until X API budget warrants the latency improvement (currently RSS sources cover the same news 30–60 min later).

### T2.4 Reddit / HN trending

- `r/wallstreetbets`, `r/economics`, `r/investing`, `r/technology` top RSS feeds.
- Already partly covered by Tier 1 HN. Reddit feeds add retail-investor sentiment and tech-community attention.

---

## Phase 8 — Tier 3: Longer-term Collection (3–4 weeks of dev each, requires stable foundation)

Only useful after Phase 5 (full editorial pipeline) ships and is stable.

### T3.1 Active research (editor-in-chief mode)

Each morning:
1. Show Gemini today's RSS-derived clusters (~200).
2. Ask Gemini: "What should be tracked today that this list does not cover?"
3. For each missing topic Gemini proposes, run Gemini with Search Grounding to find the answer.
4. Convert findings into synthetic signals and merge with the RSS signal pool.

Cost: $10–30/month (Search Grounding + Gemini Pro). Defer until Phase 5 ships and routine costs are stable.

### T3.2 Structured data APIs (numbers, not text)

| API | Use | Cost |
|---|---|---|
| FRED API | US macro time series (rates, GDP, CPI, employment) | Free |
| Yahoo Finance / Stooq | Equities prices | Free |
| TWSE / TPEx API | Taiwan stock data | Free |
| Coingecko | Crypto | Free |
| Alpha Vantage / IEX | US equities real-time | Free tier |

Goal: pair each event signal with same-day market reaction. Lets you read "how much was already priced in" alongside the news itself.

### T3.3 Alternative data (high cost, high signal)

| Source | Use | Cost |
|---|---|---|
| Planet Labs (satellite) | Parking-lot traffic, port activity | $$$$ |
| Glassnode (on-chain) | Crypto whale movements | $200+/month |
| Second Measure (credit card) | Real consumer spend trends | $$$$ |
| Apptopia (app downloads) | Product health proxy | $$ |

Listed for awareness only. Defer until clear use case + budget approval.

### T3.4 Cross-language coverage gaps

Current pipeline is English + Traditional Chinese heavy. Possible additions:
- Mainland China: 21 世紀經濟報導 / 財新 / 新華社 (via RSSHub)
- Non-English Europe: Handelsblatt / FAZ
- Korea: Yonhap economy
- Southeast Asia: The Straits Times / Nikkei Asia

Precondition: operator can read or trust the language. Skip unless someone reviews routinely.

---

## Phase 9 — Tier 4: Paid Data (Executive Decision)

| Source | Approx cost | Use |
|---|---|---|
| Bloomberg Terminal | $24,000/year | First-hand news, real-time data, analyst reports |
| Refinitiv Eikon | similar | Bloomberg competitor |
| S&P Capital IQ | $$$ | Deep company financials |
| FactSet | $$$ | Same as above |
| The Information | $$/month | Tech exclusives |
| Bloomberg Pro subscription | $40/month | Cheapest Bloomberg entry |

Not on the roadmap until MVP has paying customers. The constraint today is "too much information to process," not "not enough information."

---

## Governance Layer (cross-cutting, applies to all tiers)

### G.1 Source rating

Add fields to the Google Sheet `RSS List`:

| Field | Meaning |
|---|---|
| `tier` | 1 (primary) / 2 (media) / 3 (small / mirror) |
| `desk` | Market / Tech / Policy / Industry |
| `expected_cadence` | daily / weekly / monthly / event-driven |
| `bias_note` | known orientation (left / right / industry skew) |

Importance judgement should weight tier 1 sources higher than tier 3 for the same content.

### G.2 Noise blacklist

Pattern-based deweighting:
- Title contains "業配" / "廣編" / "advertorial" → cap importance at 0.
- Publisher on a known low-quality list → cap at 30.
- Title is a digest / roundup ("快訊整理", "今日要聞") → cap at 50.

### G.3 Source rotation cycle

Weekly review, automated where possible:
- Silent sources (>7 days zero output) → flag for removal.
- Flaky sources (>7 days >50% ingest fail rate) → flag for removal.
- New-source trial (added in last 14 days) → keep / drop decision.

Add `review_status` column to the Sheet.

### G.4 Coverage heatmap

Daily Report adds a section:

```
Today desk coverage:
  Macro/Policy:    25 events  ← healthy
  Corporate (US):  80 events  ← healthy
  Corporate (TW):  60 events  ← healthy
  Tech:            30 events
  Industry:        15 events  ← low, consider adding sources
  Asia (ex TW):     5 events  ← critically low, missing Nikkei/SCMP/Yonhap
  Europe:           3 events  ← critically low, missing Le Monde/FAZ
```

Reviewed weekly; gaps trigger Tier 1 / 2 source additions.

---

## Phase Hard Limits (after all tiers)

Even with everything above implemented, the following remain unobservable without paid data or human network:
- Internal company information before public disclosure.
- Bloomberg Terminal exclusives that never leak to public web.
- True leading indicators (satellite, on-chain, credit card flow).
- The intent behind why a story is breaking now versus six months ago.

These are the boundaries. Acknowledge them; do not pretend the pipeline can fill them.

---

## Action Sequencing

| Window | Focus |
|---|---|
| This week (Phase 3 wrap) | T1.1 + T1.2 (add ~25 RSS sources), T1.3 (prune flaky / silent) |
| Next week (Phase 4 dev) | T2.2 (RSSHub routes), G.1 (source rating fields) |
| After Phase 4 ships | T2.1 Watchlist, T3.2 structured data APIs |
| After Phase 5 ships | T3.1 active research, T2.3 X watch (if budget allows) |
| TBD by paying-customer milestone | Phase 9 Tier 4 paid data |

---

## n8n Workflow Map (Production)

| ID | Name | Cadence | Endpoint | Sheet Tab |
|---|---|---|---|---|
| W1 | Sheet Sync | 12h | `POST /sources/sheets/sync` | Sync_Log |
| W2 | RSS Ingest | 30m | `POST /sources/rss/ingest` | Ingest_Log |
| W3 | Daily Report | 08:00 daily | `GET /sources/rss/signal-report` | Daily_Report |
| W4 | Clustering | 1h | `POST /signals/cluster` | Clustering_Log |
| W5 | Verify + Judge | 1h at :30 | `POST /signals/verify` then `POST /signals/judge` | Judgement_Log |

Workflows 1–4 are live. W5 is planned for Phase 3.

---

## Operating Principles

1. RSS frequency is not importance. Source health is operational only.
2. Topic heat (how many sources reported) and importance (real impact) are separate dimensions.
3. Each phase passes acceptance before the next phase starts. Backlog phase 6 runs alongside.
4. Cost is monitored per phase. Phases 1–2 run effectively free; Phase 3 budgets ~$10/month; Phase 4+ TBD.
5. Manual sampling is a required acceptance gate, not optional. LLM-only validation is insufficient.

---

## AI Model Strategy

- `gemini-2.5-flash` — RSS cleanup, classification, low-cost batch ops (none in current production yet)
- `gemini-2.5-pro` — cross-verification reasoning, importance judgement, business impact, editorial briefing
- `text-embedding-004` (Vertex) — clustering embeddings (live in Phase 2)

OpenAI A/B is possible but not required. Default stays on Google given the existing GCP / Vertex / Firestore stack.

---

## Decision Log

| Date | Decision | Rationale |
|---|---|---|
| 2026-05-05 | Run RSS pipeline v1 in production | Source pool stable enough for downstream phases |
| 2026-05-06 | Sheet sync schedule corrected to 12h (was 1h) | Apps Script only updates state every 12h |
| 2026-05-06 | Phase 2 deployed with threshold 0.15, window 4h, every 4h schedule | Lower latency than every-day, no overlap |
| 2026-05-07 | Switch Phase 2 to every 1h with 4h window (overlap) | New items reach clusters within 1h instead of 4h |
| 2026-05-07 | Phase 3 plan finalized; topic_heat added as second dimension separate from cluster_status | Avoids conflating "popular" with "important" |
| 2026-05-07 | Phase 6 (source expansion) adopted as Option A only | Cheapest, simplest, aligned with existing pipeline |
| 2026-05-07 | Phase 3 prompt v1 deployed; small-batch test showed event-vs-context mis-anchoring | LLM scored a market-wrap article 90 because body mentioned Iran |
| 2026-05-07 | Phase 3 v2 (prompt restructure) insufficient; LLM still ignored explicit rule | Need code-level enforcement, not just prompt instruction |
| 2026-05-07 | Phase 3 v3 (prompt v2 + code guard rails) shipped: market-wrap regex caps importance ≤ 45; non-systemic single-source earnings caps ≤ 65; summary truncated 1000 → 300 chars | Validated by re-judge: 歐股盤後 dropped out of top60, Fortinet 72→65 |
| 2026-05-07 | Information collection strategy expanded into tiered roadmap (Phase 6/7/8/9) | Captures full long-horizon plan; previous Phase 6 was too narrow |

---

## Glossary

- **Source** — a row in `RSS List` Google Sheet with a feed URL.
- **Item** — a single article fetched from a source.
- **Signal / Cluster** — a group of items the embedding pipeline grouped together, representing the same event or topic.
- **cluster_status** — degree of independent multi-source confirmation (rule-based).
- **topic_heat** — discussion volume across sources (rule-based).
- **importance_score** — LLM-judged real-world importance, independent of heat.
- **Window** — the time range a clustering run looks at (default 4h).
- **Backfill** — one-time re-processing of historical signals when a new judging stage launches.
