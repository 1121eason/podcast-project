"""Single source of truth for LLM pricing across all services.

Previously each service had its own PROVIDER_PRICING dict that hardcoded prices
keyed by provider (gemini/openai). When models switched (e.g. Pro → Flash),
the prices were left at Pro level — costing reports were inflated ~16x.

This module fixes that by keying pricing on model name. Add a model here and
every service uses the right price automatically.

Prices are USD per **1 million tokens** (input / output) — copied verbatim
from Google / OpenAI public pricing pages, no inline math. ``compute_llm_cost``
divides token counts by 1_000_000 before multiplying.

Historical bug (fixed 2026-05-15): the previous version used `1.25 / 1000` and
multiplied by raw token count, which silently inflated reported cost by 1000x
(20k input + 8k output of Pro reported $105 instead of ~$0.105).
"""
from typing import Optional


# Updated 2026-05-13. Keep in sync with provider pricing pages.
# All values are USD per 1M tokens — DO NOT pre-divide here; compute_llm_cost
# normalises by dividing token counts by 1_000_000.
PRICE_DIVISOR = 1_000_000

MODEL_PRICING: dict[str, dict[str, float]] = {
    # Gemini (USD per 1M tokens)
    "gemini-2.5-flash":         {"input": 0.075, "output": 0.30},
    "gemini-2.5-pro":           {"input": 1.25,  "output": 10.0},
    "gemini-embedding-001":     {"input": 0.025, "output": 0.0},
    "text-embedding-004":       {"input": 0.025, "output": 0.0},
    # OpenAI (USD per 1M tokens)
    "gpt-5-mini":               {"input": 0.25,  "output": 2.0},
    "gpt-5":                    {"input": 1.25,  "output": 10.0},
    "gpt-4o":                   {"input": 2.50,  "output": 10.0},
    "gpt-4o-mini":              {"input": 0.15,  "output": 0.60},
}

# Fallback pricing if model name unknown (assume Pro-level so we over-report
# rather than silently undercount).
_FALLBACK_PRICING = {"input": 1.25, "output": 10.0}


def pricing_for_model(model: Optional[str]) -> dict[str, float]:
    if not model:
        return _FALLBACK_PRICING
    return MODEL_PRICING.get(model, _FALLBACK_PRICING)


def compute_llm_cost(model: Optional[str], input_tokens: int, output_tokens: int) -> float:
    p = pricing_for_model(model)
    cost = (
        (input_tokens / PRICE_DIVISOR) * p["input"]
        + (output_tokens / PRICE_DIVISOR) * p["output"]
    )
    return round(cost, 6)
