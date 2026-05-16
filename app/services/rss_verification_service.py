import logging
import time
from datetime import datetime, timedelta, timezone

from app.clients.firestore_client import firestore_client
from app.models.signal import RssSignal
from app.services.log_summary_utils import add_log_summary, seconds_text, tagged
from app.services.publisher_groups import count_independent_groups
from app.services.rss_source_service import utc_now_iso

logger = logging.getLogger(__name__)


def determine_cluster_status(signal: RssSignal) -> str:
    sources = signal.source_count
    if sources <= 1:
        return "single_source"

    independent_groups = count_independent_groups(signal.publishers)
    market_levels = set(signal.market_levels or [])
    has_global = "Global" in market_levels

    if sources >= 3 and independent_groups >= 3:
        return "confirmed"
    if sources >= 3 and has_global and independent_groups >= 2:
        return "confirmed"
    if sources >= 3 and len(market_levels) == 1 and not has_global:
        return "regional_only"
    return "partially_supported"


def determine_topic_heat(signal: RssSignal) -> str:
    sources = signal.source_count
    publishers = signal.publisher_count

    if sources >= 5 and publishers >= 4:
        return "viral"
    if sources >= 3 and publishers >= 3:
        return "high"
    if sources >= 2:
        return "medium"
    return "low"


def _since_iso(hours: int) -> str:
    return (
        (datetime.now(timezone.utc) - timedelta(hours=hours))
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def verify_signals(since_hours: int = 24, force: bool = False) -> dict[str, object]:
    started = time.monotonic()
    since_iso = _since_iso(since_hours)
    signals = firestore_client.list_recent_signals(since_iso, limit=2000)

    candidates: list[RssSignal] = []
    for signal in signals:
        if not force and signal.cluster_status and signal.topic_heat:
            continue
        candidates.append(signal)

    if not candidates:
        result = {
            "since_hours": since_hours,
            "total_signal_count": len(signals),
            "verified_signal_count": 0,
            "skipped_already_verified_count": len(signals),
            "status_distribution": {},
            "heat_distribution": {},
            "duration_ms": int((time.monotonic() - started) * 1000),
        }
        add_log_summary(result, _compose_verify_log_summary(result))
        return result

    verified_at = utc_now_iso()
    status_counts: dict[str, int] = {}
    heat_counts: dict[str, int] = {}

    updates: list[RssSignal] = []
    for signal in candidates:
        status = determine_cluster_status(signal)
        heat = determine_topic_heat(signal)
        status_counts[status] = status_counts.get(status, 0) + 1
        heat_counts[heat] = heat_counts.get(heat, 0) + 1
        signal.cluster_status = status
        signal.topic_heat = heat
        updates.append(signal)

    firestore_client.upsert_rss_signals(updates)

    result = {
        "since_hours": since_hours,
        "verified_at": verified_at,
        "total_signal_count": len(signals),
        "verified_signal_count": len(updates),
        "skipped_already_verified_count": len(signals) - len(updates),
        "status_distribution": status_counts,
        "heat_distribution": heat_counts,
        "duration_ms": int((time.monotonic() - started) * 1000),
    }
    add_log_summary(result, _compose_verify_log_summary(result))
    return result


def _compose_verify_log_summary(result: dict[str, object]) -> list[str]:
    status_distribution = result.get("status_distribution") if isinstance(result.get("status_distribution"), dict) else {}
    heat_distribution = result.get("heat_distribution") if isinstance(result.get("heat_distribution"), dict) else {}
    status_text = ", ".join(f"{k}={v}" for k, v in status_distribution.items()) or "無新驗證"
    heat_text = ", ".join(f"{k}={v}" for k, v in heat_distribution.items()) or "無新驗證"
    return [
        tagged(
            "ok",
            (
                f"W5 Verify 檢查 {result.get('total_signal_count', 0)} 個 signal，"
                f"更新 {result.get('verified_signal_count', 0)} 個，"
                f"已驗證略過 {result.get('skipped_already_verified_count', 0)} 個。"
            ),
        ),
        tagged("ok", f"cluster_status 分布：{status_text}。"),
        tagged("ok", f"topic_heat 分布：{heat_text}。"),
        tagged("time", f"總耗時 {seconds_text(result.get('duration_ms'))}。"),
    ]
