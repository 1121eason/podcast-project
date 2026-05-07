import json
import logging
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from app.clients.firestore_client import firestore_client
from app.clients.gemini_client import JUDGEMENT_MODEL, gemini_client
from app.models.signal import RssJudgementRun, RssSignal
from app.services.rss_source_service import utc_now_iso

logger = logging.getLogger(__name__)

_VALID_IMPACT_TYPES = {
    "market",
    "policy",
    "corporate",
    "tech",
    "industry",
    "macro",
    "noise",
}

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "importance_judgement_v1.txt"
PROMPT_TEMPLATE: Optional[str] = None
COST_PER_1K_INPUT_TOKENS = 1.25 / 1000
COST_PER_1K_OUTPUT_TOKENS = 10.0 / 1000

SUMMARY_CHAR_LIMIT = 300

_MARKET_WRAP_PATTERNS = [
    r"盤後",
    r"盤前",
    r"盤中",
    r"收盤",
    r"開盤",
    r"收漲",
    r"收跌",
    r"收紅",
    r"收黑",
    r"盤勢",
    r"期指",
    r"大盤",
    r"指數",
    r"closing\s*bell",
    r"market\s*close",
    r"market\s*wrap",
    r"closes\s+higher",
    r"closes\s+lower",
    r"futures\s+rise",
    r"futures\s+fall",
]
MARKET_WRAP_REGEX = re.compile("|".join(_MARKET_WRAP_PATTERNS), re.IGNORECASE)
MARKET_WRAP_CAP = 45

_SINGLE_CORP_EARNINGS_PATTERNS = [
    r"earnings",
    r"財報",
    r"季報",
    r"營收",
    r"\bbeat\b",
    r"\bmiss\b",
    r"\bguidance\b",
    r"outlook",
]
SINGLE_CORP_REGEX = re.compile("|".join(_SINGLE_CORP_EARNINGS_PATTERNS), re.IGNORECASE)
SINGLE_CORP_CAP = 65

SYSTEMIC_ENTITIES = {
    "Apple", "Microsoft", "NVIDIA", "Google", "Alphabet", "Amazon",
    "Meta", "Tesla", "TSMC", "Berkshire", "JPMorgan", "ExxonMobil",
    "ASML", "Samsung", "Saudi Aramco",
}

_PUBLIC_HEALTH_PATTERNS = [
    r"hantavirus",
    r"漢他病毒",
    r"\bvirus\b",
    r"病毒",
    r"\boutbreak\b",
    r"疫情",
    r"\bepidemic\b",
    r"\bpandemic\b",
    r"\binfection\b",
    r"感染",
    r"傳染",
    r"\bH1N1\b",
    r"\bH5N1\b",
    r"\bcovid\b",
    r"新冠",
    r"\bdisease\b",
]
PUBLIC_HEALTH_REGEX = re.compile("|".join(_PUBLIC_HEALTH_PATTERNS), re.IGNORECASE)
PUBLIC_HEALTH_CAP = 65

_ANALYSIS_FEATURE_PATTERNS = [
    r"^為何",
    r"為何.{1,15}加碼",
    r"為何.{1,15}下跌",
    r"為何.{1,15}飆漲",
    r"^解析",
    r"^深度",
    r"^獨家分析",
    r"^Why\s+is",
    r"^Why\s+does",
    r"^Why\s+the",
    r"Here'?s\s+how",
    r"Here'?s\s+why",
    r"^What\s+to\s+expect",
    r"^Inside",
    r"^Explainer",
    r"專欄",
    r"觀察",
    r"分析師.{0,5}解讀",
    r"投資人.{0,5}解讀",
    r"從.{1,10}看.{1,10}",
]
ANALYSIS_REGEX = re.compile("|".join(_ANALYSIS_FEATURE_PATTERNS), re.IGNORECASE)
ANALYSIS_CAP = 60


def _is_market_wrap(title: str) -> bool:
    if not title:
        return False
    return bool(MARKET_WRAP_REGEX.search(title))


def _is_single_corp_low_heat(signal_title: str, source_count: int, topic_heat: str, key_entities: list[str]) -> bool:
    if source_count > 1:
        return False
    if topic_heat not in ("low", "medium"):
        return False
    if not SINGLE_CORP_REGEX.search(signal_title or ""):
        return False
    for entity in key_entities or []:
        for systemic in SYSTEMIC_ENTITIES:
            if systemic.lower() in entity.lower():
                return False
    return True


def _has_market_entity(key_entities: list[str]) -> bool:
    market_keywords = ["nvidia", "apple", "tsmc", "amazon", "microsoft", "google",
                       "amd", "tesla", "stock", "market", "earnings", "fed", "ecb",
                       "央行", "股", "etf", "fund", "bond", "treasury", "oil",
                       "原油", "黃金", "gold", "btc", "bitcoin", "美元", "日圓",
                       "exchange", "interest rate", "inflation", "通膨", "cpi", "pmi"]
    blob = " ".join(key_entities or []).lower()
    return any(k in blob for k in market_keywords)


