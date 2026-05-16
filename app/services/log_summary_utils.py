from __future__ import annotations

from typing import Iterable, Mapping, MutableMapping


LOG_SUMMARY_VERSION = 1
MAX_LOG_LINES = 6
MAX_SAMPLES = 3

_PREFIXES = {"ok", "new", "repeat", "warn", "cost", "time", "skip"}


def tagged(prefix: str, message: str) -> str:
    clean_prefix = (prefix or "ok").strip().lower()
    if clean_prefix not in _PREFIXES:
        clean_prefix = "ok"
    clean_message = " ".join(str(message or "").split())
    return f"[{clean_prefix}] {clean_message}" if clean_message else ""


def sample_values(values: Iterable[object] | None, limit: int = MAX_SAMPLES) -> str:
    out: list[str] = []
    for value in values or []:
        text = " ".join(str(value or "").split())
        if not text:
            continue
        out.append(text)
        if len(out) >= limit:
            break
    return "、".join(out)


def sample_from_dicts(
    rows: Iterable[Mapping[str, object]] | None,
    fields: tuple[str, ...],
    limit: int = MAX_SAMPLES,
) -> str:
    samples: list[str] = []
    for row in rows or []:
        parts = []
        for field in fields:
            value = str(row.get(field) or "").strip()
            if value:
                parts.append(value)
        if parts:
            samples.append(" / ".join(parts))
        if len(samples) >= limit:
            break
    return sample_values(samples, limit=limit)


def seconds_text(duration_ms: object) -> str:
    try:
        ms = int(duration_ms or 0)
    except (TypeError, ValueError):
        ms = 0
    if ms < 1000:
        return f"{ms}ms"
    return f"{ms / 1000:.1f}s"


def cost_text(cost_usd: object) -> str:
    try:
        cost = float(cost_usd or 0.0)
    except (TypeError, ValueError):
        cost = 0.0
    return f"${cost:.6f}".rstrip("0").rstrip(".") if cost else "$0"


def token_text(input_tokens: object, output_tokens: object) -> str:
    try:
        in_tok = int(input_tokens or 0)
        out_tok = int(output_tokens or 0)
    except (TypeError, ValueError):
        in_tok = 0
        out_tok = 0
    return f"{in_tok} input / {out_tok} output tokens"


def add_log_summary(
    result: MutableMapping[str, object],
    lines: Iterable[str],
) -> MutableMapping[str, object]:
    cleaned = [str(line).strip() for line in lines if str(line or "").strip()]
    if not cleaned:
        cleaned = [tagged("ok", "完成，沒有特殊警示。")]
    result["log_summary_version"] = LOG_SUMMARY_VERSION
    result["log_summary"] = cleaned[:MAX_LOG_LINES]
    return result


def add_duplicate_log_summary(
    result: MutableMapping[str, object],
    workflow_label: str,
    run_bucket: str | None,
) -> MutableMapping[str, object]:
    bucket = run_bucket or "(none)"
    previous = result.get("log_summary")
    previous_lines = previous if isinstance(previous, list) else []
    return add_log_summary(
        result,
        [
            tagged(
                "skip",
                f"{workflow_label} run_bucket {bucket} 已完成或正在執行，跳過重跑昂貴步驟。",
            ),
            *[str(line) for line in previous_lines[: MAX_LOG_LINES - 1]],
        ],
    )
