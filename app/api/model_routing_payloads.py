from typing import Optional

from pydantic import BaseModel


class ModelRouteOverride(BaseModel):
    provider: Optional[str] = None
    model: Optional[str] = None
    reasoning_effort: Optional[str] = None


def dump_model_overrides(
    overrides: Optional[dict[str, ModelRouteOverride]],
) -> dict[str, dict[str, object]]:
    if not overrides:
        return {}
    return {
        key: value.model_dump(exclude_none=True)
        for key, value in overrides.items()
    }
