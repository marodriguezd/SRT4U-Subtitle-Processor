"""Framework-independent transcription execution and result models.

Mirrors ``translation_models``: plain dataclasses, JSON-compatible ``to_dict``,
no third-party imports. Segment lists convert directly to ``SubtitleItem``
so transcription feeds Analytics, QA, cleaning, translation, and burn-in
without duplicating structures.
"""

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class TranscriptionSegment:
    """One transcribed cue with millisecond timestamps."""

    index: int
    start_ms: int
    end_ms: int
    text: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TranscriptionMetrics:
    """Observable metrics for one transcription run.

    ``real_time_factor`` is computed only when both the media duration and
    the processing duration are known; otherwise it stays ``None`` (never
    invented).
    """

    provider: str
    model: Optional[str]
    source_language: str
    segment_count: int
    characters_output: int
    words_output: int
    media_duration_ms: Optional[int]
    processing_duration_ms: Optional[int]
    real_time_factor: Optional[float] = None
    success: bool = True
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    device: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def build(
        cls,
        *,
        provider: str,
        model: Optional[str],
        source_language: str,
        segments: List[TranscriptionSegment],
        media_duration_ms: Optional[int],
        processing_duration_ms: Optional[int],
        success: bool = True,
        error_type: Optional[str] = None,
        error_message: Optional[str] = None,
        device: Optional[str] = None,
    ) -> "TranscriptionMetrics":
        characters = sum(len(segment.text) for segment in segments)
        words = sum(len(segment.text.split()) for segment in segments)
        real_time_factor: Optional[float] = None
        if (
            media_duration_ms is not None
            and media_duration_ms > 0
            and processing_duration_ms is not None
            and processing_duration_ms >= 0
        ):
            real_time_factor = round(processing_duration_ms / media_duration_ms, 4)
        return cls(
            provider=provider,
            model=model,
            source_language=source_language,
            segment_count=len(segments),
            characters_output=characters,
            words_output=words,
            media_duration_ms=media_duration_ms,
            processing_duration_ms=processing_duration_ms,
            real_time_factor=real_time_factor,
            success=success,
            error_type=error_type,
            error_message=error_message,
            device=device,
        )


@dataclass
class TranscriptionResult:
    """Structured transcription outcome plus subtitle-ready conversion."""

    segments: List[TranscriptionSegment] = field(default_factory=list)
    language: str = "auto"
    duration_ms: Optional[int] = None
    model: Optional[str] = None
    provider: str = "whisper"
    processing_time_ms: Optional[int] = None
    success: bool = True
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    metrics: Optional[TranscriptionMetrics] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """JSON-compatible payload; carries aggregates, never media bytes."""
        return {
            "segments": [segment.to_dict() for segment in self.segments],
            "language": self.language,
            "duration_ms": self.duration_ms,
            "model": self.model,
            "provider": self.provider,
            "processing_time_ms": self.processing_time_ms,
            "success": self.success,
            "error_type": self.error_type,
            "error_message": self.error_message,
            "metrics": self.metrics.to_dict() if self.metrics is not None else None,
            "metadata": dict(self.metadata),
        }

    def to_subtitle_items(self) -> List[Any]:
        """Convert validated segments to ``SubtitleItem`` (reindexed, sane)."""
        from .subtitle_service import SubtitleItem

        items: List[Any] = []
        for position, segment in enumerate(self.segments, 1):
            text = (segment.text or "").strip()
            if not text:
                continue
            start_ms = max(0, int(segment.start_ms))
            end_ms = int(segment.end_ms)
            if end_ms <= start_ms:
                end_ms = start_ms + 1000
            items.append(
                SubtitleItem(
                    index=position, start_ms=start_ms, end_ms=end_ms, text=text
                )
            )
        for position, item in enumerate(items, 1):
            item.index = position
        return items
