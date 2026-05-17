import hashlib
import json
import math
import re
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

try:
    import numpy as np  # type: ignore
    _NUMPY_AVAILABLE = True
except Exception:  # pragma: no cover - numpy is in requirements but stay defensive
    _NUMPY_AVAILABLE = False


MAJOR_ENTITY_PATTERNS = [
    "nvidia",
    "apple",
    "microsoft",
    "google",
    "alphabet",
    "amazon",
    "meta",
    "tesla",
    "tsmc",
    "openai",
    "anthropic",
    "berkshire",
    "jpmorgan",
    "exxonmobil",
    "asml",
    "samsung",
    "fed",
    "federal reserve",
    "ecb",
    "boj",
    "央行",
    "聯準會",
    "台積電",
    "三星",
]

# Black-swan = high-impact action / event keywords. Entity names DO NOT count.
# Country / region names (iran/taiwan/china) were intentionally removed because
# 30-50% of geopolitics signals mention them; they made `is_major_or_black_swan`
# fire too often and triggered Pro adjudication unnecessarily.
BLACK_SWAN_PATTERNS = [
    "ceasefire",
    "bankruptcy",
    "fraud",
    "indictment",
    "default",
    "shutdown",
    "outbreak",
    "pandemic",
    "coup",
    "invasion",
    "missile strike",
    "airstrike",
    "export ban",
    "export control",
    "rate cut",
    "rate hike",
    "emergency meeting",
    "circuit breaker",
    "trading halt",
    "oil shock",
    "停火",
    "破產",
    "詐欺",
    "違約",
    "下市",
    "停工",
    "疫情",
    "政變",
    "出口管制",
    "降息",
    "升息",
    "緊急會議",
    "重大公告",
]

GENERIC_TITLE_PATTERNS = [
    r"live updates?",
    r"here'?s the latest",
    r"what to know",
    r"market wrap",
    r"closing bell",
    r"morning bid",
    r"盤後",
    r"盤前",
    r"快訊",
    r"最新",
]
GENERIC_TITLE_REGEX = re.compile("|".join(GENERIC_TITLE_PATTERNS), re.IGNORECASE)

