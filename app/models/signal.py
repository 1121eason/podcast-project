from typing import Optional

from pydantic import BaseModel, Field


class RssSignal(BaseModel):
    signal_id: str
    generated_at: str
    window_start: str
    window_end: str

    member_item_ids: list[str] = Field(default_factory=list)
    cluster_size: int = 0
    source_count: int = 0
    publisher_count: int = 0

    publishers: list[str] = Field(default_factory=list)
    desks: list[str] = Field(default_factory=list)
    market_levels: list[str] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)

    representative_item_id: str = ""
    representative_title: str = ""
    representative_url: str = ""
    representative_summary: str = ""
    representative_published_at: Optional[str] = None
    representative_publisher: str = ""

    cluster_status: Optional[str] = None
    topic_heat: Optional[str] = None

    importance_score: Optional[int] = None
    impact_type: Optional[str] = None
    key_entities: Optional[list[str]] = None
    regions: Optional[list[str]] = None
    reasoning: Optional[str] = None
    heat_vs_importance_note: Optional[str] = None

    judged_at: Optional[str] = None
    judge_model: Optional[str] = None
    judge_input_tokens: Optional[int] = None
    judge_output_tokens: Optional[int] = None


class RssClusteringRun(BaseModel):
    run_id: str
    generated_at: str
    window_hours: int

    candidate_item_count: int = 0
    embedded_item_count: int = 0
    embedding_failed_item_count: int = 0
    embedding_skipped_cached_count: int = 0

    cluster_count: int = 0
    multi_source_cluster_count: int = 0
    singleton_cluster_count: int = 0

    duration_ms: int = 0
    embedding_cost_usd: float = 0.0

    error: Optional[str] = None
