from collections import Counter
from datetime import datetime, timedelta, timezone
import re
from typing import Any

from app.clients.firestore_client import firestore_client
from app.models.rss import RssItem
from app.services.rss_source_service import utc_now_iso


STOP_WORDS = {
    "about",
    "after",
    "amid",
    "and",
    "are",
    "as",
    "for",
    "from",
    "into",
    "its",
    "new",
    "not",
    "over",
    "says",
    "the",
    "to",
    "with",
}


def _since_iso(since_hours: int) -> str:
    since = datetime.now(timezone.utc) - timedelta(hours=since_hours)
    return since.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _counter(items: list[Any], field: str) -> dict[str, int]:
    counts = Counter(str(getattr(item, field, "") or "unknown") for item in items)
    return dict(counts.most_common())


def _top_terms(items: list[RssItem], limit: int = 20) -> list[dict[str, object]]:
    counter: Counter[str] = Counter()
    for item in items:
        words = re.findall(r"[A-Za-z][A-Za-z0-9-]{2,}|[\u4e00-\u9fff]{2,}", item.title.lower())
        counter.update(word for word in words if word not in STOP_WORDS)
    return [{"term": term, "count": count} for term, count in counter.most_common(limit)]


def _source_item_counts(items: list[RssItem], limit: int = 20) -> list[dict[str, object]]:
    counts = Counter(item.source_id for item in items)
    publisher_by_source = {item.source_id: item.publisher for item in items}
    desk_by_source = {item.source_id: item.desk for item in items}
    return [
        {
            "source_id": source_id,
            "publisher": publisher_by_source.get(source_id, ""),
            "desk": desk_by_source.get(source_id, ""),
            "item_count": count,
        }
        for source_id, count in counts.most_common(limit)
    ]


def _title_fingerprints(items: list[RssItem], limit: int = 20) -> list[dict[str, object]]:
    grouped: dict[str, list[RssItem]] = {}
    for item in items:
        words = re.findall(r"[a-z][a-z0-9-]{2,}", item.title.lower())
        keywords = [word for word in words if word not in STOP_WORDS][:8]
        if len(keywords) < 3:
            continue
        fingerprint = " ".join(sorted(set(keywords)))
        grouped.setdefault(fingerprint, []).append(item)

    duplicates = [
        {
            "fingerprint": fingerprint,
            "item_count": len(group),
            "publisher_count": len({item.publisher for item in group if item.publisher}),
            "sample_titles": [item.title for item in group[:3]],
        }
        for fingerprint, group in grouped.items()
        if len(group) > 1
    ]
    duplicates.sort(key=lambda item: (int(item["publisher_count"]), int(item["item_count"])), reverse=True)
    return duplicates[:limit]


def _freshness_summary(items: list[RssItem]) -> dict[str, int]:
    now = datetime.now(timezone.utc)
    buckets = {
        "published_within_3h": 0,
        "published_within_12h": 0,
        "published_within_24h": 0,
        "missing_published_at": 0,
    }
    for item in items:
        if not item.published_at:
            buckets["missing_published_at"] += 1
            continue
        try:
            published_at = datetime.fromisoformat(item.published_at.replace("Z", "+00:00"))
        except ValueError:
            buckets["missing_published_at"] += 1
            continue
        age_hours = (now - published_at.astimezone(timezone.utc)).total_seconds() / 3600
        if age_hours <= 3:
            buckets["published_within_3h"] += 1
        if age_hours <= 12:
            buckets["published_within_12h"] += 1
        if age_hours <= 24:
            buckets["published_within_24h"] += 1
    return buckets


def build_source_health_summary() -> dict[str, object]:
    sources = firestore_client.list_rss_sources(fetchable_only=False)
    health_counts = Counter(source.health_status for source in sources)
    publisher_counts = Counter(source.publisher or "unknown" for source in sources)
    return {
        "generated_at": utc_now_iso(),
        "source_count": len(sources),
        "fetchable_source_count": sum(1 for source in sources if source.is_fetchable),
        "unfetchable_source_count": sum(1 for source in sources if not source.is_fetchable),
        "health_status_counts": dict(health_counts.most_common()),
        "publisher_counts": dict(publisher_counts.most_common()),
        "sources": [source.model_dump() for source in sources],
    }


def get_recent_rss_items(since_hours: int = 24) -> dict[str, object]:
    since = _since_iso(since_hours)
    items = firestore_client.list_rss_items_since(since)
    items.sort(key=lambda item: item.published_at or item.first_seen_at, reverse=True)
    return {
        "since_hours": since_hours,
        "window_start": since,
        "generated_at": utc_now_iso(),
        "item_count": len(items),
        "items": [item.model_dump() for item in items],
    }


def build_signal_observation_report(since_hours: int = 24) -> dict[str, object]:
    since = _since_iso(since_hours)
    items = firestore_client.list_rss_items_since(since)
    sources = firestore_client.list_rss_sources(fetchable_only=True)
    items.sort(key=lambda item: item.published_at or item.first_seen_at, reverse=True)
    active_source_ids = {item.source_id for item in items}
    fetchable_source_ids = {source.source_id for source in sources}
    active_fetchable_source_ids = active_source_ids.intersection(fetchable_source_ids)

    return {
        "report_type": "rss_signal_observation",
        "since_hours": since_hours,
        "window_start": since,
        "generated_at": utc_now_iso(),
        "rss_frequency_is_not_importance": True,
        "summary": {
            "item_count": len(items),
            "unique_source_count": len({item.source_id for item in items}),
            "fetchable_source_count": len(fetchable_source_ids),
            "active_source_count": len(active_source_ids),
            "active_fetchable_source_count": len(active_fetchable_source_ids),
            "silent_fetchable_source_count": len(fetchable_source_ids - active_source_ids),
            "source_coverage_ratio": (
                round(len(active_fetchable_source_ids) / len(fetchable_source_ids), 4)
                if fetchable_source_ids
                else 0
            ),
            "desk_counts": _counter(items, "desk"),
            "publisher_counts": _counter(items, "publisher"),
            "market_level_counts": _counter(items, "market_level"),
            "category_counts": _counter(items, "category"),
            "top_title_terms": _top_terms(items),
            "source_item_counts": _source_item_counts(items),
            "freshness": _freshness_summary(items),
            "possible_duplicate_topics": _title_fingerprints(items),
        },
        "recent_item_sample": [item.model_dump() for item in items[:20]],
        "caveats": [
            "RSS status only reflects feed availability, not editorial quality or market importance.",
            "Higher RSS frequency is an observation signal, not an importance score.",
            "Lower RSS frequency can reflect source bias, feed limits, or early-stage signals.",
            "This report intentionally avoids investment recommendations and final importance ranking.",
        ],
    }
