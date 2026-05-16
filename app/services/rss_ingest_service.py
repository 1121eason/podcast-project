from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import hashlib
import html
import httpx
import re
import time
import uuid
from typing import Optional
import xml.etree.ElementTree as ET

from app.clients.firestore_client import firestore_client
from app.models.rss import RssIngestRun, RssItem, RssSource
from app.services.log_summary_utils import (
    add_log_summary,
    sample_from_dicts,
    sample_values,
    seconds_text,
    tagged,
)
from app.services.rss_source_service import utc_now_iso


USER_AGENT = "SignalBriefRSSBot/1.0"
DEFAULT_FEED_TIMEOUT_SECONDS = 25
DEFAULT_MAX_WORKERS = 10
DEFAULT_RSSHUB_WORKERS = 2
DEFAULT_GOV_WORKERS = 3
RSSHUB_HOST_MARKER = "zeabur.app"
GOV_HOST_MARKERS = (".gov", ".bls.gov", ".cftc.gov", ".ftc.gov", ".sec.gov", ".cisa.gov", ".treasury.gov")


def _is_gov_url(url: str) -> bool:
    if not url:
        return False
    return any(marker in url for marker in GOV_HOST_MARKERS)

def _clean_text(value: object) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _children(element: ET.Element, name: str) -> list[ET.Element]:
    return [child for child in list(element) if _local_name(child.tag) == name]


def _first_text(element: ET.Element, names: list[str]) -> str:
    for name in names:
        for child in _children(element, name):
            text = _clean_text("".join(child.itertext()))
            if text:
                return text
    return ""


def _rss_link(element: ET.Element) -> str:
    link = _first_text(element, ["link"])
    if link:
        return link

    for child in _children(element, "link"):
        href = _clean_text(child.attrib.get("href"))
        if href:
            return href
    return ""


def _atom_link(element: ET.Element) -> str:
    for child in _children(element, "link"):
        rel = _clean_text(child.attrib.get("rel"))
        href = _clean_text(child.attrib.get("href"))
        if href and rel in {"", "alternate"}:
            return href
    return _rss_link(element)


def _parse_datetime(value: str) -> Optional[str]:
    value = _clean_text(value)
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _content_hash(title: str, url: str, summary: str) -> str:
    content = f"{title}\n{url}\n{summary}"
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _item_id(source_id: str, guid: str, url: str, content_hash: str) -> str:
    key = f"{source_id}\n{guid or url or content_hash}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def _published_or_seen_at(item: RssItem) -> str:
    return item.published_at or item.first_seen_at


def _is_iso_at_or_after(value: str, since_iso: str) -> bool:
    try:
        parsed_value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        parsed_since = datetime.fromisoformat(since_iso.replace("Z", "+00:00"))
    except ValueError:
        return value >= since_iso
    return parsed_value >= parsed_since


def fetch_feed_xml(feed_url: str, timeout_seconds: int = DEFAULT_FEED_TIMEOUT_SECONDS) -> str:
    timeout = httpx.Timeout(
        timeout_seconds,
        connect=min(5.0, float(timeout_seconds)),
        read=float(timeout_seconds),
        write=5.0,
        pool=5.0,
    )
    with httpx.Client(
        follow_redirects=True,
        timeout=timeout,
        headers={"User-Agent": USER_AGENT},
    ) as client:
        response = client.get(feed_url)
        response.raise_for_status()
        return response.text


def parse_feed_items(feed_xml: str, source: RssSource, seen_at: str | None = None) -> list[RssItem]:
    seen_at = seen_at or utc_now_iso()
    root = ET.fromstring(feed_xml)
    root_name = _local_name(root.tag).lower()
    entries = root.findall(".//{*}entry") if root_name == "feed" else root.findall(".//{*}item")

    items = []
    for entry in entries:
        is_atom = _local_name(entry.tag).lower() == "entry"
        title = _first_text(entry, ["title"])
        if not title:
            continue

        url = _atom_link(entry) if is_atom else _rss_link(entry)
        guid = _first_text(entry, ["guid", "id"])
        summary = _first_text(entry, ["description", "summary", "content", "encoded"])
        published_at = _parse_datetime(
            _first_text(entry, ["pubDate", "published", "updated", "date"])
        )
        content_hash = _content_hash(title, url, summary)

        items.append(
            RssItem(
                item_id=_item_id(source.source_id, guid, url, content_hash),
                source_id=source.source_id,
                publisher=source.publisher,
                desk=source.desk,
                category=source.category,
                market_level=source.market_level,
                title=title,
                url=url,
                guid=guid,
                summary=summary,
                published_at=published_at,
                first_seen_at=seen_at,
                last_seen_at=seen_at,
                content_hash=content_hash,
                feed_url=source.feed_url,
            )
        )
    return items


