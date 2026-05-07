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
    JUDGEMENT_PROVIDER: str = "openai"
    JUDGEMENT_MODEL_OPENAI: str = "gpt-5-mini"
    JUDGEMENT_MODEL_GEMINI: str = "gemini-2.5-pro"
    ADMIN_TOKEN: Optional[str] = None
    GOOGLE_WORKSPACE_AUTH_MODE: str = "default"
    GOOGLE_OAUTH_CLIENT_SECRET_FILE: str = "client_secret.json"
    GOOGLE_OAUTH_TOKEN_FILE: str = ".secrets/google_oauth_token.json"
    GOOGLE_SHEET_ID: str = ""
    GOOGLE_SHEET_RANGE: str = "'RSS List'!A:J"
    VERTEX_LOCATION: str = "us-central1"
    EMBEDDING_MODEL: str = "text-embedding-004"
    CLUSTERING_DISTANCE_THRESHOLD: float = 0.15
    model_config = SettingsConfigDict(env_file=(".env", ".env.local"), env_file_encoding="utf-8", extra="ignore")

settings = Settings()
