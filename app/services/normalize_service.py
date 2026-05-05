import json
from app.models.research_output import ResearchOutputSchema
from app.core.logging import logger

def _extract_json_payload(raw_output: str) -> str:
    cleaned_output = raw_output.strip()

    if cleaned_output.startswith("```"):
        lines = cleaned_output.splitlines()
        if len(lines) >= 3 and lines[-1].strip() == "```":
            cleaned_output = "\n".join(lines[1:-1]).strip()

    if cleaned_output.startswith("json"):
        cleaned_output = cleaned_output[4:].strip()

    if cleaned_output.startswith("{") and cleaned_output.endswith("}"):
        return cleaned_output

    json_start = cleaned_output.find("{")
    json_end = cleaned_output.rfind("}")
    if json_start == -1 or json_end == -1 or json_start >= json_end:
        raise ValueError("No JSON object found in research output")
    return cleaned_output[json_start:json_end + 1]


def normalize_research_output(raw_output: str) -> dict:
    try:
        json_payload = _extract_json_payload(raw_output)
        data = json.loads(json_payload)
        validated = ResearchOutputSchema(**data)
        return validated.model_dump()
    except Exception as e:
        logger.error(f"Failed to normalize research output: {e}")
        raise ValueError(f"Invalid research output schema: {e}")
