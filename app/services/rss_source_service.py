from datetime import datetime, timezone
from collections import Counter
import hashlib

from app.clients.firestore_client import firestore_client
from app.clients.sheets_client import SheetsClient
from app.models.rss import RssSource


HEADER_ID = "ID"
HEADER_MARKET_LEVEL = "市場等級"
HEADER_PUBLISHER = "資料來源"
HEADER_DESK = "類別"
HEADER_CATEGORY = "分類"
HEADER_ZH_NAME = "中文名稱"
HEADER_DESCRIPTION = "精簡說明（可看到的新聞內容）"
HEADER_FEED_URL = "RSS URL"
HEADER_STATUS = "狀態"
HEADER_LAST_CHECKED_AT = "上次偵測時間"
FETCHABLE_STATUS = "✅ OK (200)"
FETCHABLE_STATUSES = {FETCHABLE_STATUS, "200"}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _clean(value: object) -> str:
    return str(value or "").strip()


def _source_id_from_feed_url(feed_url: str) -> str:
    digest = hashlib.sha256(feed_url.encode("utf-8")).hexdigest()[:16]
    return f"rss_{digest}"


def _source_id_suffix(feed_url: str) -> str:
    return hashlib.sha256(feed_url.encode("utf-8")).hexdigest()[:8]


def classify_health_status(raw_status: str) -> tuple[str, bool]:
    raw_status = _clean(raw_status)
    if raw_status in FETCHABLE_STATUSES:
        return "stable", True

    status = raw_status.lower()
    if not status:
        return "unknown", False

    failure_tokens = [
        "失敗",
        "錯誤",
        "不可",
        "failed",
        "fail",
        "error",
        "timeout",
        "404",
        "500",
        "502",
        "503",
    ]

    if any(token in status for token in failure_tokens):
        return "broken", False
    return "not_ok", False


def parse_sheet_source_rows(rows: list[list[str]], synced_at: str | None = None) -> list[RssSource]:
    if not rows:
        return []

    header_index = None
    for index, row in enumerate(rows):
        if HEADER_FEED_URL in row:
            header_index = index
            break

    if header_index is None:
        raise ValueError("Google Sheet source registry must include an RSS URL header.")

    headers = [_clean(header) for header in rows[header_index]]
    synced_at = synced_at or utc_now_iso()
    sources = []
    parsed_rows = []

    for row in rows[header_index + 1 :]:
        data = {
            header: _clean(row[index]) if index < len(row) else ""
            for index, header in enumerate(headers)
        }
        feed_url = data.get(HEADER_FEED_URL, "")
        if not feed_url:
            continue
        candidate_source_id = data.get(HEADER_ID, "") or _source_id_from_feed_url(feed_url)
        parsed_rows.append((data, feed_url, candidate_source_id))

    source_id_counts = Counter(candidate_source_id for _, _, candidate_source_id in parsed_rows)

    for data, feed_url, candidate_source_id in parsed_rows:
        raw_status = data.get(HEADER_STATUS, "")
        health_status, is_fetchable = classify_health_status(raw_status)
        source_id = candidate_source_id
        if source_id_counts[candidate_source_id] > 1:
            source_id = f"{candidate_source_id}-{_source_id_suffix(feed_url)}"

        sources.append(
            RssSource(
                source_id=source_id,
                market_level=data.get(HEADER_MARKET_LEVEL, ""),
                publisher=data.get(HEADER_PUBLISHER, ""),
                desk=data.get(HEADER_DESK, ""),
                category=data.get(HEADER_CATEGORY, ""),
                zh_name=data.get(HEADER_ZH_NAME, ""),
                description=data.get(HEADER_DESCRIPTION, ""),
                feed_url=feed_url,
                raw_status=raw_status,
                health_status=health_status,
                is_fetchable=is_fetchable,
                last_checked_at=data.get(HEADER_LAST_CHECKED_AT, ""),
                synced_at=synced_at,
                last_seen_in_sheet_at=synced_at,
            )
        )

    return sources


def count_duplicate_sheet_source_ids(rows: list[list[str]]) -> int:
    if not rows:
        return 0

    header_index = None
    for index, row in enumerate(rows):
        if HEADER_FEED_URL in row:
            header_index = index
            break
    if header_index is None:
        return 0

    headers = [_clean(header) for header in rows[header_index]]
    candidates = []
    for row in rows[header_index + 1 :]:
        data = {
            header: _clean(row[index]) if index < len(row) else ""
            for index, header in enumerate(headers)
        }
        feed_url = data.get(HEADER_FEED_URL, "")
        if not feed_url:
            continue
        candidates.append(data.get(HEADER_ID, "") or _source_id_from_feed_url(feed_url))

    counts = Counter(candidates)
    return sum(count - 1 for count in counts.values() if count > 1)


def sync_rss_sources_from_sheet() -> dict[str, object]:
    rows = SheetsClient().read_source_rows()
    sources = parse_sheet_source_rows(rows)
    synced_at = sources[0].synced_at if sources else utc_now_iso()
    source_id_counts = Counter(source.source_id for source in sources)
    duplicate_source_id_count = sum(count - 1 for count in source_id_counts.values() if count > 1)
    duplicate_sheet_id_count = count_duplicate_sheet_source_ids(rows)

    firestore_client.upsert_rss_sources(sources)
    deactivated_missing_source_count = firestore_client.deactivate_missing_rss_sources(
        {source.source_id for source in sources},
        synced_at,
    )

    return {
        "synced_source_count": len(sources),
        "fetchable_source_count": sum(1 for source in sources if source.is_fetchable),
        "broken_source_count": sum(1 for source in sources if source.health_status == "broken"),
        "non_fetchable_source_count": sum(1 for source in sources if not source.is_fetchable),
        "deactivated_missing_source_count": deactivated_missing_source_count,
        "unique_source_count": len(source_id_counts),
        "duplicate_source_id_count": duplicate_source_id_count,
        "duplicate_sheet_id_count": duplicate_sheet_id_count,
        "required_fetchable_status": FETCHABLE_STATUS,
        "synced_at": synced_at,
    }
