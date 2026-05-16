import os
from dataclasses import asdict, dataclass
from typing import Mapping, Optional

from app.clients.firestore_client import firestore_client
from app.core.config import settings
from app.services.signal_v2_utils import utc_now_iso


CONFIG_COLLECTION_ID = "model_routing"
CACHE_TTL_SECONDS = 60


@dataclass(frozen=True)
class ModelRouteSpec:
    key: str
    default_provider: str
    allowed_providers: tuple[str, ...]
    gemini_model_setting: Optional[str] = None
    openai_model_setting: Optional[str] = None
    provider_setting: Optional[str] = None
    reasoning_effort_setting: Optional[str] = None


@dataclass(frozen=True)
class ModelRoute:
    key: str
    provider: str
    model: str
    reasoning_effort: Optional[str] = None
    source: str = "env"

    def model_dump(self) -> dict[str, object]:
        return asdict(self)


ROUTE_SPECS: dict[str, ModelRouteSpec] = {
    "w4_canonicalization": ModelRouteSpec(
        key="w4_canonicalization",
        default_provider="gemini",
        allowed_providers=("gemini",),
        gemini_model_setting="CANONICALIZATION_MODEL_GEMINI",
    ),
    "w4_match_adjudication": ModelRouteSpec(
        key="w4_match_adjudication",
        default_provider="gemini",
        allowed_providers=("gemini",),
        gemini_model_setting="MATCH_ADJUDICATION_MODEL_GEMINI",
    ),
    "w5_judgement": ModelRouteSpec(
        key="w5_judgement",
        default_provider="gemini",
        allowed_providers=("gemini", "openai"),
        gemini_model_setting="JUDGEMENT_MODEL_GEMINI",
        openai_model_setting="JUDGEMENT_MODEL_OPENAI",
        provider_setting="JUDGEMENT_PROVIDER",
        reasoning_effort_setting="JUDGEMENT_REASONING_EFFORT",
    ),
    "w6_business_impact": ModelRouteSpec(
        key="w6_business_impact",
        default_provider="gemini",
        allowed_providers=("gemini", "openai"),
        gemini_model_setting="IMPACT_MODEL_GEMINI",
        openai_model_setting="IMPACT_MODEL_OPENAI",
        provider_setting="IMPACT_PROVIDER",
        reasoning_effort_setting="IMPACT_REASONING_EFFORT",
    ),
    "w7_thread_refine": ModelRouteSpec(
        key="w7_thread_refine",
        default_provider="gemini",
        allowed_providers=("gemini",),
        gemini_model_setting="DAILY_CONSOLIDATION_MODEL_GEMINI",
    ),
    "w7_phase_assignment": ModelRouteSpec(
        key="w7_phase_assignment",
        default_provider="gemini",
        allowed_providers=("gemini",),
        gemini_model_setting="PHASE_ASSIGNMENT_MODEL_GEMINI",
    ),
    "w8_briefing": ModelRouteSpec(
        key="w8_briefing",
        default_provider="gemini",
        allowed_providers=("gemini", "openai"),
        gemini_model_setting="BRIEFING_MODEL_GEMINI",
        openai_model_setting="BRIEFING_MODEL_OPENAI",
        provider_setting="BRIEFING_PROVIDER",
        reasoning_effort_setting="BRIEFING_REASONING_EFFORT",
    ),
    "w9_podcast_script": ModelRouteSpec(
        key="w9_podcast_script",
        default_provider="gemini",
        allowed_providers=("gemini", "openai"),
        gemini_model_setting="PODCAST_SCRIPT_MODEL_GEMINI",
        openai_model_setting="PODCAST_SCRIPT_MODEL_OPENAI",
        provider_setting="PODCAST_SCRIPT_PROVIDER",
        reasoning_effort_setting="PODCAST_SCRIPT_REASONING_EFFORT",
    ),
}

_CACHE: dict[str, object] = {"loaded_at": 0.0, "config": {}}


