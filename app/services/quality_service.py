from typing import Any


def build_quality_report(
    *,
    research_data: dict[str, Any],
    reviewed_briefing_text: str,
    script_text: str,
    source_links: list[str],
) -> dict[str, Any]:
    developments = research_data.get("top_developments") or []
    warnings = []
    checks = {
        "has_reviewed_briefing": bool(reviewed_briefing_text.strip()),
        "has_script": bool(script_text.strip()),
        "has_minimum_developments": len(developments) >= 3,
        "has_minimum_sources": len(source_links) >= 5,
        "all_developments_have_sources": all(
            bool(development.get("sources")) for development in developments
        ),
        "all_developments_have_business_implication": all(
            bool(str(development.get("business_implication", "")).strip())
            for development in developments
        ),
        "all_developments_have_confidence_level": all(
            development.get("confidence_level") in {"high", "medium", "low"}
            for development in developments
        ),
    }

    if not checks["has_minimum_developments"]:
        warnings.append("Fewer than 3 top developments were produced.")
    if not checks["has_minimum_sources"]:
        warnings.append("Fewer than 5 unique source links were collected.")
    if not checks["all_developments_have_sources"]:
        warnings.append("At least one development has no source link.")
    if not checks["all_developments_have_business_implication"]:
        warnings.append("At least one development is missing a business implication.")
    if not checks["all_developments_have_confidence_level"]:
        warnings.append("At least one development is missing a valid confidence level.")

    status = "pass" if all(checks.values()) else "needs_review"

    return {
        "status": status,
        "checks": checks,
        "warnings": warnings,
        "source_count": len(source_links),
        "development_count": len(developments),
    }
