import logging
from typing import Optional

from app.clients.docs_client import docs_client
from app.models.signal import BriefingCategory, BriefingSection

logger = logging.getLogger(__name__)


def _format_briefing_text(
    briefing_date: str,
    overview: str,
    categories: list[BriefingCategory],
    signal_pool_health: dict,
) -> str:
    lines: list[str] = []
    lines.append(f"Signal Brief Daily — {briefing_date}")
    lines.append("=" * 60)
    lines.append("")
    lines.append("【今日總覽】")
    lines.append(overview)
    lines.append("")
    lines.append("=" * 60)
    lines.append("")

    for cat in categories:
        lines.append(f"━━━ {cat.title} ━━━")
        lines.append("")
        if cat.category_overview:
            lines.append(cat.category_overview)
            lines.append("")
        if not cat.sections:
            lines.append("（今日無達門檻訊號）")
            lines.append("")
            lines.append("")
            continue
        for idx, sec in enumerate(cat.sections, start=1):
            lines.append(f"{idx}. {sec.title}  [importance: {sec.importance_score}]")
            lines.append("")
            lines.append(sec.summary)
            lines.append("")
            if sec.impacted_sectors:
                lines.append(f"影響產業：{', '.join(sec.impacted_sectors)}")
            if sec.watch_points:
                lines.append("接下來看：")
                for w in sec.watch_points:
                    lines.append(f"  - {w}")
            if sec.referenced_urls:
                lines.append("參考來源：")
                for u in sec.referenced_urls:
                    lines.append(f"  - {u}")
            lines.append("")
            lines.append("---")
            lines.append("")
        lines.append("")

    lines.append("=" * 60)
    lines.append("【訊號池體檢】")
    if signal_pool_health.get("total_judged"):
        lines.append(f"總判分訊號：{signal_pool_health.get('total_judged')}")
    if signal_pool_health.get("high_importance_count") is not None:
        lines.append(f"達門檻訊號：{signal_pool_health.get('high_importance_count')}")
    if signal_pool_health.get("main_themes"):
        lines.append("今日主要主題：")
        for t in signal_pool_health["main_themes"]:
            lines.append(f"  - {t}")
    if signal_pool_health.get("coverage_gaps"):
        lines.append("覆蓋缺口：")
        for g in signal_pool_health["coverage_gaps"]:
            lines.append(f"  - {g}")
    return "\n".join(lines)


def write_briefing_to_doc(
    briefing_date: str,
    overview: str,
    categories: list[BriefingCategory],
    signal_pool_health: dict,
) -> tuple[Optional[str], Optional[str]]:
    title = f"Signal Brief Daily — {briefing_date}"
    text = _format_briefing_text(briefing_date, overview, categories, signal_pool_health)

    if not docs_client.service:
        logger.warning("Docs client not ready, skipping Google Doc write")
        return None, None

    try:
        doc = docs_client.create_document(title)
        doc_id = doc.get("documentId")
        if not doc_id:
            return None, None
        docs_client.insert_text(doc_id, text)
        return doc_id, f"https://docs.google.com/document/d/{doc_id}/edit"
    except Exception as exc:
        logger.error("Failed to write briefing to Google Doc: %s", exc)
        return None, None
