import json
import logging

from app.clients.gemini_client import gemini_client
from app.models.rss import RssItem
from app.services.llm_cost_utils import compute_llm_cost
from app.services.model_routing_service import resolve_model_route
from app.services.signal_v2_utils import (
    canonical_event_hash,
    compact_text,
    extract_keywords,
    is_generic_title,
    is_major_or_black_swan,
    utc_now_iso,
)

logger = logging.getLogger(__name__)


CANONICAL_FIELDS = [
    "actor",
    "action",
    "object",
    "location",
    "time",
    "magnitude",
    "event_type",
    "claim_type",
    "source_stance",
    "key_entities",
    "impact_hint",
    "canonical_event_text",
    "evidence_span",
    "confidence_score",
]


def should_canonicalize(item: RssItem, mode: str = "selective") -> bool:
    if mode in {"false", "off", "none"}:
        return False
    if mode in {"true", "all"}:
        return True
    text = compact_text(item.title, item.summary, item.article_lead, limit=2000)
    return (
        len((item.summary or "").strip()) < 120
        or is_generic_title(item.title or "")
        or is_major_or_black_swan(text)
        or len(text) < 220
    )


def canonicalize_item(
    item: RssItem,
    mode: str = "selective",
    model_overrides: dict[str, object] | None = None,
) -> dict[str, object]:
    input_text = compact_text(item.title, item.summary, item.article_lead, item.category, item.desk, limit=3000)
    input_hash = canonical_event_hash(input_text)
    if item.canonical_event_hash == input_hash and item.canonical_event_text:
        return {
            "changed": False,
            "canonical_event": item.canonical_event,
            "canonical_event_text": item.canonical_event_text,
            "canonical_event_hash": item.canonical_event_hash,
            "canonicalized_at": item.canonicalized_at,
            "canonical_model": item.canonical_model,
            "canonical_input_tokens": 0,
            "canonical_output_tokens": 0,
            "canonical_cost_usd": 0.0,
        }
    if not should_canonicalize(item, mode=mode):
        fallback = build_fallback_canonical_event(item)
        return {
            "changed": True,
            "canonical_event": fallback,
            "canonical_event_text": fallback["canonical_event_text"],
            "canonical_event_hash": input_hash,
            "canonicalized_at": None,
            "canonical_model": "rule_fallback",
            "canonical_input_tokens": 0,
            "canonical_output_tokens": 0,
            "canonical_cost_usd": 0.0,
        }

    try:
        prompt = _render_prompt(item, input_text)
        route = resolve_model_route("w4_canonicalization", model_overrides)
        payload, input_tokens, output_tokens = gemini_client.generate_json(
            prompt,
            model=route.model,
        )
        canonical = validate_canonical_event(payload)
        return {
            "changed": True,
            "canonical_event": canonical,
            "canonical_event_text": canonical["canonical_event_text"],
            "canonical_event_hash": input_hash,
            "canonicalized_at": utc_now_iso(),
            "canonical_model": route.model,
            "canonical_input_tokens": int(input_tokens or 0),
            "canonical_output_tokens": int(output_tokens or 0),
            "canonical_cost_usd": compute_llm_cost(
                route.model,
                int(input_tokens or 0),
                int(output_tokens or 0),
            ),
        }
    except Exception as exc:
        logger.warning("Canonicalization fallback for %s: %s", item.item_id, exc)
        fallback = build_fallback_canonical_event(item)
        return {
            "changed": True,
            "canonical_event": fallback,
            "canonical_event_text": fallback["canonical_event_text"],
            "canonical_event_hash": input_hash,
            "canonicalized_at": utc_now_iso(),
            "canonical_model": "rule_fallback",
            "canonicalization_error": str(exc)[:200],
            "canonical_input_tokens": 0,
            "canonical_output_tokens": 0,
            "canonical_cost_usd": 0.0,
        }


def build_fallback_canonical_event(item: RssItem) -> dict:
    text = compact_text(item.title, item.summary, item.article_lead, limit=800)
    entities = extract_keywords(text)
    return validate_canonical_event(
        {
            "actor": entities[0] if entities else "",
            "action": "",
            "object": entities[1] if len(entities) > 1 else "",
            "location": item.market_level or "",
            "time": item.published_at or item.first_seen_at,
            "magnitude": "",
            "event_type": item.category or item.desk or "unknown",
            "claim_type": "reported",
            "source_stance": "unknown",
            "key_entities": entities,
            "impact_hint": item.category or item.desk or "",
            "canonical_event_text": text,
            "evidence_span": (item.summary or item.title or "")[:240],
            "confidence_score": 0.45,
        }
    )


def validate_canonical_event(payload: dict) -> dict:
    out = {}
    for field in CANONICAL_FIELDS:
        value = payload.get(field)
        if field == "key_entities":
            if not isinstance(value, list):
                value = []
            out[field] = [str(v)[:80] for v in value][:8]
        elif field == "confidence_score":
            try:
                out[field] = max(0.0, min(1.0, float(value)))
            except (TypeError, ValueError):
                out[field] = 0.0
        else:
            out[field] = str(value or "").strip()[:1000]
    if not out["canonical_event_text"]:
        pieces = [out["actor"], out["action"], out["object"], out["location"], out["time"]]
        out["canonical_event_text"] = compact_text(*pieces, limit=1000)
    return out


def _render_prompt(item: RssItem, input_text: str) -> str:
    schema = {field: "" for field in CANONICAL_FIELDS}
    schema["key_entities"] = []
    schema["confidence_score"] = 0.0
    return (
        "You convert RSS/news text into a neutral canonical event JSON.\n"
        "Return JSON only. Preserve facts, do not add interpretation.\n"
        "Fields must match this schema:\n"
        f"{json.dumps(schema, ensure_ascii=False)}\n\n"
        f"Publisher: {item.publisher}\n"
        f"Desk: {item.desk}\n"
        f"Category: {item.category}\n"
        f"Market level: {item.market_level}\n"
        f"Published at: {item.published_at}\n"
        f"Text:\n{input_text}"
    )
