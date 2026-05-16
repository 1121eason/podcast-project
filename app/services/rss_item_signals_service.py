"""Mechanical replacement for canonical_event extraction (Plan A, no LLM).

Produces a small structured dict from an RssItem using only regex + dict lookups.
Output schema (item.item_signals):
  {
    "entities":       list[str]  — top-K entities (NER + dict + ticker regex)
    "primary_action": str        — head verb from title (heuristic)
    "event_tags":     list[str]  — BLACK_SWAN keywords that matched the blob
    "market_tags":    list[str]  — [category, desk, market_level] filtered to non-empty
    "publisher_tier": str        — "aggregator" | "tier1" | "other"
    "lang":           str        — "zh" | "en" | "mixed"
  }

This replaces what canonical_event used to provide for embedding inputs and
matching hard-gates, without any LLM call.
"""
import re

from app.models.rss import RssItem
from app.services.signal_v2_utils import (
    BLACK_SWAN_PATTERNS,
    MAJOR_ENTITY_PATTERNS,
    compact_text,
    extract_keywords,
    publisher_tier,
    stable_hash,
)

# Stock ticker patterns: $AAPL, NVDA, 2330.TW, 700.HK, 7203.T
TICKER_PATTERNS = [
    re.compile(r"\$([A-Z]{1,5})\b"),                     # $AAPL
    re.compile(r"\b(\d{4})\.TW\b", re.IGNORECASE),       # 2330.TW
    re.compile(r"\b(\d{3,5})\.HK\b", re.IGNORECASE),     # 700.HK
    re.compile(r"\b(\d{4})\.T\b"),                       # 7203.T (Tokyo)
]

# Heuristic head verbs (zh + en) — first match wins
ZH_ACTION_PATTERNS = [
    "降息", "升息", "停火", "破產", "詐欺", "違約", "下市", "停工",
    "漲", "跌", "上升", "下跌", "開始", "結束", "批准", "拒絕",
    "出口管制", "緊急會議", "重大公告", "宣布", "公布", "推出", "發表",
]
EN_ACTION_PATTERNS = [
    "rate cut", "rate hike", "ceasefire", "bankruptcy", "fraud", "default",
    "shutdown", "outbreak", "coup", "invasion", "missile strike", "airstrike",
    "export ban", "export control", "emergency meeting", "circuit breaker",
    "trading halt", "oil shock", "announce", "launch", "release", "unveil",
    "rises", "falls", "surges", "drops", "approves", "rejects",
]


def _detect_lang(text: str) -> str:
    if not text:
        return "en"
    zh_count = sum(1 for c in text if "一" <= c <= "鿿")
    en_count = sum(1 for c in text if c.isascii() and c.isalpha())
    total = zh_count + en_count
    if total == 0:
        return "en"
    zh_ratio = zh_count / total
    if zh_ratio > 0.6:
        return "zh"
    if zh_ratio < 0.1:
        return "en"
    return "mixed"


def _extract_tickers(text: str) -> list[str]:
    found = []
    for pattern in TICKER_PATTERNS:
        for m in pattern.findall(text or ""):
            sym = m if isinstance(m, str) else m[0] if m else ""
            if sym:
                found.append(sym.upper())
    return found


def _extract_entities(text: str, item: RssItem, max_entities: int = 8) -> list[str]:
    """Combine: dict-major-entity hits + tickers + general keyword extraction."""
    out: list[str] = []
    seen: set[str] = set()

    def add(token: str):
        key = token.lower()
        if key and key not in seen and len(out) < max_entities:
            seen.add(key)
            out.append(token[:40])

    blob_lower = (text or "").lower()
    # 1. Major entity dictionary
    for pat in MAJOR_ENTITY_PATTERNS:
        if pat in blob_lower:
            add(pat)
    # 2. Tickers
    for t in _extract_tickers(text):
        add(t)
    # 3. Generic keyword extraction (NER-like)
    for kw in extract_keywords(text, max_terms=max_entities):
        add(kw)
    return out[:max_entities]


def _extract_primary_action(title: str, text: str) -> str:
    """Heuristic head verb: scan zh then en patterns; first match wins."""
    title_lower = (title or "").lower()
    text_lower = (text or "").lower()
    # zh patterns (substring match)
    for pat in ZH_ACTION_PATTERNS:
        if pat in (title or ""):
            return pat
    for pat in ZH_ACTION_PATTERNS:
        if pat in (text or ""):
            return pat
    # en patterns
    for pat in EN_ACTION_PATTERNS:
        if pat in title_lower:
            return pat
    for pat in EN_ACTION_PATTERNS:
        if pat in text_lower:
            return pat
    return ""


def _extract_event_tags(text: str) -> list[str]:
    """All BLACK_SWAN_PATTERNS that match the blob (deduped)."""
    blob = (text or "").lower()
    hits = [pat for pat in BLACK_SWAN_PATTERNS if pat in blob]
    # dedupe preserving order
    seen = set()
    out = []
    for h in hits:
        if h not in seen:
            seen.add(h)
            out.append(h)
    return out[:8]


def extract_item_signals(item: RssItem) -> dict:
    """Build the item_signals dict from an RssItem. Pure function, no IO."""
    blob = compact_text(item.title, item.summary, item.article_lead, limit=3000)
    entities = _extract_entities(blob, item)
    primary_action = _extract_primary_action(item.title or "", blob)
    event_tags = _extract_event_tags(blob)
    market_tags = [t for t in [item.category, item.desk, item.market_level] if t]
    tier = publisher_tier(item.publisher or "")
    lang = _detect_lang(blob)
    return {
        "entities": entities,
        "primary_action": primary_action,
        "event_tags": event_tags,
        "market_tags": market_tags,
        "publisher_tier": tier,
        "lang": lang,
    }


def item_signals_hash(signals: dict) -> str:
    """Stable hash used to skip re-computation when nothing has changed."""
    return stable_hash(signals)
