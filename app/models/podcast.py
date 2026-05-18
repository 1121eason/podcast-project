from typing import Optional

from pydantic import BaseModel, Field


class ScriptSegment(BaseModel):
    segment_id: str
    position: int
    segment_type: str  # opening | top_changes | theme | closing
    title: str = ""
    text: str = ""
    duration_estimate_seconds: int = 0
    referenced_signal_ids: list[str] = Field(default_factory=list)
    theme: Optional[str] = None  # geopolitics | global_finance | tech_ai | semi_supply_chain | corporate_moves | other_signal


class RssPodcastScript(BaseModel):
    script_id: str
    briefing_id: str
    briefing_date: str
    generated_at: str
    status: str = "script_generated"

    episode_title: str = ""
    script: str = ""
    word_count: int = 0
    duration_estimate_minutes: float = 0.0
    segments: list[ScriptSegment] = Field(default_factory=list)

    themes_covered: list[str] = Field(default_factory=list)
    themes_skipped: list[str] = Field(default_factory=list)
    skipped_repetition_count: int = 0

    show_notes: str = ""
    validation_warnings: list[str] = Field(default_factory=list)

    google_doc_id: Optional[str] = None
    google_doc_url: Optional[str] = None
    google_doc_error: Optional[str] = None

    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    duration_ms: int = 0


class RssPodcastEpisode(BaseModel):
    episode_id: str
    script_id: str
    briefing_date: str
    generated_at: str
    status: str = "audio_generated"

    audio_url: Optional[str] = None
    audio_gcs_uri: Optional[str] = None
    audio_bucket: Optional[str] = None
    audio_object_path: Optional[str] = None
    audio_size_bytes: int = 0
    audio_duration_seconds: int = 0

    tts_voice: str = ""
    tts_model: str = ""
    tts_language_code: str = ""
    tts_location: str = ""
    tts_chars: int = 0
    tts_cost_usd: float = 0.0
    tts_duration_ms: int = 0


class RssPublishPackage(BaseModel):
    package_id: str
    script_id: str
    episode_id: Optional[str] = None
    briefing_id: str
    briefing_date: str
    generated_at: str
    status: str = "package_generated"

    episode_title: str = ""
    show_notes: str = ""
    audio_url: Optional[str] = None
    audio_gcs_uri: Optional[str] = None
    google_doc_url: Optional[str] = None
    source_urls: list[str] = Field(default_factory=list)


class RssPodcastRun(BaseModel):
    run_id: str
    generated_at: str
    briefing_date: str
    script_id: Optional[str] = None
    episode_id: Optional[str] = None
    package_id: Optional[str] = None

    ok: bool = True
    failed_step: Optional[str] = None
    error: Optional[str] = None

    duration_ms: int = 0
    cost_usd: float = 0.0
