import json

from google import genai
from google.genai import types

from app.core.config import settings
from app.core.logging import logger

JUDGEMENT_MODEL = "gemini-2.5-pro"
EDITORIAL_MODEL = "gemini-2.5-pro"


class GeminiClient:
    def __init__(self):
        try:
            if settings.GEMINI_API_KEY:
                self.client = genai.Client(api_key=settings.GEMINI_API_KEY)
                logger.info("Initialized Gemini Client via AI Studio API Key.")
            elif settings.GCP_PROJECT_ID:
                self.client = genai.Client(vertexai=True, project=settings.GCP_PROJECT_ID, location="us-central1")
                logger.info("Initialized Gemini Client via GCP Vertex AI.")
            else:
                import warnings
                warnings.warn("No API key or GCP Project ID provided.")
                self.client = None
        except Exception as e:
            logger.error(f"Failed to initialize Gemini Client: {e}")
            self.client = None

    def generate_json(self, prompt: str, model: str = JUDGEMENT_MODEL) -> tuple[dict, int, int]:
        if not self.client:
            raise Exception("Gemini API Client not initialized")
        try:
            response = self.client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.2,
                    response_mime_type="application/json",
                ),
            )
            text = response.text or ""
            if not text:
                raise ValueError("Gemini returned empty json response")
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = json.loads(text, strict=False)
            usage = getattr(response, "usage_metadata", None)
            input_tokens = int(getattr(usage, "prompt_token_count", 0) or 0) if usage else 0
            output_tokens = int(getattr(usage, "candidates_token_count", 0) or 0) if usage else 0
            return parsed, input_tokens, output_tokens
        except Exception as e:
            logger.error(f"Error in generate_json: {e}")
            raise


gemini_client = GeminiClient()
