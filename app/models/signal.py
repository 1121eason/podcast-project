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

    impacted_sectors: Optional[list[str]] = None
    impacted_assets: Optional[list[str]] = None
    impacted_regions: Optional[list[str]] = None
    watch_points: Optional[list[str]] = None
    counterfactual: Optional[str] = None
    gap_note: Optional[str] = None
    impact_judged_at: Optional[str] = None
    impact_judge_model: Optional[str] = None
    impact_input_tokens: Optional[int] = None
    impact_output_tokens: Optional[int] = None


class RssJudgementRun(BaseModel):
    run_id: str
    generated_at: str
    since_hours: int

    candidate_signal_count: int = 0
    judged_signal_count: int = 0
    skipped_already_judged_count: int = 0
    skipped_unverified_count: int = 0
    failed_signal_count: int = 0

    avg_score: float = 0.0
    score_80plus_count: int = 0
    score_60_79_count: int = 0
    score_40_59_count: int = 0
    score_below_40_count: int = 0

    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0

    duration_ms: int = 0
    judge_model: str = ""
    errors: list[dict[str, str]] = Field(default_factory=list)


class BriefingSection(BaseModel):
    section_id: str
    title: str
    summary: str
    importance_score: int = 0
    impact_type: Optional[str] = None
    impacted_sectors: list[str] = Field(default_factory=list)
    watch_points: list[str] = Field(default_factory=list)
    referenced_signal_ids: list[str] = Field(default_factory=list)
    referenced_urls: list[str] = Field(default_factory=list)


class BriefingCategory(BaseModel):
    category_id: str
    title: str
    category_overview: str = ""
    sections: list[BriefingSection] = Field(default_factory=list)


class RssBriefing(BaseModel):
    briefing_id: str
    briefing_date: str
    generated_at: str
    score_threshold: int

    selected_signal_count: int = 0
    total_input_signals: int = 0

    overview: str = ""
    categories: list[BriefingCategory] = Field(default_factory=list)
    sections: list[BriefingSection] = Field(default_factory=list)
    signal_pool_health: dict = Field(default_factory=dict)

    google_doc_id: Optional[str] = None
    google_doc_url: Optional[str] = None

    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    duration_ms: int = 0


class RssBusinessImpactRun(BaseModel):
    run_id: str
    generated_at: str
    since_hours: int

    candidate_signal_count: int = 0
    analyzed_signal_count: int = 0
    skipped_already_analyzed_count: int = 0
    skipped_low_score_count: int = 0
    failed_signal_count: int = 0

    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0
    duration_ms: int = 0
    impact_model: str = ""
    errors: list[dict[str, str]] = Field(default_factory=list)


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
