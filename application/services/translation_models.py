"""Framework-independent translation execution and result models."""

from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, Optional


def _word_count(text: str) -> int:
    return len(text.split())


@dataclass
class TranslationMetrics:
    """Observable metrics for one translation request or aggregated file run."""

    provider: str
    model: Optional[str]
    source_language: str
    target_language: str
    number_of_cues: int
    characters_input: int
    characters_output: int
    words_input: int
    words_output: int
    duration_ms: Optional[int]
    success: bool
    error_type: Optional[str] = None
    retry_count: int = 0
    fallback_used: bool = False
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    estimated_cost: Optional[float] = None
    requested_provider: Optional[str] = None
    providers_used: Optional[list[str]] = None
    error_message: Optional[str] = None
    fallback_error_type: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Return JSON-compatible metrics; unknown token/cost values remain null."""
        return asdict(self)

    @classmethod
    def aggregate(
        cls,
        metrics: Iterable["TranslationMetrics"],
        *,
        source_language: str,
        target_language: str,
        number_of_cues: int,
        characters_input: int,
        characters_output: int,
        words_input: int,
        words_output: int,
        duration_ms: Optional[int],
        success: bool,
        requested_provider: str,
        providers_used: Optional[list[str]] = None,
        error_type: Optional[str] = None,
        error_message: Optional[str] = None,
        fallback_error_type: Optional[str] = None,
    ) -> "TranslationMetrics":
        runs = list(metrics)
        used_providers = (
            list(dict.fromkeys(providers_used))
            if providers_used is not None
            else list(
                dict.fromkeys(
                    provider
                    for run in runs
                    for provider in (run.providers_used or [run.provider])
                )
            )
        )
        models = {run.model for run in runs if run.model}

        def sum_when_known(name: str) -> Optional[int]:
            values = [getattr(run, name) for run in runs]
            return (
                sum(values)
                if values and all(value is not None for value in values)
                else None
            )

        costs = [run.estimated_cost for run in runs]
        fallback_errors = [
            run.fallback_error_type for run in runs if run.fallback_error_type
        ]
        return cls(
            provider=used_providers[-1] if used_providers else requested_provider,
            model=next(iter(models)) if len(models) == 1 else None,
            source_language=source_language,
            target_language=target_language,
            number_of_cues=number_of_cues,
            characters_input=characters_input,
            characters_output=characters_output,
            words_input=words_input,
            words_output=words_output,
            duration_ms=(max(0, int(duration_ms)) if duration_ms is not None else None),
            success=success,
            error_type=error_type,
            retry_count=sum(run.retry_count for run in runs),
            fallback_used=any(run.fallback_used for run in runs),
            input_tokens=sum_when_known("input_tokens"),
            output_tokens=sum_when_known("output_tokens"),
            total_tokens=sum_when_known("total_tokens"),
            estimated_cost=sum(costs)
            if costs and all(cost is not None for cost in costs)
            else None,
            requested_provider=requested_provider,
            providers_used=used_providers,
            error_message=error_message,
            fallback_error_type=(
                fallback_error_type or (fallback_errors[0] if fallback_errors else None)
            ),
        )

    @classmethod
    def for_text(
        cls,
        *,
        provider: str,
        model: Optional[str],
        source_language: str,
        target_language: str,
        source_text: str,
        translated_text: str,
        duration_ms: int,
        success: bool,
        error_type: Optional[str] = None,
        retry_count: int = 0,
        fallback_used: bool = False,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
        total_tokens: Optional[int] = None,
        estimated_cost: Optional[float] = None,
        requested_provider: Optional[str] = None,
        providers_used: Optional[list[str]] = None,
        error_message: Optional[str] = None,
        fallback_error_type: Optional[str] = None,
    ) -> "TranslationMetrics":
        return cls(
            provider=provider,
            model=model,
            source_language=source_language,
            target_language=target_language,
            number_of_cues=1,
            characters_input=len(source_text),
            characters_output=len(translated_text),
            words_input=_word_count(source_text),
            words_output=_word_count(translated_text),
            duration_ms=max(0, int(duration_ms)),
            success=success,
            error_type=error_type,
            retry_count=max(0, retry_count),
            fallback_used=fallback_used,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            estimated_cost=estimated_cost,
            requested_provider=requested_provider,
            providers_used=providers_used or [provider],
            error_message=error_message,
            fallback_error_type=fallback_error_type,
        )


@dataclass
class TranslationResult:
    """Translated text plus structured execution metrics."""

    text: str
    metrics: TranslationMetrics

    def to_dict(self) -> Dict[str, Any]:
        return {"text": self.text, "metrics": self.metrics.to_dict()}