def route_keys() -> list[str]:
    return list(ROUTE_SPECS.keys())


def default_model_route(route_key: str, provider: Optional[str] = None) -> ModelRoute:
    spec = _spec(route_key)
    chosen_provider = _normalize_provider(
        provider or _setting(spec.provider_setting) or spec.default_provider,
        spec,
    )
    model = _default_model_for_provider(spec, chosen_provider)
    return ModelRoute(
        key=route_key,
        provider=chosen_provider,
        model=model,
        reasoning_effort=_setting(spec.reasoning_effort_setting),
        source="env",
    )


def resolve_model_route(
    route_key: str,
    model_overrides: Optional[Mapping[str, object]] = None,
) -> ModelRoute:
    route = default_model_route(route_key)
    runtime_route = _runtime_route(route_key)
    if runtime_route:
        route = _merge_route(route, runtime_route, source="firestore")
    override_route = _override_route(route_key, model_overrides)
    if override_route:
        route = _merge_route(route, override_route, source="request")
    return route


def effective_model_routes(
    model_overrides: Optional[Mapping[str, object]] = None,
    keys: Optional[list[str]] = None,
) -> dict[str, dict[str, object]]:
    selected_keys = keys or route_keys()
    return {
        key: resolve_model_route(key, model_overrides).model_dump()
        for key in selected_keys
    }


def get_runtime_model_routing() -> dict[str, object]:
    raw = _load_runtime_config(use_cache=True)
    routes = raw.get("routes") if isinstance(raw, dict) else {}
    return {
        "version": int(raw.get("version") or 1) if isinstance(raw, dict) else 1,
        "updated_at": raw.get("updated_at") if isinstance(raw, dict) else None,
        "routes": _normalize_routes(routes if isinstance(routes, dict) else {}),
        "enabled": runtime_model_routing_enabled(),
    }


def set_runtime_model_routing(
    routes: Mapping[str, object],
    note: Optional[str] = None,
) -> dict[str, object]:
    normalized = _normalize_routes(dict(routes))
    existing = get_runtime_model_routing()
    existing_routes = existing.get("routes") if isinstance(existing, dict) else {}
    merged_routes = dict(existing_routes) if isinstance(existing_routes, dict) else {}
    merged_routes.update(normalized)
    payload: dict[str, object] = {
        "version": 1,
        "updated_at": utc_now_iso(),
        "routes": merged_routes,
        "enabled": runtime_model_routing_enabled(),
    }
    if note:
        payload["note"] = note[:500]
    if runtime_model_routing_enabled() and hasattr(firestore_client, "set_runtime_config"):
        firestore_client.set_runtime_config(CONFIG_COLLECTION_ID, payload)
    clear_model_routing_cache()
    return payload


def clear_model_routing_cache() -> None:
    _CACHE["loaded_at"] = 0.0
    _CACHE["config"] = {}


def runtime_model_routing_enabled() -> bool:
    raw = os.environ.get("MODEL_ROUTING_RUNTIME_ENABLED")
    if raw is not None:
        return raw.strip().lower() in {"1", "true", "yes", "on"}
    # Zeabur injects service metadata env vars; enable Firestore runtime reads in
    # deployed services, while local/unit-test runs avoid accidental network calls.
    return bool(os.environ.get("ZEABUR_SERVICE_ID"))


def validate_model_overrides(model_overrides: Optional[Mapping[str, object]]) -> dict[str, dict[str, object]]:
    if not model_overrides:
        return {}
    return _normalize_routes(dict(model_overrides))


def _spec(route_key: str) -> ModelRouteSpec:
    if route_key not in ROUTE_SPECS:
        raise ValueError(f"unknown model route: {route_key}")
    return ROUTE_SPECS[route_key]


def _setting(name: Optional[str]) -> Optional[str]:
    if not name:
        return None
    value = getattr(settings, name, None)
    return str(value).strip() if value is not None and str(value).strip() else None


