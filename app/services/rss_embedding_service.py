import logging
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.clients.embedding_client import EmbeddingClient, estimate_cost_usd
from app.clients.firestore_client import firestore_client
from app.core.config import settings
from app.models.rss import RssItem
from app.services.rss_source_service import utc_now_iso

logger = logging.getLogger(__name__)

MAX_INPUT_CHARS = 2048
SUMMARY_LIMIT = 500


_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")


def _strip_html(value: str) -> str:
    if not value:
        return ""
    return _HTML_TAG_RE.sub(" ", value)


def _normalize_whitespace(value: str) -> str:
    return _WHITESPACE_RE.sub(" ", value).strip()


def build_text_for_embedding(item: RssItem) -> str:
    title = _normalize_whitespace(_strip_html(item.title or ""))
    summary = _normalize_whitespace(_strip_html(item.summary or ""))[:SUMMARY_LIMIT]
    combined = f"{title} {summary}".strip()
    if len(combined) > MAX_INPUT_CHARS:
        combined = combined[:MAX_INPUT_CHARS]
    return combined


def _window_start_iso(window_hours: int) -> str:
    start = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    return start.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def embed_pending_items(
    window_hours: int = 4,
    embedding_client: Optional[EmbeddingClient] = None,
) -> dict[str, object]:
    started = time.monotonic()
    since_iso = _window_start_iso(window_hours)

    candidates = firestore_client.list_rss_items_pending_embedding(since_iso)
    if not candidates:
        return {
            "since": since_iso,
            "candidate_item_count": 0,
            "embedded_item_count": 0,
            "embedding_failed_item_count": 0,
            "cost_usd": 0.0,
            "duration_ms": 0,
        }

    client = embedding_client or EmbeddingClient()
    if not client.is_ready:
        return {
            "since": since_iso,
            "candidate_item_count": len(candidates),
            "embedded_item_count": 0,
            "embedding_failed_item_count": len(candidates),
            "cost_usd": 0.0,
            "duration_ms": int((time.monotonic() - started) * 1000),
            "error": "embedding_client_not_ready",
        }

    texts = [build_text_for_embedding(item) for item in candidates]
    vectors, failed_indices, total_chars = client.embed_batch(texts)

    embedded_at = utc_now_iso()
    updates: dict[str, tuple[list[float], str, str]] = {}
    for item, vec in zip(candidates, vectors):
        if vec is None:
            continue
        updates[item.item_id] = (vec, settings.EMBEDDING_MODEL, embedded_at)

    written = firestore_client.update_rss_item_embeddings(updates)

    return {
        "since": since_iso,
        "candidate_item_count": len(candidates),
        "embedded_item_count": written,
        "embedding_failed_item_count": len(failed_indices),
        "cost_usd": estimate_cost_usd(total_chars),
        "duration_ms": int((time.monotonic() - started) * 1000),
    }
