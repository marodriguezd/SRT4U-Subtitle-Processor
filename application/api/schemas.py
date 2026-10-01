"""Pydantic contracts for the local SRT4U REST API.

These mirror the domain dataclasses field-for-field without importing them
into the contract: the domain never depends on FastAPI/Pydantic, and the API
never duplicates business rules.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from ..version import APP_VERSION


class ParseIssueModel(BaseModel):
    """One block the parser could not use (advisory; never a failure)."""

    kind: str = Field(examples=["invalid_timestamp", "reversed_timing", "empty_cue"])
    reason: str
    line: Optional[int] = None
    snippet: str = ""


class HealthResponse(BaseModel):
    status: str = Field(examples=["ok"])
    version: str = Field(examples=[APP_VERSION])


class ErrorResponse(BaseModel):
    detail: str


class QAFindingModel(BaseModel):
    severity: str
    rule: str
    subtitle_index: Optional[int] = None
    message: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class QAReportModel(BaseModel):
    passed: bool
    strict_passed: bool
    error_count: int
    warning_count: int
    info_count: int
    findings: List[QAFindingModel] = Field(default_factory=list)


class ContentMetricsModel(BaseModel):
    subtitle_count: int = 0
    total_words: int = 0
    total_characters: int = 0
    average_characters_per_subtitle: float = 0.0
    max_characters_per_subtitle: int = 0
    average_words_per_subtitle: float = 0.0
    line_count: int = 0
    average_lines_per_subtitle: float = 0.0
    empty_subtitles: int = 0
    duplicate_subtitles: int = 0


class TimingMetricsModel(BaseModel):
    total_duration_ms: int = 0
    average_cps: float = 0.0
    max_cps: float = 0.0
    min_cps: float = 0.0
    overlapping_subtitles: int = 0
    too_short_subtitles: int = 0
    too_long_subtitles: int = 0
    cps_violations: int = 0


class QualityMetricsModel(BaseModel):
    line_length_violations: int = 0
    errors: int = 0
    warnings: int = 0
    infos: int = 0
    rule_counts: Dict[str, int] = Field(default_factory=dict)


class ProcessingMetricsModel(BaseModel):
    processing_time_seconds: float = 0.0
    lines_removed: int = 0
    translation_failures: int = 0
    parse_issues: int = 0


class SubtitleAnalyticsModel(BaseModel):
    content: ContentMetricsModel = Field(default_factory=ContentMetricsModel)
    timing: TimingMetricsModel = Field(default_factory=TimingMetricsModel)
    quality: QualityMetricsModel = Field(default_factory=QualityMetricsModel)
    processing: ProcessingMetricsModel = Field(default_factory=ProcessingMetricsModel)


class AnalyzeResponse(BaseModel):
    analytics: SubtitleAnalyticsModel
    qa: QAReportModel


class TranslationMetricsModel(BaseModel):
    provider: str
    model: Optional[str] = None
    source_language: str
    target_language: str
    number_of_cues: int = 0
    characters_input: int = 0
    characters_output: int = 0
    words_input: int = 0
    words_output: int = 0
    duration_ms: Optional[int] = None
    success: bool = False
    error_type: Optional[str] = None
    retry_count: int = 0
    fallback_used: bool = False
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    estimated_cost: Optional[float] = None
    requested_provider: Optional[str] = None
    providers_used: Optional[List[str]] = None
    error_message: Optional[str] = None
    fallback_error_type: Optional[str] = None


class TranslationResultModel(BaseModel):
    text: str
    metrics: TranslationMetricsModel


class ProcessResultModel(BaseModel):
    output_content: str
    output_format: str
    stats: ProcessingMetricsModel
    processed_items_count: int = 0
    translation_metrics: Optional[TranslationMetricsModel] = None
    qa: Optional[QAReportModel] = None
    # P1: parser findings ride along as a top-level advisory list so API
    # clients can warn their users. Declared explicitly because the /process
    # route serializes this exact model into the job result (documented via
    # JobStatusResponse.result in create_app's OpenAPI extension).
    parse_issues: List[ParseIssueModel] = Field(default_factory=list)


class JobCreatedResponse(BaseModel):
    job_id: str
    status: str = Field(examples=["queued"])


class JobStatusResponse(BaseModel):
    job_id: str
    operation: str
    status: str = Field(
        examples=["queued", "running", "completed", "failed", "cancelled"]
    )
    created_at: str
    finished_at: Optional[str] = None
    error: Optional[str] = None
    # The concrete payload depends on `operation`; create_app's OpenAPI
    # extension documents `result` as the union of the job-result models.
    # Runtime stays tolerant (jobs carry plain dicts built by the routes).
    result: Optional[Any] = None


class HistoryItemModel(BaseModel):
    id: int
    timestamp: Optional[str] = None
    operation: Optional[str] = None
    file_path: Optional[str] = None
    file_format: Optional[str] = None
    source_language: Optional[str] = None
    target_language: Optional[str] = None
    provider: Optional[str] = None
    requested_provider: Optional[str] = None
    model: Optional[str] = None
    number_of_cues: Optional[int] = None
    duration_ms: Optional[int] = None
    success: Optional[bool] = None
    error_type: Optional[str] = None
    retry_count: Optional[int] = None
    fallback_used: Optional[bool] = None
    providers_used: Optional[List[str]] = None
    qa_errors: Optional[int] = None
    qa_warnings: Optional[int] = None
    translation_failures: Optional[int] = None
    benchmark_id: Optional[str] = None
    run_index: Optional[int] = None
    parse_issues: Optional[int] = None


class HistoryListResponse(BaseModel):
    items: List[HistoryItemModel] = Field(default_factory=list)


class BenchmarkSummaryModel(BaseModel):
    benchmark_id: str
    runs: int = 0
    providers: List[str] = Field(default_factory=list)
    first_seen: Optional[str] = None


class BenchmarkListResponse(BaseModel):
    items: List[BenchmarkSummaryModel] = Field(default_factory=list)


class BenchmarkRunModel(BaseModel):
    provider: Optional[str] = None
    requested_provider: Optional[str] = None
    model: Optional[str] = None
    run_index: Optional[int] = None
    timestamp: Optional[str] = None
    number_of_cues: Optional[int] = None
    duration_ms: Optional[int] = None
    success: Optional[bool] = None
    error_type: Optional[str] = None
    retry_count: Optional[int] = None
    fallback_used: Optional[bool] = None
    providers_used: Optional[List[str]] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    estimated_cost: Optional[float] = None


class BenchmarkDetailResponse(BaseModel):
    benchmark_id: str
    runs: List[BenchmarkRunModel] = Field(default_factory=list)


class TranscriptionMetricsModel(BaseModel):
    provider: str
    model: Optional[str] = None
    source_language: str = "auto"
    segment_count: int = 0
    characters_output: int = 0
    words_output: int = 0
    media_duration_ms: Optional[int] = None
    processing_duration_ms: Optional[int] = None
    real_time_factor: Optional[float] = None
    success: bool = False
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    device: Optional[str] = None


class TranscriptionResultModel(BaseModel):
    output_content: str
    output_format: str
    language: str = "auto"
    processed_items_count: int = 0
    metrics: Optional[TranscriptionMetricsModel] = None