OPPOSITE_ACTION_PAIRS = [
    ("rise", "fall"),
    ("gain", "drop"),
    ("start", "end"),
    ("begin", "collapse"),
    ("approve", "reject"),
    ("ceasefire", "attack"),
    ("漲", "跌"),
    ("上升", "下跌"),
    ("開始", "結束"),
    ("批准", "拒絕"),
]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def since_iso(hours: int) -> str:
    return (
        (datetime.now(timezone.utc) - timedelta(hours=hours))
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def stable_hash(value: object) -> str:
    if isinstance(value, str):
        payload = value
    else:
        payload = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def article_text_hash(text: str) -> str:
    return stable_hash(compact_text(text, limit=20000))


def canonical_event_hash(event: dict | str) -> str:
    return stable_hash(event)


def event_embedding_hash(embedding_inputs: dict[str, str]) -> str:
    return stable_hash(embedding_inputs)


def signal_fingerprint_hash(parts: object) -> str:
    return stable_hash(parts)


def thread_memory_hash(parts: object) -> str:
    return stable_hash(parts)


def short_hash(value: object, length: int = 12) -> str:
    return stable_hash(value)[:length]


def compact_text(*parts: object, limit: int = 3000) -> str:
    text = " ".join(str(p or "").strip() for p in parts if str(p or "").strip())
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def is_generic_title(title: str) -> bool:
    return bool(GENERIC_TITLE_REGEX.search(title or ""))


# ============================================================
# Publisher tier — used by W5 quality gate, briefing weighting, and signal-level tagging
# ============================================================
# Tier-1 direct sources: high-credibility, primary reporters. Single-source from
# these is still worth Judge attention (Reuters scoop / Fed press release).
TIER1_PUBLISHERS = {
    "reuters",
    "bloomberg",
    "ap news",
    "reuters markets（路透）",
    "the new york times",
    "wall street journal",
    "financial times",
    "bbc",
    "nikkei",
    "nikkei（日經）",
    "scmp",
    "中央通訊社",
    "香港經濟日報",
    "the guardian",
    "cnbc",
    "le monde",
    "deutsche welle",
}

# Aggregator publishers: content is repackaged from other sources, summary tends to be thin.
AGGREGATOR_PUBLISHERS = {"yahoo", "yahoo奇摩", "yahoo 奇摩", "msn"}


def _publisher_in_set(publisher: str, pset: set[str]) -> bool:
    p = (publisher or "").lower()
    return any(t in p for t in pset)


def publisher_tier(publisher: str) -> str:
    """Single publisher → tier label. tier1 / aggregator / other."""
    if _publisher_in_set(publisher, AGGREGATOR_PUBLISHERS):
        return "aggregator"
    if _publisher_in_set(publisher, TIER1_PUBLISHERS):
        return "tier1"
    return "other"


def signal_publisher_tier(publishers: list[str]) -> str:
    """Best tier among a signal's publishers. tier1 wins, then other, then aggregator.

    Returns:
        "tier1"      — at least one tier1 publisher present (highest credibility)
        "other"      — only unknown / generic publishers (default category)
        "aggregator" — all publishers are aggregators (lowest credibility, content second-hand)
        ""           — empty publishers list
    """
    if not publishers:
        return ""
    tiers = {publisher_tier(p) for p in publishers if p}
    if "tier1" in tiers:
        return "tier1"
    if "other" in tiers:
        return "other"
    return "aggregator"


def importance_bucket(score: Optional[int]) -> str:
    """Collapse 0-100 importance into 4 actionable buckets.

    Downstream consumers (briefing, podcast, thread promotion) should call this
    rather than ad-hoc thresholds on raw score — keeps semantics consistent and
    lets us adjust cutoffs in one place.
    """
    if score is None:
        return "noise"
    if score >= 80:
        return "critical"     # podcast top-changes + story thread promotion
    if score >= 70:
        return "high"          # briefing 重點 + matching adjudication
    if score >= 60:
        return "medium"        # briefing 候選
    return "noise"             # 不進 briefing


def is_major_or_black_swan(text: str) -> bool:
    blob = (text or "").lower()
    return any(p in blob for p in MAJOR_ENTITY_PATTERNS + BLACK_SWAN_PATTERNS)


def extract_keywords(text: str, max_terms: int = 8) -> list[str]:
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9&.-]{2,}|[\u4e00-\u9fff]{2,}", text or "")
    stop = {
        "the",
        "and",
        "for",
        "with",
        "from",
        "this",
        "that",
        "news",
        "latest",
        "market",
    }
    out: list[str] = []
    seen = set()
    for token in tokens:
        key = token.lower()
        if key in stop or key in seen:
            continue
        seen.add(key)
        out.append(token[:40])
        if len(out) >= max_terms:
            break
    return out


def coerce_numeric_vector(vec: Iterable[object] | None) -> list[float] | None:
    """Return a flat finite float vector, or None for malformed stored embeddings."""
    if vec is None or isinstance(vec, (str, bytes)):
        return None
    out: list[float] = []
    try:
        values = list(vec)
    except TypeError:
        return None
    if not values:
        return None
    for value in values:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(number):
            return None
        out.append(number)
    return out or None


def is_numeric_vector(vec: Iterable[object] | None) -> bool:
    return coerce_numeric_vector(vec) is not None


def cosine_similarity(a: list[float] | None, b: list[float] | None) -> float:
    va_list = coerce_numeric_vector(a)
    vb_list = coerce_numeric_vector(b)
    if not va_list or not vb_list:
        return 0.0
    n = min(len(va_list), len(vb_list))
    if n == 0:
        return 0.0
    if _NUMPY_AVAILABLE:
        va = np.asarray(va_list[:n], dtype=np.float32)
        vb = np.asarray(vb_list[:n], dtype=np.float32)
        norm_a = float(np.linalg.norm(va))
        norm_b = float(np.linalg.norm(vb))
        if not norm_a or not norm_b:
            return 0.0
        return float(np.clip(np.dot(va, vb) / (norm_a * norm_b), -1.0, 1.0))
    dot = sum(va_list[i] * vb_list[i] for i in range(n))
    norm_a = math.sqrt(sum(va_list[i] ** 2 for i in range(n)))
    norm_b = math.sqrt(sum(vb_list[i] ** 2 for i in range(n)))
    if not norm_a or not norm_b:
        return 0.0
    return max(-1.0, min(1.0, dot / (norm_a * norm_b)))


