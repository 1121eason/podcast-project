import logging
import re
from html import unescape
from html.parser import HTMLParser

import httpx

from app.models.rss import RssItem
from app.services.signal_v2_utils import (
    article_text_hash,
    utc_now_iso,
)

logger = logging.getLogger(__name__)

ARTICLE_LEAD_CHAR_LIMIT = 1600
# X1: RSS desc >= this many chars → skip scrape entirely (RSS self-sufficient)
RSS_SUFFICIENT_CHARS = 400
# X2: scraped lead >= this many chars → status="success", else "thin"
SCRAPE_USEFUL_CHARS = 500


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._skip_stack: list[str] = []
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript", "svg", "nav", "footer"}:
            self._skip_stack.append(tag)

    def handle_endtag(self, tag):
        if self._skip_stack and self._skip_stack[-1] == tag:
            self._skip_stack.pop()

    def handle_data(self, data):
        if self._skip_stack:
            return
        text = re.sub(r"\s+", " ", unescape(data or "")).strip()
        if len(text) >= 30:
            self.parts.append(text)


def should_extract_article(item: RssItem) -> bool:
    """X1 gate: only scrape when RSS-provided summary is below the sufficient threshold."""
    if not item.url:
        return False
    summary = (item.summary or "").strip()
    return len(summary) < RSS_SUFFICIENT_CHARS


def extract_article_lead(item: RssItem, timeout_seconds: int = 10) -> dict[str, object]:
    if not should_extract_article(item):
        return {
            "status": "skipped",
            "article_lead": item.article_lead or "",
            "article_text_hash": item.article_text_hash,
            "extracted_at": item.article_extracted_at,
        }
    try:
        headers = {"User-Agent": "InformativeAI-SignalProcessor/1.0"}
        response = httpx.get(item.url, headers=headers, timeout=timeout_seconds, follow_redirects=True)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        if "html" not in content_type and "text" not in content_type:
            raise ValueError(f"unsupported content-type: {content_type}")
        lead = _clean_html_to_lead(response.text)
        if not lead:
            raise ValueError("no article text extracted")
        # X2 gate: classify scrape success by content depth
        status = "success" if len(lead) >= SCRAPE_USEFUL_CHARS else "thin"
        return {
            "status": status,
            "article_lead": lead,
            "article_text_hash": article_text_hash(lead),
            "extracted_at": utc_now_iso(),
        }
    except Exception as exc:
        logger.warning("Article extraction failed for %s: %s", item.item_id, exc)
        return {
            "status": "failed",
            "article_lead": item.article_lead or "",
            "article_text_hash": item.article_text_hash,
            "extracted_at": utc_now_iso(),
            "error": str(exc)[:200],
        }


def _clean_html_to_lead(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html or "")
    text = " ".join(parser.parts)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:ARTICLE_LEAD_CHAR_LIMIT]
