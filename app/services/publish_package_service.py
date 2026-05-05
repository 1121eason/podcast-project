from typing import Any

from app.services.quality_service import build_quality_report


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    deduped = []
    for value in values:
        cleaned = value.strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            deduped.append(cleaned)
    return deduped


def _collect_source_links(research_data: dict[str, Any]) -> list[str]:
    links = []
    for development in research_data.get("top_developments", []) or []:
        links.extend(str(source) for source in development.get("sources", []))

    for category_sources in (research_data.get("source_categories") or {}).values():
        if isinstance(category_sources, list):
            links.extend(str(source) for source in category_sources)
        else:
            links.append(str(category_sources))

    return _dedupe(links)


def _build_highlights(research_data: dict[str, Any]) -> list[str]:
    highlights = []
    for development in (research_data.get("top_developments") or [])[:5]:
        title = development.get("title", "").strip()
        implication = (
            development.get("business_implication")
            or development.get("why_it_matters")
            or development.get("what_happened")
            or ""
        ).strip()
        if title and implication:
            highlights.append(f"{title} - {implication}")
        elif title:
            highlights.append(title)
    return highlights


def build_publish_package(
    *,
    run_date: str,
    research_data: dict[str, Any],
    reviewed_briefing_text: str,
    script_text: str,
    doc_url: str,
    audio_url: str,
) -> dict[str, Any]:
    highlights = _build_highlights(research_data)
    source_links = _collect_source_links(research_data)
    quality_report = build_quality_report(
        research_data=research_data,
        reviewed_briefing_text=reviewed_briefing_text,
        script_text=script_text,
        source_links=source_links,
    )
    developments = research_data.get("top_developments") or [{}]
    lead_title = developments[0].get("title", "Daily Brief")
    short_summary = research_data.get("global_mood") or reviewed_briefing_text[:260].strip()

    description_lines = [
        f"Signal Brief {run_date}: {short_summary}",
        "",
        "本集重點：",
        *[f"- {highlight}" for highlight in highlights],
        "",
        "完整文字版與來源請見 show notes。此內容為情資摘要與商務觀察，不構成投資建議。",
    ]

    return {
        "episode_title": f"Signal Brief | {run_date} | {lead_title}",
        "short_summary": short_summary,
        "podcast_description": "\n".join(description_lines).strip(),
        "bullet_highlights": highlights,
        "source_links": source_links,
        "quality_report": quality_report,
        "doc_url": doc_url,
        "audio_url": audio_url,
        "script_character_count": len(script_text),
        "manual_upload_checklist": [
            "Download the MP3 from audio_url or attach it from Drive.",
            "Use episode_title as the podcast episode title.",
            "Paste podcast_description into the episode description/show notes.",
            "Include doc_url as the full written briefing link.",
            "Review source_links before publishing.",
            "Publish manually through the selected podcast hosting platform.",
        ],
    }
