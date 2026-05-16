from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.security import require_admin_token
from app.api.model_routing_payloads import ModelRouteOverride
from app.services.model_routing_service import (
    CACHE_TTL_SECONDS,
    effective_model_routes,
    get_runtime_model_routing,
    route_keys,
    set_runtime_model_routing,
    validate_model_overrides,
)

router = APIRouter()


class ModelRoutingPatchRequest(BaseModel):
    routes: dict[str, ModelRouteOverride] = Field(default_factory=dict)
    note: Optional[str] = None


@router.get("/model-routing")
def get_model_routing(_: None = Depends(require_admin_token)):
    try:
        runtime = get_runtime_model_routing()
        return {
            "version": 1,
            "available_routes": route_keys(),
            "cache_ttl_seconds": CACHE_TTL_SECONDS,
            "runtime_config": runtime,
            "effective_routes": effective_model_routes(),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.patch("/model-routing")
def patch_model_routing(
    request: ModelRoutingPatchRequest,
    _: None = Depends(require_admin_token),
):
    try:
        raw_routes = {
            key: value.model_dump(exclude_none=True)
            for key, value in request.routes.items()
        }
        normalized = validate_model_overrides(raw_routes)
        runtime = set_runtime_model_routing(normalized, note=request.note)
        return {
            "version": 1,
            "runtime_config": runtime,
            "effective_routes": effective_model_routes(),
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
