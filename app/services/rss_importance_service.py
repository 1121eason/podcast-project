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
from app.clients.gemini_client import gemini_client
from app.clients.openai_client import openai_client
from app.core.config import settings
from app.models.signal import RssJudgementRun, RssSignal
from app.services.llm_cost_utils import compute_llm_cost
from app.services.log_summary_utils import (
    add_duplicate_log_summary,
    add_log_summary,
    cost_text,
    seconds_text,
    tagged,
    token_text,
)
from app.services.model_routing_service import (
    default_model_route,
    effective_model_routes,
    resolve_model_route,
    validate_model_overrides,
)
from app.services.rss_source_service import utc_now_iso
from app.services.signal_v2_utils import (
    MAJOR_ENTITY_PATTERNS,
    is_generic_title,
    is_major_or_black_swan,
)
from app.services.workflow_run_service import complete_workflow_run, fail_workflow_run, start_workflow_run

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

_VALID_PRIMARY_THEMES = {
    "geopolitics",
    "global_finance",
    "tech_ai",
    "semi_supply_chain",
    "corporate_moves",
    "other_signal",
}

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "importance_judgement_v1.txt"
PROMPT_TEMPLATE: Optional[str] = None

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
MARKET_WRAP_CAP = settings.JUDGE_CAP_MARKET_WRAP

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
SINGLE_CORP_CAP = settings.JUDGE_CAP_SINGLE_CORP

# SYSTEMIC_ENTITIES: corporate names that count as "too important to cap on a single-source
# earnings story" (the single_corp guard rail exception). Derived from MAJOR_ENTITY_PATTERNS
# (single source of truth in signal_v2_utils) by excluding non-corporate entities like
# central banks (Fed/ECB) and private AI labs that don't have public earnings.
_NON_CORPORATE_PATTERNS = {
    "fed", "federal reserve", "ecb", "boj",
    "央行", "聯準會",
    "openai", "anthropic",  # private, no public earnings yet
}
SYSTEMIC_ENTITIES = {
    e for e in MAJOR_ENTITY_PATTERNS if e.lower() not in _NON_CORPORATE_PATTERNS
} | {"saudi aramco"}  # add energy giant not in MAJOR_ENTITY_PATTERNS

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
PUBLIC_HEALTH_CAP = settings.JUDGE_CAP_PUBLIC_HEALTH

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
ANALYSIS_CAP = settings.JUDGE_CAP_ANALYSIS


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
    # Title must match; summary alone is too noisy (caught wind power / metaphorical 感染 cases).
    if not PUBLIC_HEALTH_REGEX.search(title or ""):
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
    triggered: list[str] = []  # which guard rules fired (for monitoring)

    if _is_market_wrap(title) and score > MARKET_WRAP_CAP:
        note_parts.append(f"[guard] market_wrap title cap {MARKET_WRAP_CAP}")
        triggered.append("market_wrap")
        payload["importance_score"] = MARKET_WRAP_CAP
        payload["impact_type"] = "market"

    if _is_single_corp_low_heat(
        title,
        source_count,
        topic_heat,
        payload.get("key_entities") or [],
    ) and payload["importance_score"] > SINGLE_CORP_CAP:
        note_parts.append(f"[guard] single-source non-systemic earnings cap {SINGLE_CORP_CAP}")
        triggered.append("single_corp")
        payload["importance_score"] = SINGLE_CORP_CAP

    if _is_public_health_no_market(
        title,
        summary,
        payload.get("key_entities") or [],
    ) and payload["importance_score"] > PUBLIC_HEALTH_CAP:
        note_parts.append(f"[guard] public-health non-market cap {PUBLIC_HEALTH_CAP}")
        triggered.append("public_health")
        payload["importance_score"] = PUBLIC_HEALTH_CAP

    if _is_single_source_analysis(title, source_count) and payload["importance_score"] > ANALYSIS_CAP:
        note_parts.append(f"[guard] analysis/feature single-source cap {ANALYSIS_CAP}")
        triggered.append("analysis")
        payload["importance_score"] = ANALYSIS_CAP

    if note_parts:
        existing = (payload.get("heat_vs_importance_note") or "").strip()
        guard_note = "; ".join(note_parts)
        payload["heat_vs_importance_note"] = (
            f"{guard_note} | {existing}" if existing else guard_note
        )
    payload["_guard_rails_triggered"] = triggered
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

    primary_theme = str(payload.get("primary_theme") or "other_signal").strip()
    if primary_theme not in _VALID_PRIMARY_THEMES:
        primary_theme = "other_signal"

    return {
        "importance_score": int(score),
        "impact_type": impact,
        "primary_theme": primary_theme,
        "what_happened": str(payload.get("what_happened") or "").strip()[:200],
        "why_matters": str(payload.get("why_matters") or "").strip()[:300],
        "who_affected": str(payload.get("who_affected") or "").strip()[:300],
        "what_next": str(payload.get("what_next") or "").strip()[:300],
        "key_entities": [str(x) for x in key_entities][:5],
        "regions": [str(x) for x in regions][:5],
        "reasoning": reasoning,
        "heat_vs_importance_note": note,
    }