def cosine_similarity_batch(query: list[float] | None, candidates: list[list[float] | None]) -> list[float]:
    """Vectorized cosine of one query vs N candidate vectors. Returns 0.0 for missing entries."""
    query_vec = coerce_numeric_vector(query)
    if not query_vec or not candidates:
        return [0.0] * len(candidates) if candidates else []
    if not _NUMPY_AVAILABLE:
        return [cosine_similarity(query_vec, c) for c in candidates]
    dim = len(query_vec)
    valid_index = []
    matrix_rows = []
    for idx, vec in enumerate(candidates):
        candidate_vec = coerce_numeric_vector(vec)
        if not candidate_vec:
            continue
        if len(candidate_vec) < dim:
            continue
        row = candidate_vec[:dim]
        valid_index.append(idx)
        matrix_rows.append(row)
    if not matrix_rows:
        return [0.0] * len(candidates)
    q = np.asarray(query_vec[:dim], dtype=np.float32)
    q_norm = float(np.linalg.norm(q))
    if not q_norm:
        return [0.0] * len(candidates)
    mat = np.asarray(matrix_rows, dtype=np.float32)
    norms = np.linalg.norm(mat, axis=1)
    norms[norms == 0] = 1.0
    sims = (mat @ q) / (norms * q_norm)
    sims = np.clip(sims, -1.0, 1.0)
    out = [0.0] * len(candidates)
    for slot, score in zip(valid_index, sims.tolist()):
        out[slot] = float(score)
    return out


def normalize_vector(vec: list[float] | None) -> list[float] | None:
    clean = coerce_numeric_vector(vec)
    if not clean:
        return None
    norm = math.sqrt(sum(v ** 2 for v in clean))
    if not norm:
        return clean
    return [v / norm for v in clean]


def decay_centroid(old: list[float] | None, new: list[float] | None, decay: float) -> list[float] | None:
    old_vec = coerce_numeric_vector(old)
    new_vec = coerce_numeric_vector(new)
    if not old_vec:
        return normalize_vector(new_vec)
    if not new_vec:
        return normalize_vector(old_vec)
    n = min(len(old_vec), len(new_vec))
    mixed = [old_vec[i] * decay + new_vec[i] * (1.0 - decay) for i in range(n)]
    return normalize_vector(mixed)


def overlap_ratio(left: Iterable[str] | None, right: Iterable[str] | None) -> float:
    a = {str(x).lower() for x in (left or []) if str(x).strip()}
    b = {str(x).lower() for x in (right or []) if str(x).strip()}
    if not a or not b:
        return 0.0
    return len(a & b) / max(len(a), len(b))


def phase_flags_from_rationale(rationale: Optional[str]) -> dict[str, bool]:
    """Parse W7 phase decision flags out of (text) rationale.

    W7 writes ``thread_mismatch_suspected:...`` or ``duplicate_suspected:...``
    into ``signal.adjudication_rationale`` (not ``adjudication_decision``, which
    only carries W4's same_event / same_thread / different_event). Both W8
    briefing and W9 podcast services read these flags so the prompt rules can
    address them by name.
    """
    text = (rationale or "").strip().lower()
    return {
        "thread_mismatch_suspected": text.startswith("thread_mismatch_suspected"),
        "duplicate_suspected": text.startswith("duplicate_suspected"),
    }


def actions_conflict(left: str, right: str) -> bool:
    a = (left or "").lower()
    b = (right or "").lower()
    for first, second in OPPOSITE_ACTION_PAIRS:
        if (first in a and second in b) or (second in a and first in b):
            return True
    return False
