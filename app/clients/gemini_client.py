from google import genai
from google.genai import types
from app.core.config import settings
from app.core.logging import logger
from app.models.research_output import ResearchOutputSchema
import json

RESEARCH_MODEL = "gemini-2.5-pro"
EDITORIAL_MODEL = "gemini-2.5-pro"
JUDGEMENT_MODEL = "gemini-2.5-pro"

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

    def generate_research(self, prompt: str) -> str:
        if not self.client:
            raise Exception("Gemini API Client not initialized")

        logger.info("Generating research output via Gemini model")
        try:
            response = self.client.models.generate_content(
                model=RESEARCH_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.2,
                    response_mime_type="application/json",
                    response_schema=ResearchOutputSchema,
                ),
            )
            if response.parsed:
                return response.parsed.model_dump_json()
            if response.text:
                return response.text
            raise ValueError("Gemini returned an empty research response")
        except Exception as e:
            logger.error(f"Error generating research output: {e}")
            raise

    def generate_briefing(self, research_data: dict, prompt_template: str) -> str:
        if not self.client:
            raise Exception("Gemini API Client not initialized")
        prompt = prompt_template.format(research_data=json.dumps(research_data, ensure_ascii=False))
        try:
            response = self.client.models.generate_content(
                model=EDITORIAL_MODEL,
                contents=prompt,
            )
            if not response.text:
                raise ValueError("Gemini returned an empty briefing response")
            return response.text
        except Exception as e:
            logger.error(f"Error generating briefing: {e}")
            raise

    def generate_podcast_script(self, briefing_text: str, prompt_template: str) -> str:
        if not self.client:
            raise Exception("Gemini API Client not initialized")
        prompt = prompt_template.format(briefing_text=briefing_text)
        try:
            response = self.client.models.generate_content(
                model=EDITORIAL_MODEL,
                contents=prompt,
            )
            if not response.text:
                raise ValueError("Gemini returned an empty podcast script response")
            return response.text
        except Exception as e:
            logger.error(f"Error generating podcast script: {e}")
            raise

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

    def generate_tts(self, text: str) -> bytes:
        logger.info("Generating TTS via Google Cloud Text-to-Speech")
        from google.cloud import texttospeech
        tts_client = texttospeech.TextToSpeechClient()
        synthesis_input = texttospeech.SynthesisInput(text=text)
        voice = texttospeech.VoiceSelectionParams(
            language_code="cmn-TW",
            name="cmn-TW-Wavenet-A"
        )
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3
        )
        
        audio_chunks = []
        chunk_size = 1500 # Safe size to stay under 5000 bytes for CJK characters
        text_chunks = [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]
        
        for chunk in text_chunks:
            synthesis_input = texttospeech.SynthesisInput(text=chunk)
            res = tts_client.synthesize_speech(
                input=synthesis_input, voice=voice, audio_config=audio_config
            )
            audio_chunks.append(res.audio_content)
            
        return b''.join(audio_chunks)

gemini_client = GeminiClient()
