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

    # Best publisher tier among signal.publishers: "tier1" | "other" | "aggregator" | ""
    # Used for W5 quality_gate (tier1 single-source still worth Judge) and debugging.
    publisher_tier: str = ""

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

    what_happened: Optional[str] = None
    why_matters: Optional[str] = None
    who_affected: Optional[str] = None
    what_next: Optional[str] = None
    primary_theme: Optional[str] = None

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

    thread_id: Optional[str] = None
    phase_id: Optional[str] = None
    is_background_repeat: bool = False
    signal_status: str = "provisional"
    event_centroid: Optional[list[float]] = None
    entity_centroid: Optional[list[float]] = None
    impact_centroid: Optional[list[float]] = None
    context_centroid: Optional[list[float]] = None
    confidence_score: float = 0.0
    match_score: float = 0.0
    novelty_score: float = 0.0
    today_delta: str = ""
    candidate_match_ids: list[str] = Field(default_factory=list)
    last_member_at: Optional[str] = None
    last_consolidated_at: Optional[str] = None
    signal_fingerprint_hash: Optional[str] = None

    # W4 adjudication metadata (persisted so W7 can consume W4's same_thread evidence).
    adjudication_decision: Optional[str] = None  # same_event | same_thread | different_event
    adjudication_confidence: Optional[float] = None
    adjudication_rationale: Optional[str] = None
    adjudication_candidate_thread_id: Optional[str] = None


class RssJudgementRun(BaseModel):
    run_id: str
    generated_at: str
    since_hours: int

    candidate_signal_count: int = 0
    judged_signal_count: int = 0
    skipped_already_judged_count: int = 0
    skipped_unverified_count: int = 0
    skipped_quality_gate_count: int = 0
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
    # P1 monitoring: which guard-rail caps were applied this run and how often.
    # Keys: market_wrap / single_corp / public_health / analysis
    guard_rails_triggered: dict[str, int] = Field(default_factory=dict)
    errors: list[dict[str, str]] = Field(default_factory=list)


class BriefingSection(BaseModel):
    section_id: str
    title: str
    summary: str
    importance_score: int = 0
    impact_type: Optional[str] = None
    is_continuation: bool = False
    continuation_note: str = ""
    impacted_sectors: list[str] = Field(default_factory=list)
    watch_points: list[str] = Field(default_factory=list)
    referenced_signal_ids: list[str] = Field(default_factory=list)
    referenced_urls: list[str] = Field(default_factory=list)


class BriefingCategory(BaseModel):
    category_id: str
    title: str
    category_overview: str = ""
    sections: list[BriefingSection] = Field(default_factory=list)


class BriefingTopChange(BaseModel):
    rank: int
    title: str
    summary: str
    category_id: str = ""
    importance_score: int = 0
    is_continuation: bool = False
    referenced_signal_ids: list[str] = Field(default_factory=list)
    referenced_urls: list[str] = Field(default_factory=list)


class RssBriefing(BaseModel):
    briefing_id: str
    briefing_date: str
    generated_at: str
    score_threshold: int

    selected_signal_count: int = 0
    total_input_signals: int = 0

    overview: str = ""
    top_changes: list[BriefingTopChange] = Field(default_factory=list)
    categories: list[BriefingCategory] = Field(default_factory=list)
    sections: list[BriefingSection] = Field(default_factory=list)
    aggregated_watch_points: list[str] = Field(default_factory=list)
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

    # W6 output-quality monitoring (added 2026-05-13).
    # Helps spot LLM "filling fields lazily" — e.g. mostly-empty watch_points or
    # placeholder counterfactual. Reviewed against W6 health-check checklist.
    avg_sectors_per_signal: float = 0.0       # 0-5; healthy ≥ 3
    avg_assets_per_signal: float = 0.0        # 0-5; healthy ≥ 2
    avg_regions_per_signal: float = 0.0       # 0-5; healthy ≥ 2
    avg_watch_points_per_signal: float = 0.0  # 0-5; healthy ≥ 3 (LLM tends to slack here)
    empty_counterfactual_count: int = 0       # how many signals had blank counterfactual
    empty_gap_note_count: int = 0             # how many signals had blank gap_note
    avg_counterfactual_chars: float = 0.0     # healthy 30-200
    avg_gap_note_chars: float = 0.0           # healthy 30-200


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


class RssStoryThread(BaseModel):
    thread_id: str
    title: str = ""
    status: str = "active"
    active_since: str = ""
    last_seen_at: str = ""
    signal_ids: list[str] = Field(default_factory=list)
    key_entities: list[str] = Field(default_factory=list)
    event_centroid: Optional[list[float]] = None
    context_centroid: Optional[list[float]] = None
    known_background: str = ""
    covered_points: list[str] = Field(default_factory=list)
    latest_developments: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    today_delta: str = ""
    novelty_score: float = 0.0
    do_not_repeat_points: list[str] = Field(default_factory=list)
    continuation_prompt_hint: str = ""
    last_covered_in_podcast_at: Optional[str] = None
    thread_memory_hash: Optional[str] = None
    phases_initialized_at: Optional[str] = None


class RssThreadPhase(BaseModel):
    phase_id: str
    thread_id: str
    title: str = ""
    status: str = "emerging"  # emerging | active | dormant | resolved
    parent_phase_id: Optional[str] = None
    child_phase_ids: list[str] = Field(default_factory=list)
    signal_ids: list[str] = Field(default_factory=list)
    signal_count: int = 0
    key_entities: list[str] = Field(default_factory=list)
    summary: str = ""
    novelty_reason: str = ""
    llm_decision_log: list[str] = Field(default_factory=list)
    event_centroid: Optional[list[float]] = None
    context_centroid: Optional[list[float]] = None
    centroid_updated_at: Optional[str] = None
    opened_at: str = ""
    last_advanced_at: str = ""
    today_delta: str = ""
    continuation_prompt_hint: str = ""
    do_not_repeat_points: list[str] = Field(default_factory=list)


class WorkflowRun(BaseModel):
    run_id: str
    workflow_name: str
    run_bucket: str
    status: str = "running"
    started_at: str
    completed_at: Optional[str] = None
    request_hash: str = ""
    summary: dict = Field(default_factory=dict)
    error: Optional[str] = None
