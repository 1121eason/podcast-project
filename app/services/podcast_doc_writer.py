import logging
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.clients.docs_client import docs_client
from app.core.config import settings
from app.models.podcast import ScriptSegment

logger = logging.getLogger(__name__)


def _codex_update_note() -> str:
    try:
        tz = ZoneInfo(settings.BRIEFING_TIMEZONE or "UTC")
    except ZoneInfoNotFoundError:
        tz = timezone.utc
    return f"更新紀錄：{datetime.now(tz).strftime('%Y/%m/%d')} Codex 更新"


def _format_podcast_text(
    briefing_date: str,
    episode_title: str,
    script: str,
    segments: list[ScriptSegment],
    show_notes: str,
    themes_covered: list[str],
    word_count: int,
    duration_estimate: float,
    validation_warnings: list[str] | None = None,
) -> str:
    lines: list[str] = []
    lines.append(f"Informative AI Podcast — {briefing_date}")
    lines.append(_codex_update_note())
    lines.append("=" * 60)
    lines.append(f"Episode title：{episode_title}")
    lines.append(f"字數：{word_count}")
    lines.append(f"預估時長：{duration_estimate} 分鐘")
    lines.append(f"主題涵蓋：{', '.join(themes_covered) if themes_covered else '(空)'}")
    if validation_warnings:
        lines.append(f"驗證提醒：{'; '.join(validation_warnings)}")
    lines.append("備註：此文件為 Phase 5 自動備份與檢視稿，不是人工審稿關卡。")
    lines.append("")
    lines.append("=" * 60)
    lines.append("【完整文稿】")
    lines.append("=" * 60)
    lines.append("")
    lines.append(script)
    lines.append("")
    lines.append("")
    lines.append("=" * 60)
    lines.append("【段落結構】(給編輯參考)")
    lines.append("=" * 60)
    lines.append("")
    for seg in segments:
        type_label = {
            "opening": "開場",
            "top_changes": "今日重點",
            "theme": f"主題：{seg.theme or ''}",
            "closing": "結尾",
        }.get(seg.segment_type, seg.segment_type)
        lines.append(f"#{seg.position} [{type_label}] {seg.title}")
        lines.append(f"  時長：~{seg.duration_estimate_seconds}s")
        if seg.referenced_signal_ids:
            lines.append(f"  引用：{', '.join(seg.referenced_signal_ids[:5])}")
        lines.append("")

    lines.append("")
    lines.append("=" * 60)
    lines.append("【Show Notes】(給 Spotify / Apple Podcasts description)")
    lines.append("=" * 60)
    lines.append("")
    lines.append(show_notes)
    return "\n".join(lines)


def write_podcast_script_to_doc(
    briefing_date: str,
    episode_title: str,
    script: str,
    segments: list[ScriptSegment],
    show_notes: str,
    themes_covered: list[str],
    word_count: int,
    duration_estimate: float,
    validation_warnings: list[str] | None = None,
) -> tuple[Optional[str], Optional[str]]:
    title = episode_title or f"Informative AI Podcast — {briefing_date}"
    text = _format_podcast_text(
        briefing_date,
        episode_title,
        script,
        segments,
        show_notes,
        themes_covered,
        word_count,
        duration_estimate,
        validation_warnings,
    )

    if not docs_client.service:
        logger.warning("Docs client not ready, skipping podcast Google Doc write")
        return None, None

    try:
        doc = docs_client.create_document(title)
        doc_id = doc.get("documentId")
        if not doc_id:
            return None, None
        docs_client.insert_text(doc_id, text)
        return doc_id, f"https://docs.google.com/document/d/{doc_id}/edit"
    except Exception as exc:
        logger.error("Failed to write podcast script to Google Doc: %s", exc)
        return None, None