def _ingest_one_source(
    source: RssSource,
    timeout_seconds: int,
    window_start_iso: str | None,
) -> dict[str, object]:
    started = time.monotonic()
    result: dict[str, object] = {
        "source_id": source.source_id,
        "publisher": source.publisher,
        "desk": source.desk,
        "category": source.category,
        "feed_url": source.feed_url,
        "status": "failed",
        "duration_ms": 0,
        "fetch_duration_ms": 0,
        "write_duration_ms": 0,
        "item_count": 0,
        "new_item_count": 0,
        "updated_item_count": 0,
        "skipped_existing_item_count": 0,
        "skipped_old_item_count": 0,
        "error": None,
        "error_type": None,
    }

    try:
        fetch_started = time.monotonic()
        feed_xml = fetch_feed_xml(source.feed_url, timeout_seconds=timeout_seconds)
        result["fetch_duration_ms"] = int((time.monotonic() - fetch_started) * 1000)
        items = parse_feed_items(feed_xml, source)
        skipped_old_item_count = 0
        if window_start_iso:
            filtered_items = []
            for item in items:
                if _is_iso_at_or_after(_published_or_seen_at(item), window_start_iso):
                    filtered_items.append(item)
                else:
                    skipped_old_item_count += 1
            items = filtered_items

        new_item_count = 0
        updated_item_count = 0
        skipped_existing_item_count = 0
        write_started = time.monotonic()
        new_item_count, updated_item_count, skipped_existing_item_count = firestore_client.upsert_rss_items(items)
        result["write_duration_ms"] = int((time.monotonic() - write_started) * 1000)

        result.update(
            {
                "status": "success",
                "item_count": len(items),
                "new_item_count": new_item_count,
                "updated_item_count": updated_item_count,
                "skipped_existing_item_count": skipped_existing_item_count,
                "skipped_old_item_count": skipped_old_item_count,
            }
        )
    except Exception as exc:
        result.update(
            {
                "error": str(exc),
                "error_type": type(exc).__name__,
            }
        )
    finally:
        result["duration_ms"] = int((time.monotonic() - started) * 1000)

    return result