def _call_judgement_model(
    prompt: str,
    model_overrides: Optional[dict[str, object]] = None,
) -> tuple[dict, int, int, str]:
    """Returns (payload, input_tokens, output_tokens, model_used)."""
    route = resolve_model_route("w5_judgement", model_overrides)
    if route.provider == "openai" and openai_client.is_ready:
        model = route.model
        payload, in_tok, out_tok = openai_client.generate_json(
            prompt,
            model=model,
            reasoning_effort=route.reasoning_effort or settings.JUDGEMENT_REASONING_EFFORT,
        )
        return payload, in_tok, out_tok, model
    # fallback to Gemini
    model = route.model if route.provider == "gemini" else default_model_route("w5_judgement", "gemini").model
    payload, in_tok, out_tok = gemini_client.generate_json(prompt, model=model)
    return payload, in_tok, out_tok, model


def _judge_one(
    signal: RssSignal,
    model_overrides: Optional[dict[str, object]] = None,
) -> dict[str, object]:
    prompt = _render_prompt(signal)
    last_exc: Optional[Exception] = None
    for attempt in range(2):
        try:
            payload, input_tokens, output_tokens, model_used = _call_judgement_model(prompt, model_overrides)
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
                "model_used": model_used,
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
    quality_gate: str = "supported_or_promoted",
    run_bucket: Optional[str] = None,
    model_overrides: Optional[dict[str, object]] = None,
) -> dict[str, object]:
    started = time.monotonic()
    run_id = _generate_run_id()
    generated_at = utc_now_iso()
    since_iso = _since_iso(since_hours)
    request_payload = {
        "since_hours": since_hours,
        "max_workers": max_workers,
        "force": force,
        "max_signals_per_run": max_signals_per_run,
        "quality_gate": quality_gate,
        "run_bucket": run_bucket,
        "model_overrides": validate_model_overrides(model_overrides),
    }
    should_skip, workflow_run_id, existing_summary = start_workflow_run(
        "signal_judge",
        run_bucket,
        request_payload,
    )
    if should_skip:
        out = dict(existing_summary)
        out.update({"skipped_duplicate": True, "run_bucket": run_bucket, "workflow_run_id": workflow_run_id})
        add_duplicate_log_summary(out, "W5 Judge", run_bucket)
        return out

    signals = firestore_client.list_recent_signals(since_iso, limit=2000)

    candidates: list[RssSignal] = []
    skipped_unverified = 0
    skipped_already_judged = 0
    skipped_quality_gate = 0
    for signal in signals:
        if not signal.cluster_status:
            skipped_unverified += 1
            continue
        if signal.importance_score is not None and not force:
            skipped_already_judged += 1
            continue
        if not _passes_quality_gate(signal, quality_gate):
            skipped_quality_gate += 1
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
    # P1 monitoring: accumulate guard-rail trigger counts across all signals in this run
    guard_rails_triggered: dict[str, int] = {
        "market_wrap": 0,
        "single_corp": 0,
        "public_health": 0,
        "analysis": 0,
    }
    # Per-model token tally so cost is correct even if some signals go to OpenAI and others to Gemini
    tokens_by_model: dict[str, dict[str, int]] = {}

    if candidates:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_judge_one, s, model_overrides): s for s in candidates}
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
                signal.primary_theme = payload["primary_theme"]
                signal.what_happened = payload["what_happened"]
                signal.why_matters = payload["why_matters"]
                signal.who_affected = payload["who_affected"]
                signal.what_next = payload["what_next"]
                signal.key_entities = payload["key_entities"]
                signal.regions = payload["regions"]
                signal.reasoning = payload["reasoning"]
                signal.heat_vs_importance_note = payload["heat_vs_importance_note"]
                signal.judged_at = utc_now_iso()
                signal.judge_model = result.get("model_used", "unknown")
                signal.judge_input_tokens = result["input_tokens"]
                signal.judge_output_tokens = result["output_tokens"]
                model_used = signal.judge_model
                judged_signals.append(signal)
                score_done += 1
                score_sum += payload["importance_score"]
                score_counts[_bucket_score(payload["importance_score"])] += 1
                total_input_tokens += result["input_tokens"]
                total_output_tokens += result["output_tokens"]
                # Tally per-model tokens for accurate pricing
                m_bucket = tokens_by_model.setdefault(model_used, {"input": 0, "output": 0})
                m_bucket["input"] += result["input_tokens"]
                m_bucket["output"] += result["output_tokens"]
                # Accumulate guard rail triggers from this signal
                for rule in (payload.get("_guard_rails_triggered") or []):
                    guard_rails_triggered[rule] = guard_rails_triggered.get(rule, 0) + 1

        firestore_client.upsert_rss_signals(judged_signals)

    # P0 fix: compute cost per actual model used (no more hardcoded provider-keyed pricing)
    cost_usd = sum(
        compute_llm_cost(model, tok["input"], tok["output"])
        for model, tok in tokens_by_model.items()
    )
    duration_ms = int((time.monotonic() - started) * 1000)
    avg_score = round(score_sum / score_done, 2) if score_done else 0.0

    # judge_model: most-used model across this run (handles mixed-provider runs)
    if tokens_by_model:
        judge_model = max(tokens_by_model.items(), key=lambda kv: kv[1]["input"] + kv[1]["output"])[0]
    else:
        judge_model = resolve_model_route("w5_judgement", model_overrides).model

    run = RssJudgementRun(
        run_id=run_id,
        generated_at=generated_at,
        since_hours=since_hours,
        candidate_signal_count=len(candidates),
        judged_signal_count=score_done,
        skipped_already_judged_count=skipped_already_judged,
        skipped_unverified_count=skipped_unverified,
        skipped_quality_gate_count=skipped_quality_gate,
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
        judge_model=judge_model,
        guard_rails_triggered=guard_rails_triggered,
        errors=errors[:10],
    )
    firestore_client.create_judgement_run(run)
    result = run.model_dump()
    result["quality_gate"] = quality_gate
    result["run_bucket"] = run_bucket
    result["workflow_run_id"] = workflow_run_id
    result["skipped_duplicate"] = False
    result["model_routing"] = effective_model_routes(model_overrides, ["w5_judgement"])
    add_log_summary(result, _compose_judge_log_summary(result))
    complete_workflow_run(workflow_run_id, result)
    return result


