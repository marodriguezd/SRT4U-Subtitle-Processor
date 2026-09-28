"""Provider-neutral translation coordinator with a backward-compatible text API."""

import threading
import time
from typing import Callable, Dict, List, Optional

from ..logging_setup import get_logger
from .config_service import ConfigService
from .translation_models import TranslationMetrics, TranslationResult
from .translation_providers import (
    ProviderConfigurationError,
    ProviderRegistry,
    ProviderResponse,
    ProviderResponseError,
    TranslationProviderError,
    ProviderUnknownError,
)

logger = get_logger("translation")


class TranslationService:
    """Coordinates registered providers and exposes legacy and structured APIs."""

    SUPPORTED_LANGUAGES: List[Dict[str, str]] = [
        {"code": "es", "name": "Español"},
        {"code": "en", "name": "English"},
        {"code": "fr", "name": "Français"},
        {"code": "de", "name": "Deutsch"},
        {"code": "it", "name": "Italiano"},
        {"code": "pt", "name": "Português"},
        {"code": "ja", "name": "日本語 (Japanese)"},
        {"code": "ko", "name": "한국어 (Korean)"},
        {"code": "zh-CN", "name": "简体中文 (Chinese)"},
        {"code": "ru", "name": "Русский (Russian)"},
    ]

    # Compatibility policy: previous automatic fallbacks are now explicit/configurable.
    DEFAULT_FALLBACKS = {
        "deepl": ("google",),
        "openai": ("google",),
        "llm": ("google",),
        "ollama": ("google",),
    }

    def __init__(
        self,
        config_service: Optional[ConfigService] = None,
        *,
        fallbacks: Optional[Dict[str, List[str]]] = None,
        max_retries: int = 0,
    ):
        self.config_service = config_service or ConfigService()
        if (
            isinstance(max_retries, bool)
            or not isinstance(max_retries, int)
            or max_retries < 0
        ):
            raise ValueError("max_retries debe ser un entero no negativo")
        self.max_retries = max_retries
        configured_fallbacks = (
            self.DEFAULT_FALLBACKS if fallbacks is None else fallbacks
        )
        self.fallbacks = {
            str(name).casefold(): tuple(str(value).casefold() for value in values)
            for name, values in configured_fallbacks.items()
        }
        self._tls = threading.local()

    @property
    def last_error(self) -> Optional[str]:
        return getattr(self._tls, "last_error", None)

    @property
    def last_result(self) -> Optional[TranslationResult]:
        return getattr(self._tls, "last_result", None)

    def _set_result(self, result: TranslationResult) -> None:
        self._tls.last_result = result
        self._tls.last_error = (
            result.metrics.error_type if not result.metrics.success else None
        )

    def _set_last_error(self, message: Optional[str]) -> None:
        """Backward-compatible setter used by integrations and test doubles."""
        self._tls.last_error = message
        result = getattr(self._tls, "last_result", None)
        if result is not None and message:
            result.metrics.success = False
            result.metrics.error_message = message
            result.metrics.error_type = "unknown"

    def clear_last_result(self) -> None:
        self._tls.last_result = None
        self._tls.last_error = None

    def translate_text(
        self,
        text: str,
        target_language: str,
        source_language: str = "auto",
        engine: str = "google",
        progress_callback: Optional[Callable] = None,
    ) -> str:
        """Translate a fragment and preserve the legacy string-returning API."""
        result = self.translate_with_metrics(
            text=text,
            target_language=target_language,
            source_language=source_language,
            provider=engine,
        )
        self._tls.last_error = (
            result.metrics.error_type if not result.metrics.success else None
        )
        if progress_callback:
            progress_callback("translation", result.text)
        return result.text

    def translate_with_metrics(
        self,
        text: str,
        target_language: str,
        source_language: str = "auto",
        provider: str = "google",
        *,
        context: Optional[str] = None,
    ) -> TranslationResult:
        """Translate via the registry and report metrics without leaking content/secrets."""
        started = time.perf_counter()
        requested = provider.casefold() if isinstance(provider, str) else str(provider)
        if not isinstance(text, str):
            error = ProviderConfigurationError("el texto debe ser una cadena")
            result = self._failure_result(
                text=str(text),
                provider=requested,
                source_language=source_language,
                target_language=target_language,
                started=started,
                error=error,
                requested_provider=requested,
            )
            self._set_result(result)
            return result
        if not text:
            result = TranslationResult(
                text,
                TranslationMetrics.for_text(
                    provider=requested,
                    model=None,
                    source_language=source_language,
                    target_language=target_language,
                    source_text=text,
                    translated_text=text,
                    duration_ms=0,
                    success=True,
                    requested_provider=requested,
                    providers_used=[],
                ),
            )
            self._set_result(result)
            return result

        try:
            candidates = self._provider_chain(requested)
        except ProviderConfigurationError as error:
            result = self._failure_result(
                text=text,
                provider=requested,
                source_language=source_language,
                target_language=target_language,
                started=started,
                error=error,
                requested_provider=requested,
            )
            self._set_result(result)
            return result
        providers_used: List[str] = []
        attempted_providers: List[str] = []
        fallback_used = False
        original_error: Optional[TranslationProviderError] = None
        fallback_error_type = None
        last_error: Optional[TranslationProviderError] = None
        response: Optional[ProviderResponse] = None
        translated = text
        selected = requested
        total_retries = 0

        for candidate_position, candidate in enumerate(candidates):
            if candidate_position:
                fallback_used = True
                logger.warning(
                    "Translation fallback: requested=%s provider=%s error_type=%s",
                    requested,
                    candidate,
                    original_error.error_type if original_error else "unknown",
                )
            provider_attempts = 0
            candidate_response = None
            try:
                active_provider = ProviderRegistry.get(candidate, self.config_service)
                attempted_providers.append(candidate)
                while True:
                    try:
                        candidate_response = active_provider.translate_detailed(
                            text, source_language, target_language, context=context
                        )
                        if (
                            not isinstance(candidate_response, ProviderResponse)
                            or not isinstance(candidate_response.text, str)
                            or not candidate_response.text.strip()
                        ):
                            raise ProviderResponseError(
                                "provider devolvió una respuesta de traducción inválida"
                            )
                        response = candidate_response
                        translated = candidate_response.text
                        selected = candidate
                        providers_used.append(candidate)
                        last_error = None
                        break
                    except Exception as raw_error:
                        exc = (
                            raw_error
                            if isinstance(raw_error, TranslationProviderError)
                            else ProviderUnknownError(
                                f"{candidate}: error de provider ({type(raw_error).__name__})"
                            )
                        )
                        last_error = exc
                        if candidate_position == 0:
                            original_error = exc
                            fallback_error_type = exc.error_type
                        if exc.retryable and provider_attempts < self.max_retries:
                            provider_attempts += 1
                            total_retries += 1
                            logger.warning(
                                "Translation retry: provider=%s model=%s retry=%s error_type=%s",
                                candidate,
                                getattr(active_provider, "model", None),
                                provider_attempts,
                                exc.error_type,
                            )
                            continue
                        raise
                break
            except TranslationProviderError as exc:
                last_error = exc
                if candidate_position == 0:
                    original_error = exc
                    fallback_error_type = exc.error_type
                else:
                    fallback_error_type = exc.error_type
            except Exception as exc:
                safe_error = (
                    exc
                    if isinstance(exc, TranslationProviderError)
                    else ProviderUnknownError(
                        f"{candidate}: error de provider ({type(exc).__name__})"
                    )
                )
                last_error = safe_error
                if candidate_position == 0:
                    original_error = safe_error
                fallback_error_type = safe_error.error_type

        success = last_error is None and bool(translated)
        duration_ms = int((time.perf_counter() - started) * 1000)
        error_type = None
        error_message = None
        if not success:
            error = last_error or ProviderConfigurationError(
                f"no se pudo resolver el provider: {requested}"
            )
            error_type = error.error_type
            error_message = None
            logger.warning(
                "Translation failed: provider=%s model=%s error_type=%s",
                selected,
                response.model if response else None,
                error_type,
            )

        metrics = TranslationMetrics.for_text(
            provider=selected,
            model=response.model if response else None,
            source_language=source_language,
            target_language=target_language,
            source_text=text,
            translated_text=translated,
            duration_ms=duration_ms,
            success=success,
            error_type=error_type,
            retry_count=total_retries,
            fallback_used=fallback_used,
            input_tokens=response.input_tokens if response else None,
            output_tokens=response.output_tokens if response else None,
            total_tokens=response.total_tokens if response else None,
            estimated_cost=response.estimated_cost if response else None,
            requested_provider=requested,
            providers_used=providers_used or attempted_providers,
            error_message=error_message,
            fallback_error_type=fallback_error_type,
        )
        result = TranslationResult(translated, metrics)
        self._set_result(result)
        if success:
            logger.info(
                "Translation completed: provider=%s model=%s duration_ms=%s retries=%s fallback=%s",
                selected,
                metrics.model,
                duration_ms,
                total_retries,
                fallback_used,
            )
        return result

    def _provider_chain(self, requested: str) -> tuple[str, ...]:
        """Resolve a bounded, deterministic fallback chain and reject cycles."""
        chain = []
        pending = [requested]
        while pending:
            candidate = pending.pop(0)
            if candidate in chain:
                raise ProviderConfigurationError(
                    f"fallback circular o repetido para provider: {candidate}"
                )
            chain.append(candidate)
            if len(chain) > 8:
                raise ProviderConfigurationError(
                    "la cadena de fallback supera 8 providers"
                )
            pending.extend(self.fallbacks.get(candidate, ()))
        return tuple(chain)

    @staticmethod
    def _failure_result(
        *,
        text,
        provider,
        source_language,
        target_language,
        started,
        error,
        requested_provider,
    ):
        return TranslationResult(
            text,
            TranslationMetrics.for_text(
                provider=provider,
                model=None,
                source_language=source_language,
                target_language=target_language,
                source_text=text,
                translated_text=text,
                duration_ms=int((time.perf_counter() - started) * 1000),
                success=False,
                error_type=error.error_type,
                retry_count=error.retry_count,
                requested_provider=requested_provider,
                providers_used=[],
                error_message=str(error),
            ),
        )