def _is_public_health_no_market(title: str, summary: str, key_entities: list[str]) -> bool:
    if not PUBLIC_HEALTH_REGEX.search(title or "") and not PUBLIC_HEALTH_REGEX.search(summary or ""):
        return False
    return not _has_market_entity(key_entities)


def _is_single_source_analysis(title: str, source_count: int) -> bool:
    if source_count > 1:
        return False
    return bool(ANALYSIS_REGEX.search(title or ""))


def _load_prompt() -> str:
    global PROMPT_TEMPLATE
    if PROMPT_TEMPLATE is None:
        PROMPT_TEMPLATE = PROMPT_PATH.read_text(encoding="utf-8")
    return PROMPT_TEMPLATE


def _since_iso(hours: int) -> str:
    return (
        (datetime.now(timezone.utc) - timedelta(hours=hours))
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _generate_run_id() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"judge_{ts}_{uuid.uuid4().hex[:8]}"


def _render_prompt(signal: RssSignal) -> str:
    template = _load_prompt()
    return template.format(
        representative_title=signal.representative_title or "(no title)",
        representative_summary=(signal.representative_summary or "")[:SUMMARY_CHAR_LIMIT],
        representative_published_at=signal.representative_published_at or "(unknown)",
        source_count=signal.source_count,
        publisher_count=signal.publisher_count,
        publishers=", ".join(signal.publishers or []),
        cluster_status=signal.cluster_status or "unknown",
        topic_heat=signal.topic_heat or "unknown",
        market_levels=", ".join(signal.market_levels or []),
        desks=", ".join(signal.desks or []),
    )


def _apply_guard_rails(
    payload: dict,
    title: str,
    summary: str,
    source_count: int,
    topic_heat: str,
) -> dict:
    score = payload["importance_score"]
    note_parts: list[str] = []

    if _is_market_wrap(title) and score > MARKET_WRAP_CAP:
        note_parts.append(f"[guard] market_wrap title cap {MARKET_WRAP_CAP}")
        payload["importance_score"] = MARKET_WRAP_CAP
        payload["impact_type"] = "market"

    if _is_single_corp_low_heat(
        title,
        source_count,
        topic_heat,
        payload.get("key_entities") or [],
    ) and payload["importance_score"] > SINGLE_CORP_CAP:
        note_parts.append(f"[guard] single-source non-systemic earnings cap {SINGLE_CORP_CAP}")
        payload["importance_score"] = SINGLE_CORP_CAP

    if _is_public_health_no_market(
        title,
        summary,
        payload.get("key_entities") or [],
    ) and payload["importance_score"] > PUBLIC_HEALTH_CAP:
        note_parts.append(f"[guard] public-health non-market cap {PUBLIC_HEALTH_CAP}")
        payload["importance_score"] = PUBLIC_HEALTH_CAP

    if _is_single_source_analysis(title, source_count) and payload["importance_score"] > ANALYSIS_CAP:
        note_parts.append(f"[guard] analysis/feature single-source cap {ANALYSIS_CAP}")
        payload["importance_score"] = ANALYSIS_CAP

    if note_parts:
        existing = (payload.get("heat_vs_importance_note") or "").strip()
        guard_note = "; ".join(note_parts)
        payload["heat_vs_importance_note"] = (
            f"{guard_note} | {existing}" if existing else guard_note
        )
    return payload


def _validate_payload(payload: dict) -> dict:
    score = payload.get("importance_score")
    if not isinstance(score, int):
        try:
            score = int(score)
        except (TypeError, ValueError):
            raise ValueError("importance_score is missing or not int")
    if score < 0 or score > 100:
        raise ValueError(f"importance_score out of range: {score}")

    impact = payload.get("impact_type")
    if impact not in _VALID_IMPACT_TYPES:
        raise ValueError(f"impact_type invalid: {impact}")

    key_entities = payload.get("key_entities") or []
    if not isinstance(key_entities, list):
        raise ValueError("key_entities must be list")
    regions = payload.get("regions") or []
    if not isinstance(regions, list):
        raise ValueError("regions must be list")

    reasoning = str(payload.get("reasoning") or "").strip()
    note = str(payload.get("heat_vs_importance_note") or "").strip()

    return {
        "importance_score": int(score),
        "impact_type": impact,
        "key_entities": [str(x) for x in key_entities][:5],
        "regions": [str(x) for x in regions][:5],
        "reasoning": reasoning,
        "heat_vs_importance_note": note,
    }


def _judge_one(signal: RssSignal) -> dict[str, object]:
    prompt = _render_prompt(signal)
    last_exc: Optional[Exception] = None
    for attempt in range(2):
        try:
            payload, input_tokens, output_tokens = gemini_client.generate_json(prompt)
            validated = _validate_payload(payload)
            validated = _apply_guard_rails(
                validated,
                title=signal.representative_title or "",
                summary=signal.representative_summary or "",
                source_count=signal.source_count,
                topic_heat=signal.topic_heat or "",
            )
            return {
                "signal_id": signal.signal_id,
                "ok": True,
                "payload": validated,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
            }
        except (json.JSONDecodeError, ValueError, KeyError) as exc:
            last_exc = exc
            logger.warning(
                "Judge parse failed for %s attempt %d: %s",
                signal.signal_id,
                attempt + 1,
                exc,
            )
        except Exception as exc:
            last_exc = exc
            logger.warning(
                "Judge call failed for %s attempt %d: %s",
                signal.signal_id,
                attempt + 1,
                exc,
            )
    return {
        "signal_id": signal.signal_id,
        "ok": False,
        "error": str(last_exc) if last_exc else "unknown",
    }


def _bucket_score(score: int) -> str:
    if score >= 80:
        return "score_80plus_count"
    if score >= 60:
        return "score_60_79_count"
    if score >= 40:
        return "score_40_59_count"
    return "score_below_40_count"


def judge_signals(
    since_hours: int = 4,
    max_workers: int = 5,
    force: bool = False,
    max_signals_per_run: int = 200,
) -> dict[str, object]:
    started = time.monotonic()
    run_id = _generate_run_id()
    generated_at = utc_now_iso()
    since_iso = _since_iso(since_hours)

    signals = firestore_client.list_recent_signals(since_iso, limit=2000)

    candidates: list[RssSignal] = []
    skipped_unverified = 0
    skipped_already_judged = 0
    for signal in signals:
        if not signal.cluster_status:
            skipped_unverified += 1
            continue
        if signal.importance_score is not None and not force:
            skipped_already_judged += 1
            continue
        candidates.append(signal)

    if max_signals_per_run > 0:
        candidates = candidates[:max_signals_per_run]

    score_counts = {
        "score_80plus_count": 0,
        "score_60_79_count": 0,
        "score_40_59_count": 0,
        "score_below_40_count": 0,
    }
    score_sum = 0
    score_done = 0
    failed = 0
    total_input_tokens = 0
    total_output_tokens = 0
    errors: list[dict[str, str]] = []
    judged_signals: list[RssSignal] = []

    if candidates:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_judge_one, s): s for s in candidates}
            for future in as_completed(futures):
                signal = futures[future]
                try:
                    result = future.result()
                except Exception as exc:
                    failed += 1
                    errors.append({"signal_id": signal.signal_id, "error": str(exc)})
                    continue
                if not result["ok"]:
                    failed += 1
                    errors.append(
                        {"signal_id": result["signal_id"], "error": str(result.get("error"))}
                    )
                    continue
                payload = result["payload"]
                signal.importance_score = payload["importance_score"]
                signal.impact_type = payload["impact_type"]
                signal.key_entities = payload["key_entities"]
                signal.regions = payload["regions"]
                signal.reasoning = payload["reasoning"]
                signal.heat_vs_importance_note = payload["heat_vs_importance_note"]
                signal.judged_at = utc_now_iso()
                signal.judge_model = JUDGEMENT_MODEL
                signal.judge_input_tokens = result["input_tokens"]
                signal.judge_output_tokens = result["output_tokens"]
                judged_signals.append(signal)
                score_done += 1
                score_sum += payload["importance_score"]
                score_counts[_bucket_score(payload["importance_score"])] += 1
                total_input_tokens += result["input_tokens"]
                total_output_tokens += result["output_tokens"]

        firestore_client.upsert_rss_signals(judged_signals)

    cost_usd = (
        total_input_tokens / 1000 * COST_PER_1K_INPUT_TOKENS
        + total_output_tokens / 1000 * COST_PER_1K_OUTPUT_TOKENS
    )
    duration_ms = int((time.monotonic() - started) * 1000)
    avg_score = round(score_sum / score_done, 2) if score_done else 0.0

    run = RssJudgementRun(
        run_id=run_id,
        generated_at=generated_at,
        since_hours=since_hours,
        candidate_signal_count=len(candidates),
        judged_signal_count=score_done,
        skipped_already_judged_count=skipped_already_judged,
        skipped_unverified_count=skipped_unverified,
        failed_signal_count=failed,
        avg_score=avg_score,
        score_80plus_count=score_counts["score_80plus_count"],
        score_60_79_count=score_counts["score_60_79_count"],
        score_40_59_count=score_counts["score_40_59_count"],
        score_below_40_count=score_counts["score_below_40_count"],
        total_input_tokens=total_input_tokens,
        total_output_tokens=total_output_tokens,
        total_cost_usd=round(cost_usd, 6),
        duration_ms=duration_ms,
        judge_model=JUDGEMENT_MODEL,
        errors=errors[:10],
    )
    firestore_client.create_judgement_run(run)
    return run.model_dump()