def _compose_judge_log_summary(result: dict[str, object]) -> list[str]:
    skipped_total = (
        int(result.get("skipped_already_judged_count") or 0)
        + int(result.get("skipped_unverified_count") or 0)
        + int(result.get("skipped_quality_gate_count") or 0)
    )
    lines = [
        tagged(
            "ok",
            (
                f"W5 Judge 候選 {result.get('candidate_signal_count', 0)} 個，"
                f"成功評分 {result.get('judged_signal_count', 0)} 個，失敗 {result.get('failed_signal_count', 0)} 個。"
            ),
        ),
        tagged(
            "new",
            (
                f"分數分布：80+={result.get('score_80plus_count', 0)}、"
                f"60-79={result.get('score_60_79_count', 0)}、"
                f"40-59={result.get('score_40_59_count', 0)}、"
                f"<40={result.get('score_below_40_count', 0)}，平均 {result.get('avg_score', 0)}。"
            ),
        ),
    ]
    if skipped_total:
        lines.append(
            tagged(
                "repeat",
                (
                    f"略過 {skipped_total} 個：已評分 {result.get('skipped_already_judged_count', 0)}、"
                    f"未驗證 {result.get('skipped_unverified_count', 0)}、quality gate {result.get('skipped_quality_gate_count', 0)}。"
                ),
            )
        )
    guard_rails = result.get("guard_rails_triggered") if isinstance(result.get("guard_rails_triggered"), dict) else {}
    guard_text = ", ".join(f"{k}={v}" for k, v in guard_rails.items() if v)
    if guard_text:
        lines.append(tagged("warn", f"guard rail 觸發：{guard_text}。"))
    lines.append(
        tagged(
            "cost",
            (
                f"LLM 成本 {cost_text(result.get('total_cost_usd'))}，"
                f"{token_text(result.get('total_input_tokens'), result.get('total_output_tokens'))}，"
                f"model={result.get('judge_model') or 'unknown'}。"
            ),
        )
    )
    lines.append(tagged("time", f"總耗時 {seconds_text(result.get('duration_ms'))}。"))
    return lines


def _passes_quality_gate(signal: RssSignal, quality_gate: str) -> bool:
    gate = (quality_gate or "supported_or_promoted").lower()
    if gate in {"all", "none", "off"}:
        return True
    title_blob = " ".join(
        [
            signal.representative_title or "",
            signal.representative_summary or "",
            " ".join(signal.key_entities or []),
        ]
    )
    if is_generic_title(signal.representative_title or ""):
        return False
    if signal.signal_status in {"supported", "confirmed", "promoted"}:
        return True
    if signal.cluster_status == "confirmed":
        return True
    if signal.source_count >= 2 and signal.cluster_status in {"partially_supported", "regional_only"}:
        return True
    if signal.source_count <= 1 and signal.topic_heat == "low":
        return is_major_or_black_swan(title_blob)
    return False
