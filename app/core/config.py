from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional
import os
from dotenv import load_dotenv

load_dotenv(".env")
load_dotenv(".env.local", override=True)


class Settings(BaseSettings):
    PROJECT_NAME: str = "Global Intelligence Briefing"
    GCP_PROJECT_ID: str = ""
    FIRESTORE_DATABASE: str = "(default)"
    DRIVE_OUTPUT_FOLDER_ID: str = ""
    BRIEFING_TIMEZONE: str = "Australia/Brisbane"
    ENVIRONMENT: str = "dev"
    GEMINI_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None

    JUDGEMENT_PROVIDER: str = "gemini"
    JUDGEMENT_MODEL_OPENAI: str = "gpt-5-mini"
    JUDGEMENT_MODEL_GEMINI: str = "gemini-2.5-flash"
    JUDGEMENT_ESCALATION_MODEL_GEMINI: str = "gemini-2.5-pro"
    JUDGEMENT_REASONING_EFFORT: str = "medium"

    IMPACT_PROVIDER: str = "gemini"
    IMPACT_MODEL_OPENAI: str = "gpt-5-mini"
    IMPACT_MODEL_GEMINI: str = "gemini-2.5-flash"
    IMPACT_ESCALATION_MODEL_GEMINI: str = "gemini-2.5-pro"
    # 2026-05-13: high→medium. 6 個 output 中 4 個是 list 抽取（純 lookup，不需 reasoning），
    # 2 個短句 ≤200 字。high effort 對純抽取過頭，預期省 30-40% output tokens。
    IMPACT_REASONING_EFFORT: str = "medium"

    BRIEFING_PROVIDER: str = "gemini"
    BRIEFING_MODEL_OPENAI: str = "gpt-5"
    BRIEFING_MODEL_GEMINI: str = "gemini-2.5-pro"
    BRIEFING_REASONING_EFFORT: str = "medium"

    PODCAST_SCRIPT_PROVIDER: str = "gemini"
    PODCAST_SCRIPT_MODEL_OPENAI: str = "gpt-5"
    PODCAST_SCRIPT_MODEL_GEMINI: str = "gemini-2.5-pro"
    PODCAST_SCRIPT_REASONING_EFFORT: str = "medium"

    CANONICALIZATION_MODEL_GEMINI: str = "gemini-2.5-flash"
    MATCH_ADJUDICATION_MODEL_GEMINI: str = "gemini-2.5-pro"
    DAILY_CONSOLIDATION_MODEL_GEMINI: str = "gemini-2.5-pro"

    GCS_AUDIO_BUCKET: str = ""
    PODCAST_TTS_VOICE: str = "cmn-TW-Chirp3-HD-Charon"
    PODCAST_TTS_LANGUAGE_CODE: str = "cmn-TW"
    PODCAST_TTS_LOCATION: str = "global"
    PODCAST_TTS_TIMEOUT_SECONDS: int = 1800

    ADMIN_TOKEN: Optional[str] = None
    GOOGLE_WORKSPACE_AUTH_MODE: str = "default"
    GOOGLE_OAUTH_CLIENT_SECRET_FILE: str = "client_secret.json"
    GOOGLE_OAUTH_TOKEN_FILE: str = ".secrets/google_oauth_token.json"
    GOOGLE_SHEET_ID: str = ""
    GOOGLE_SHEET_RANGE: str = "'RSS List'!A:J"
    VERTEX_LOCATION: str = "us-central1"
    EMBEDDING_MODEL: str = "gemini-embedding-001"
    EMBEDDING_FALLBACK_MODEL: str = "text-embedding-004"
    CLUSTERING_DISTANCE_THRESHOLD: float = 0.15
    SIGNAL_MATCH_AUTO_THRESHOLD: float = 0.86
    SIGNAL_MATCH_REVIEW_THRESHOLD: float = 0.76
    SIGNAL_MATCH_GENERIC_AUTO_THRESHOLD: float = 0.90
    CENTROID_DECAY: float = 0.85
    STORY_THREAD_LOOKBACK_DAYS: int = 30

    # W7 phase tree
    PHASE_ASSIGNMENT_MODEL_GEMINI: str = "gemini-2.5-flash"
    PHASE_COSINE_AUTO_THRESHOLD: float = 0.82
    PHASE_DORMANT_AFTER_DAYS: int = 7

    # W5 Judge guard-rail caps. Reviewed quarterly; keep all even at 0% trigger
    # so they're available as observation/patch tools when LLM regresses.
    JUDGE_CAP_MARKET_WRAP: int = 45     # 盤後 / closing bell — generic market wrap
    JUDGE_CAP_SINGLE_CORP: int = 65     # single-source non-systemic corporate earnings
    JUDGE_CAP_PUBLIC_HEALTH: int = 65   # public-health stories without market angle
    JUDGE_CAP_ANALYSIS: int = 60        # single-source analysis / explainer / "why" pieces
    model_config = SettingsConfigDict(env_file=(".env", ".env.local"), env_file_encoding="utf-8", extra="ignore")

settings = Settings()
