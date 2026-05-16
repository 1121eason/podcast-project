from typing import Optional

from pydantic import BaseModel, Field


class RssSource(BaseModel):
    source_id: str
    market_level: str = ""
    publisher: str = ""
    desk: str = ""
    category: str = ""
    zh_name: str = ""
    description: str = ""
    feed_url: str
    raw_status: str = ""
    health_status: str = "unknown"
    is_fetchable: bool = True
    last_checked_at: str = ""
    synced_at: str = ""
    last_seen_in_sheet_at: str = ""
    last_ingested_at: str = ""
    last_ingest_status: str = ""
    last_ingest_item_count: int = 0
    last_ingest_new_item_count: int = 0
    last_ingest_updated_item_count: int = 0
    last_ingest_duration_ms: int = 0
    last_ingest_fetch_duration_ms: int = 0
    last_ingest_write_duration_ms: int = 0
    last_ingest_skipped_old_item_count: int = 0
    last_ingest_error: str = ""
    consecutive_ingest_failures: int = 0


class RssItem(BaseModel):
    item_id: str
    source_id: str
    publisher: str = ""
    desk: str = ""
    category: str = ""
    market_level: str = ""
    title: str
    url: str = ""
    guid: str = ""
    summary: str = ""
    published_at: Optional[str] = None
    first_seen_at: str
    last_seen_at: str
    content_hash: str
    feed_url: str = ""
    embedding: Optional[list[float]] = None
    embedding_model: Optional[str] = None
    embedded_at: Optional[str] = None
    signal_id: Optional[str] = None

    article_extract_status: str = ""
    article_lead: str = ""
    article_text_hash: Optional[str] = None
    article_extracted_at: Optional[str] = None

    # canonical_event: deprecated by Plan A — kept for migration backward-compat (read-only)
    canonical_event: dict = Field(default_factory=dict)
    canonical_event_text: str = ""
    canonical_event_hash: Optional[str] = None
    canonicalized_at: Optional[str] = None
    canonical_model: Optional[str] = None

    # item_signals: mechanical replacement for canonical_event (Plan A, no LLM)
    item_signals: dict = Field(default_factory=dict)
    item_signals_hash: Optional[str] = None
    item_signals_at: Optional[str] = None

    event_embedding: Optional[list[float]] = None
    entity_embedding: Optional[list[float]] = None
    impact_embedding: Optional[list[float]] = None
    context_embedding: Optional[list[float]] = None
    event_embedding_hash: Optional[str] = None
    embedding_version: str = ""
    v2_processed_at: Optional[str] = None
    v2_processing_hash: Optional[str] = None


class RssIngestRun(BaseModel):
    run_id: str
    started_at: str
    completed_at: str
    source_count: int
    fetched_source_count: int
    failed_source_count: int
    new_item_count: int
    updated_item_count: int
    error_count: int
    errors: list[dict[str, str]]
    duration_ms: int = 0
    timeout_seconds: int = 10
    max_workers: int = 10
    window_start: Optional[str] = None
    skipped_old_item_count: int = 0
    skipped_existing_item_count: int = 0
    source_results: list[dict[str, object]] = Field(default_factory=list)