def _default_model_for_provider(spec: ModelRouteSpec, provider: str) -> str:
    attr = spec.openai_model_setting if provider == "openai" else spec.gemini_model_setting
    model = _setting(attr)
    if model:
        return model
    fallback_attr = spec.gemini_model_setting or spec.openai_model_setting
    return _setting(fallback_attr) or ""


def _normalize_provider(provider: object, spec: ModelRouteSpec) -> str:
    value = str(provider or spec.default_provider).strip().lower()
    if value not in spec.allowed_providers:
        raise ValueError(
            f"route {spec.key} does not allow provider {value}; allowed={list(spec.allowed_providers)}"
        )
    return value


def _normalize_routes(raw_routes: Mapping[str, object]) -> dict[str, dict[str, object]]:
    normalized: dict[str, dict[str, object]] = {}
    for route_key, raw in raw_routes.items():
        spec = _spec(str(route_key))
        if raw is None:
            continue
        if isinstance(raw, ModelRoute):
            raw_dict = raw.model_dump()
        elif isinstance(raw, Mapping):
            raw_dict = dict(raw)
        else:
            raise ValueError(f"model route {route_key} must be an object")
        provider = raw_dict.get("provider")
        model = raw_dict.get("model")
        reasoning_effort = raw_dict.get("reasoning_effort")
        if provider is None and model is None and reasoning_effort is None:
            continue
        route: dict[str, object] = {}
        if provider is not None:
            route["provider"] = _normalize_provider(provider, spec)
        if model is not None:
            model_value = str(model).strip()
            if not model_value:
                raise ValueError(f"model route {route_key} has empty model")
            route["model"] = model_value
        if reasoning_effort is not None:
            effort_value = str(reasoning_effort).strip()
            if effort_value:
                route["reasoning_effort"] = effort_value
        normalized[str(route_key)] = route
    return normalized


def _merge_route(base: ModelRoute, overlay: Mapping[str, object], source: str) -> ModelRoute:
    spec = _spec(base.key)
    provider = _normalize_provider(overlay.get("provider", base.provider), spec)
    model = str(overlay.get("model") or "").strip()
    if not model:
        model = base.model if provider == base.provider else _default_model_for_provider(spec, provider)
    reasoning_effort = overlay.get("reasoning_effort", base.reasoning_effort)
    reasoning = str(reasoning_effort).strip() if reasoning_effort else None
    return ModelRoute(
        key=base.key,
        provider=provider,
        model=model,
        reasoning_effort=reasoning,
        source=source,
    )


def _override_route(
    route_key: str,
    model_overrides: Optional[Mapping[str, object]],
) -> Optional[dict[str, object]]:
    if not model_overrides:
        return None
    normalized = _normalize_routes(dict(model_overrides))
    return normalized.get(route_key)


def _runtime_route(route_key: str) -> Optional[dict[str, object]]:
    runtime = get_runtime_model_routing()
    routes = runtime.get("routes") if isinstance(runtime, dict) else {}
    if not isinstance(routes, dict):
        return None
    route = routes.get(route_key)
    return dict(route) if isinstance(route, dict) else None


def _load_runtime_config(use_cache: bool) -> dict[str, object]:
    import time

    if not runtime_model_routing_enabled():
        return {}
    if use_cache:
        loaded_at = float(_CACHE.get("loaded_at") or 0.0)
        if loaded_at and time.monotonic() - loaded_at < CACHE_TTL_SECONDS:
            cached = _CACHE.get("config")
            return dict(cached) if isinstance(cached, dict) else {}
    if not hasattr(firestore_client, "get_runtime_config"):
        return {}
    raw = firestore_client.get_runtime_config(CONFIG_COLLECTION_ID) or {}
    if isinstance(raw, dict):
        _CACHE["loaded_at"] = time.monotonic()
        _CACHE["config"] = dict(raw)
        return dict(raw)
    return {}