def ingest_rss_sources(
    *,
    limit_sources: Optional[int] = None,
    include_unhealthy: bool = False,
    max_workers: int = DEFAULT_MAX_WORKERS,
    timeout_seconds: int = DEFAULT_FEED_TIMEOUT_SECONDS,
    since_hours: Optional[int] = 24,
) -> dict[str, object]:
    started_at = utc_now_iso()
    started = time.monotonic()
    sources = firestore_client.list_rss_sources(fetchable_only=not include_unhealthy)
    if limit_sources is not None:
        sources = sources[:limit_sources]

    max_workers = max(1, min(max_workers, 20))
    timeout_seconds = max(1, min(timeout_seconds, 30))
    window_start_iso = None
    if since_hours is not None:
        since_hours = max(1, min(since_hours, 168))
        run_started_at = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        window_start = run_started_at - timedelta(hours=since_hours)
        window_start_iso = window_start.replace(microsecond=0).isoformat().replace("+00:00", "Z")

    rsshub_sources = [s for s in sources if RSSHUB_HOST_MARKER in (s.feed_url or "")]
    gov_sources = [
        s for s in sources
        if RSSHUB_HOST_MARKER not in (s.feed_url or "") and _is_gov_url(s.feed_url or "")
    ]
    other_sources = [
        s for s in sources
        if RSSHUB_HOST_MARKER not in (s.feed_url or "") and not _is_gov_url(s.feed_url or "")
    ]

    source_results = []
    if sources:
        other_workers = max(1, min(max_workers, len(other_sources) or 1))
        rsshub_workers = max(1, min(DEFAULT_RSSHUB_WORKERS, len(rsshub_sources) or 1))
        gov_workers = max(1, min(DEFAULT_GOV_WORKERS, len(gov_sources) or 1))
        with (
            ThreadPoolExecutor(max_workers=other_workers, thread_name_prefix="rss-direct") as exe_other,
            ThreadPoolExecutor(max_workers=rsshub_workers, thread_name_prefix="rss-rsshub") as exe_rsshub,
            ThreadPoolExecutor(max_workers=gov_workers, thread_name_prefix="rss-gov") as exe_gov,
        ):
            futures = [
                exe_other.submit(_ingest_one_source, source, timeout_seconds, window_start_iso)
                for source in other_sources
            ]
            futures.extend(
                exe_rsshub.submit(_ingest_one_source, source, timeout_seconds, window_start_iso)
                for source in rsshub_sources
            )
            futures.extend(
                exe_gov.submit(_ingest_one_source, source, timeout_seconds, window_start_iso)
                for source in gov_sources
            )
            for future in as_completed(futures):
                source_results.append(future.result())

    source_results.sort(key=lambda result: str(result.get("source_id", "")))
    errors = [
        {
            "source_id": str(result.get("source_id", "")),
            "feed_url": str(result.get("feed_url", "")),
            "error": str(result.get("error") or ""),
        }
        for result in source_results
        if result.get("status") != "success"
    ]
    fetched_source_count = sum(1 for result in source_results if result.get("status") == "success")
    new_item_count = sum(int(result.get("new_item_count") or 0) for result in source_results)
    updated_item_count = sum(int(result.get("updated_item_count") or 0) for result in source_results)
    skipped_existing_item_count = sum(int(result.get("skipped_existing_item_count") or 0) for result in source_results)
    skipped_old_item_count = sum(int(result.get("skipped_old_item_count") or 0) for result in source_results)

    completed_at = utc_now_iso()
    run = RssIngestRun(
        run_id=f"rss_ingest_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}",
        started_at=started_at,
        completed_at=completed_at,
        source_count=len(sources),
        fetched_source_count=fetched_source_count,
        failed_source_count=len(errors),
        new_item_count=new_item_count,
        updated_item_count=updated_item_count,
        error_count=len(errors),
        errors=errors[:50],
        duration_ms=int((time.monotonic() - started) * 1000),
        timeout_seconds=timeout_seconds,
        max_workers=max_workers,
        window_start=window_start_iso,
        skipped_old_item_count=skipped_old_item_count,
        skipped_existing_item_count=skipped_existing_item_count,
        source_results=source_results,
    )
    firestore_client.create_rss_ingest_run(run)

    result = run.model_dump()
    add_log_summary(result, _compose_ingest_log_summary(result))
    return result


def _compose_ingest_log_summary(result: dict[str, object]) -> list[str]:
    source_results = result.get("source_results") if isinstance(result.get("source_results"), list) else []
    errors = result.get("errors") if isinstance(result.get("errors"), list) else []
    slow_sources = sorted(
        source_results,
        key=lambda row: int(row.get("duration_ms") or 0) if isinstance(row, dict) else 0,
        reverse=True,
    )
    slow_sample = sample_values(
        [
            f"{row.get('publisher') or row.get('source_id')} {seconds_text(row.get('duration_ms'))}"
            for row in slow_sources
            if isinstance(row, dict)
        ]
    )
    error_sample = sample_from_dicts(errors, ("source_id", "error"))
    lines = [
        tagged(
            "ok",
            (
                f"W2 RSS ingest 抓取 {result.get('fetched_source_count', 0)}/"
                f"{result.get('source_count', 0)} 個 source，新增 {result.get('new_item_count', 0)} item，"
                f"重複略過 {result.get('skipped_existing_item_count', 0)}，舊文略過 {result.get('skipped_old_item_count', 0)}。"
            ),
        ),
    ]
    if int(result.get("failed_source_count") or 0):
        lines.append(
            tagged(
                "warn",
                f"{result.get('failed_source_count')} 個 source 失敗：{error_sample or '詳見 errors'}。",
            )
        )
    else:
        lines.append(tagged("ok", "所有可抓取 source 皆成功。"))
    if slow_sample:
        lines.append(tagged("time", f"慢來源樣本：{slow_sample}。"))
    lines.append(tagged("time", f"總耗時 {seconds_text(result.get('duration_ms'))}。"))
    return lines
