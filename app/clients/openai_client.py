import json
import logging
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


class OpenAIClient:
    def __init__(self):
        self.client = None
        self._init_error: Optional[str] = None
        if not settings.OPENAI_API_KEY:
            self._init_error = "OPENAI_API_KEY missing"
            logger.warning("OpenAI client not initialized: %s", self._init_error)
            return
        try:
            from openai import OpenAI
            self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
            logger.info("Initialized OpenAI Client.")
        except Exception as exc:
            self._init_error = str(exc)
            logger.error("Failed to initialize OpenAI Client: %s", exc)

    @property
    def is_ready(self) -> bool:
        return self.client is not None

    def generate_json(
        self,
        prompt: str,
        model: str,
        temperature: float = 0.2,
        reasoning_effort: Optional[str] = None,
    ) -> tuple[dict, int, int]:
        if not self.is_ready:
            raise RuntimeError(f"OpenAI client not initialized: {self._init_error}")

        kwargs: dict = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
            "temperature": temperature,
        }
        if reasoning_effort and reasoning_effort.lower() in {"minimal", "low", "medium", "high"}:
            kwargs["reasoning_effort"] = reasoning_effort.lower()

        response = self.client.chat.completions.create(**kwargs)
        choice = response.choices[0]
        text = choice.message.content or ""
        if not text:
            raise ValueError("OpenAI returned empty json response")
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = json.loads(text, strict=False)
        usage = response.usage
        input_tokens = int(getattr(usage, "prompt_tokens", 0) or 0) if usage else 0
        output_tokens = int(getattr(usage, "completion_tokens", 0) or 0) if usage else 0
        return parsed, input_tokens, output_tokens

    def generate_text(
        self,
        prompt: str,
        model: str,
        temperature: float = 0.4,
        reasoning_effort: Optional[str] = None,
    ) -> tuple[str, int, int]:
        if not self.is_ready:
            raise RuntimeError(f"OpenAI client not initialized: {self._init_error}")

        kwargs: dict = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
        }
        if reasoning_effort and reasoning_effort.lower() in {"minimal", "low", "medium", "high"}:
            kwargs["reasoning_effort"] = reasoning_effort.lower()

        response = self.client.chat.completions.create(**kwargs)
        text = response.choices[0].message.content or ""
        usage = response.usage
        input_tokens = int(getattr(usage, "prompt_tokens", 0) or 0) if usage else 0
        output_tokens = int(getattr(usage, "completion_tokens", 0) or 0) if usage else 0
        return text, input_tokens, output_tokens


openai_client = OpenAIClient()
