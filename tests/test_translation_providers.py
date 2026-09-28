import io
import json
import logging
import urllib.error

import pytest

from application.services.translation_models import TranslationMetrics
from application.services.translation_providers import (
    DeepLProvider,
    GoogleProvider,
    OpenAICompatibleProvider,
    ProviderAuthenticationError,
    ProviderConfigurationError,
    ProviderRateLimitError,
    ProviderRegistry,
    ProviderResponse,
    ProviderResponseError,
    ProviderTimeoutError,
    TranslationProvider,
)
from application.services.translation_service import TranslationService


class MemoryConfig:
    def __init__(self, **values):
        self.values = values

    def get(self, key, default=None):
        return self.values.get(key, default)


class FakeProvider(TranslationProvider):
    name = "fake"
    model = "test-model"

    def __init__(self, config_service=None):
        self.response = ProviderResponse("translated", model=self.model)
        self.error = None
        self.calls = 0

    def translate(self, text, source_language, target_language, *, context=None):
        self.calls += 1
        if self.error:
            raise self.error
        return self.response.text

    def translate_detailed(
        self, text, source_language, target_language, *, context=None
    ):
        self.calls += 1
        if self.error:
            raise self.error
        return self.response


def _response(payload, status=200):
    response = io.BytesIO(json.dumps(payload).encode("utf-8"))
    response.status = status
    response.__enter__ = lambda: response
    response.__exit__ = lambda *args: False
    return response


def test_registry_registers_aliases_and_creates_valid_provider():
    provider = ProviderRegistry.get("google", MemoryConfig())
    assert isinstance(provider, GoogleProvider)
    assert ProviderRegistry.get("llm", MemoryConfig()).name == "openai"
    assert ProviderRegistry.get("ollama", MemoryConfig()).name == "openai"

    ProviderRegistry.register("test-custom-provider", FakeProvider)
    assert isinstance(ProviderRegistry.get("TEST-CUSTOM-PROVIDER"), FakeProvider)
    with pytest.raises(ValueError, match="ya registrado"):
        ProviderRegistry.register("test-custom-provider", FakeProvider)


def test_registry_rejects_unknown_provider():
    with pytest.raises(ProviderConfigurationError, match="no soportado"):
        ProviderRegistry.get("missing-provider")


def test_provider_contract_accepts_context_and_detailed_response():
    provider = FakeProvider()
    response = provider.translate_detailed("hello", "en", "es", context="scene")
    assert response.text == "translated"
    assert provider.calls == 1


def test_google_provider_uses_optional_library_and_validates_response(monkeypatch):
    import application.services.translation_providers as providers

    class Translator:
        def __init__(self, source, target):
            assert (source, target) == ("auto", "es")

        def translate(self, text):
            return "Hola"

    monkeypatch.setattr(providers, "GoogleTranslator", Translator)
    provider = GoogleProvider()
    provider.set_deep_translator_enabled(True)
    assert provider.translate("Hello", "auto", "es") == "Hola"

    class EmptyTranslator(Translator):
        def translate(self, text):
            return ""

    monkeypatch.setattr(providers, "GoogleTranslator", EmptyTranslator)
    with pytest.raises(ProviderResponseError):
        provider.translate("Hello", "auto", "es")


def test_google_provider_urllib_response_and_timeout_classification(monkeypatch):
    import application.services.translation_providers as providers

    monkeypatch.setattr(providers, "HAS_DEEP_TRANSLATOR", False)
    monkeypatch.setattr(
        providers.urllib.request,
        "urlopen",
        lambda *a, **kw: _response([[["Hola", "Hello", None, None, 1]]]),
    )
    provider = GoogleProvider()
    provider.set_deep_translator_enabled(False)
    assert provider.translate("Hello", "auto", "es") == "Hola"

    def timeout(*args, **kwargs):
        raise TimeoutError("private detail is not exposed")

    monkeypatch.setattr(providers.urllib.request, "urlopen", timeout)
    with pytest.raises(ProviderTimeoutError):
        provider.translate("Hello", "auto", "es")


def test_deepl_request_uses_config_without_logging_api_key(monkeypatch, caplog):
    import application.services.translation_providers as providers

    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["payload"] = json.loads(request.data)
        return _response({"translations": [{"text": "Hola"}]})

    monkeypatch.setattr(providers.urllib.request, "urlopen", fake_urlopen)
    key = "secret-test-key-do-not-log"
    provider = DeepLProvider(MemoryConfig(deepl_api_key=key, deepl_type="pro"))
    assert provider.translate("Hello", "en", "es") == "Hola"
    assert captured["url"] == "https://api.deepl.com/v2/translate"
    assert captured["payload"]["target_lang"] == "ES"
    assert key in captured["headers"]["Authorization"]
    assert key not in caplog.text


def test_deepl_requires_key_and_normalizes_auth_and_rate_limit(monkeypatch):
    import application.services.translation_providers as providers

    with pytest.raises(ProviderConfigurationError):
        DeepLProvider(MemoryConfig()).translate("text", "auto", "es")

    def auth_error(*args, **kwargs):
        raise urllib.error.HTTPError(
            "https://api-free.deepl.com/v2/translate", 401, "unauthorized", {}, None
        )

    monkeypatch.setattr(providers.urllib.request, "urlopen", auth_error)
    with pytest.raises(ProviderAuthenticationError):
        DeepLProvider(MemoryConfig(deepl_api_key="secret")).translate(
            "text", "auto", "es"
        )

    def limited(*args, **kwargs):
        raise urllib.error.HTTPError(
            "https://api-free.deepl.com/v2/translate", 429, "limited", {}, None
        )

    monkeypatch.setattr(providers.urllib.request, "urlopen", limited)
    with pytest.raises(ProviderRateLimitError):
        DeepLProvider(MemoryConfig(deepl_api_key="secret")).translate(
            "text", "auto", "es"
        )


def test_openai_compatible_preserves_prompt_and_reads_reported_usage(monkeypatch):
    import application.services.translation_providers as providers

    captured = {}

    def fake_urlopen(request, timeout):
        captured["payload"] = json.loads(request.data)
        captured["headers"] = dict(request.header_items())
        return _response(
            {
                "model": "llama3",
                "choices": [{"message": {"content": " Hola "}}],
                "usage": {
                    "prompt_tokens": 7,
                    "completion_tokens": 3,
                    "total_tokens": 10,
                },
            }
        )

    monkeypatch.setattr(providers.urllib.request, "urlopen", fake_urlopen)
    provider = OpenAICompatibleProvider(
        MemoryConfig(
            openai_base_url="http://localhost:11434/v1/",
            openai_model="llama3",
            openai_api_key="",
        )
    )
    result = provider.translate_detailed("Hello", "en", "es")
    assert result.text == "Hola"
    assert (result.input_tokens, result.output_tokens, result.total_tokens) == (
        7,
        3,
        10,
    )
    assert captured["payload"]["temperature"] == 0.2
    assert "Preserve formatting tags" in captured["payload"]["messages"][0]["content"]
    assert captured["payload"]["messages"][1]["content"] == "Hello"


def test_openai_compatible_bad_response_is_normalized(monkeypatch):
    import application.services.translation_providers as providers

    monkeypatch.setattr(
        providers.urllib.request, "urlopen", lambda *a, **kw: _response({"choices": []})
    )
    provider = OpenAICompatibleProvider(
        MemoryConfig(openai_base_url="http://localhost:11434/v1", openai_model="llama3")
    )
    with pytest.raises(ProviderResponseError):
        provider.translate("hello", "en", "es")


def test_google_selection_reports_google_as_the_provider_not_just_google_http_library(
    monkeypatch,
):
    provider = FakeProvider()
    monkeypatch.setattr(
        ProviderRegistry, "get", lambda name, config_service=None: provider
    )
    service = TranslationService(config_service=MemoryConfig(), fallbacks={})
    result = service.translate_with_metrics("hello", "es", provider="fake")
    assert result.metrics.provider == "fake"
    assert result.metrics.providers_used == ["fake"]


def test_translation_service_selects_provider_and_collects_metrics(monkeypatch):
    provider = FakeProvider()
    monkeypatch.setattr(
        ProviderRegistry, "get", lambda name, config_service=None: provider
    )
    service = TranslationService(config_service=MemoryConfig(), fallbacks={})
    result = service.translate_with_metrics(
        "hello world", "es", "en", provider="fake", context="scene"
    )

    assert result.text == "translated"
    assert isinstance(result.metrics, TranslationMetrics)
    assert result.metrics.provider == "fake"
    assert result.metrics.model == "test-model"
    assert result.metrics.number_of_cues == 1
    assert result.metrics.characters_input == 11
    assert result.metrics.words_output == 1
    assert result.metrics.duration_ms >= 0
    assert result.metrics.success is True
    assert result.metrics.estimated_cost is None
    assert json.loads(json.dumps(result.to_dict()))["metrics"]["input_tokens"] is None
    assert service.last_result is result


def test_translation_service_limits_retries_and_explicit_fallback(monkeypatch, caplog):
    providers = {"primary": FakeProvider(), "backup": FakeProvider()}
    providers["primary"].error = ProviderRateLimitError("rate limited")
    providers["backup"].response = ProviderResponse(
        "translated by backup", model="backup-model"
    )
    monkeypatch.setattr(
        ProviderRegistry, "get", lambda name, config_service=None: providers[name]
    )
    service = TranslationService(
        config_service=MemoryConfig(),
        fallbacks={"primary": ["backup"]},
        max_retries=1,
    )
    caplog.set_level(logging.WARNING, logger="srt4u")
    result = service.translate_with_metrics("hello", "es", provider="primary")

    assert result.text == "translated by backup"
    assert result.metrics.success is True
    assert result.metrics.retry_count == 1
    assert result.metrics.fallback_used is True
    assert result.metrics.requested_provider == "primary"
    assert result.metrics.provider == "backup"
    assert result.metrics.fallback_error_type == "rate_limit"
    aggregated = TranslationMetrics.aggregate(
        [result.metrics],
        source_language="auto",
        target_language="es",
        number_of_cues=1,
        characters_input=5,
        characters_output=len(result.text),
        words_input=1,
        words_output=3,
        duration_ms=result.metrics.duration_ms,
        success=True,
        requested_provider="primary",
    )
    assert aggregated.fallback_used is True
    assert aggregated.fallback_error_type == "rate_limit"
    assert aggregated.providers_used == ["backup"]
    assert providers["primary"].calls == 2
    assert "Translation fallback" in caplog.text
    assert "rate limited" not in caplog.text


def test_translation_service_rejects_fallback_cycle():
    service = TranslationService(
        config_service=MemoryConfig(),
        fallbacks={"primary": ["backup"], "backup": ["primary"]},
    )
    result = service.translate_with_metrics("text", "es", provider="primary")
    assert result.text == "text"
    assert result.metrics.success is False
    assert result.metrics.error_type == "configuration"
    assert result.metrics.provider == "primary"


def test_translation_service_normalizes_failure_and_keeps_original(monkeypatch):
    provider = FakeProvider()
    provider.error = ProviderAuthenticationError("credentials rejected")
    monkeypatch.setattr(
        ProviderRegistry, "get", lambda name, config_service=None: provider
    )
    service = TranslationService(config_service=MemoryConfig(), fallbacks={})
    result = service.translate_with_metrics("sensitive input", "es", provider="fake")

    assert result.text == "sensitive input"
    assert result.metrics.success is False
    assert result.metrics.error_type == "authentication"
    # Security policy: provider failure details are sanitized to the error
    # category; raw messages (which could contain secrets or content) are
    # never retained in metrics.
    assert result.metrics.error_message is None
    assert result.metrics.fallback_error_type == "authentication"
    assert service.last_error == "authentication"
    assert "credentials rejected" not in result.to_dict().__repr__()
    assert "sensitive input" not in result.metrics.error_type.__repr__()


def test_translation_metrics_never_retain_raw_provider_messages(monkeypatch):
    from application.services.translation_providers import ProviderNetworkError

    raw_details = [
        "Bearer sk-secret-123",
        "DeepL-Auth-Key secret-key",
        "private subtitle content here",
    ]
    for raw in raw_details:
        failing = FakeProvider()
        failing.error = ProviderNetworkError(raw)
        monkeypatch.setattr(
            ProviderRegistry,
            "get",
            lambda name, config_service=None, _provider=failing: _provider,
        )
        service = TranslationService(config_service=MemoryConfig(), fallbacks={})
        result = service.translate_with_metrics("hello", "es", provider="fake")
        assert result.metrics.success is False
        assert result.metrics.error_type == "network"
        assert result.metrics.error_message is None
        assert raw not in json.dumps(result.to_dict())


def test_translation_logs_never_contain_api_keys_or_input_text(monkeypatch, caplog):
    provider = FakeProvider()
    monkeypatch.setattr(
        ProviderRegistry, "get", lambda name, config_service=None: provider
    )
    service = TranslationService(config_service=MemoryConfig(), fallbacks={})
    caplog.set_level(logging.DEBUG, logger="srt4u")
    service.translate_with_metrics("very private subtitle text", "es", provider="fake")
    assert "very private subtitle text" not in caplog.text
    assert "secret-test-key-do-not-log" not in caplog.text


def test_invalid_registry_factory_and_endpoint_configuration_are_reported():
    ProviderRegistry.register("wrong-factory", lambda **kwargs: object())
    with pytest.raises(ProviderConfigurationError, match="no devolvió"):
        ProviderRegistry.get("wrong-factory")
    with pytest.raises(ProviderConfigurationError, match="URL base"):
        OpenAICompatibleProvider(MemoryConfig(openai_base_url="javascript:alert(1)"))


def test_translation_metrics_aggregate_unknown_tokens_as_null():
    metrics = TranslationMetrics.for_text(
        provider="fake",
        model="model",
        source_language="auto",
        target_language="es",
        source_text="a b",
        translated_text="c d",
        duration_ms=15,
        success=True,
        input_tokens=2,
        output_tokens=3,
        total_tokens=5,
    )
    aggregate = TranslationMetrics.aggregate(
        [metrics],
        source_language="auto",
        target_language="es",
        number_of_cues=2,
        characters_input=4,
        characters_output=4,
        words_input=2,
        words_output=2,
        duration_ms=15,
        success=True,
        requested_provider="fake",
    )
    assert aggregate.input_tokens == 2
    assert aggregate.total_tokens == 5
    assert aggregate.estimated_cost is None


def test_translation_service_rejects_invalid_max_retries():
    with pytest.raises(ValueError, match="no negativo"):
        TranslationService(config_service=MemoryConfig(), max_retries=-1)
    with pytest.raises(ValueError, match="no negativo"):
        TranslationService(config_service=MemoryConfig(), max_retries=True)
    with pytest.raises(ValueError, match="no negativo"):
        TranslationService(config_service=MemoryConfig(), max_retries="2")


def test_translation_service_rejects_overlong_fallback_chain():
    fallbacks = {f"p{i}": [f"p{i + 1}"] for i in range(9)}
    service = TranslationService(config_service=MemoryConfig(), fallbacks=fallbacks)
    result = service.translate_with_metrics("text", "es", provider="p0")
    assert result.metrics.success is False
    assert result.metrics.error_type == "configuration"


def test_translation_service_rejects_non_string_text():
    service = TranslationService(config_service=MemoryConfig(), fallbacks={})
    result = service.translate_with_metrics(123, "es", provider="google")
    assert result.text == "123"
    assert result.metrics.success is False
    assert result.metrics.error_type == "configuration"


def test_translation_metrics_aggregate_partial_tokens_stays_null():
    known = TranslationMetrics.for_text(
        provider="fake",
        model="m",
        source_language="auto",
        target_language="es",
        source_text="a",
        translated_text="b",
        duration_ms=1,
        success=True,
        input_tokens=2,
        output_tokens=3,
        total_tokens=5,
    )
    unknown = TranslationMetrics.for_text(
        provider="fake",
        model="m",
        source_language="auto",
        target_language="es",
        source_text="c",
        translated_text="d",
        duration_ms=1,
        success=True,
    )
    aggregate = TranslationMetrics.aggregate(
        [known, unknown],
        source_language="auto",
        target_language="es",
        number_of_cues=2,
        characters_input=2,
        characters_output=2,
        words_input=2,
        words_output=2,
        duration_ms=2,
        success=True,
        requested_provider="fake",
    )
    assert aggregate.input_tokens is None
    assert aggregate.output_tokens is None
    assert aggregate.total_tokens is None
    assert aggregate.estimated_cost is None


def test_translation_metrics_aggregate_duration_is_wall_time_not_sum():
    first = TranslationMetrics.for_text(
        provider="fake",
        model="m",
        source_language="auto",
        target_language="es",
        source_text="a",
        translated_text="b",
        duration_ms=100,
        success=True,
    )
    second = TranslationMetrics.for_text(
        provider="fake",
        model="m",
        source_language="auto",
        target_language="es",
        source_text="c",
        translated_text="d",
        duration_ms=100,
        success=True,
    )
    aggregate = TranslationMetrics.aggregate(
        [first, second],
        source_language="auto",
        target_language="es",
        number_of_cues=2,
        characters_input=2,
        characters_output=2,
        words_input=2,
        words_output=2,
        duration_ms=5,
        success=True,
        requested_provider="fake",
    )
    assert aggregate.duration_ms == 5
    assert aggregate.duration_ms != 200


def test_subtitle_service_reports_wall_time_aggregate(monkeypatch):
    from application.services.subtitle_service import SubtitleItem, SubtitleService

    class SlowProvider(TranslationProvider):
        name = "slow"
        model = None

        def translate(self, text, source_language, target_language, *, context=None):
            return f"{text}-t"

        def translate_detailed(
            self, text, source_language, target_language, *, context=None
        ):
            return ProviderResponse(
                f"{text}-t",
                model=None,
                input_tokens=None,
                output_tokens=None,
                total_tokens=None,
            )

    monkeypatch.setattr(
        ProviderRegistry, "get", lambda name, config_service=None: SlowProvider()
    )
    service = SubtitleService(
        TranslationService(config_service=MemoryConfig(), fallbacks={})
    )
    # Wall clock advances 250ms while per-cue latencies stay at 0ms, proving
    # the aggregate is wall-time and not the sum of per-cue durations.
    import application.services.subtitle_service as subtitle_module

    state = {"calls": 0}

    def fake_perf_counter():
        state["calls"] += 1
        return 1000.0 if state["calls"] == 1 else 1000.25

    monkeypatch.setattr(subtitle_module.time, "perf_counter", fake_perf_counter)
    items = [
        SubtitleItem(index=1, start_ms=0, end_ms=1000, text="Hello"),
        SubtitleItem(index=2, start_ms=1000, end_ms=2000, text="World"),
    ]
    service.translate_subtitles(
        items, target_language="es", engine="slow", parallel=False
    )
    metrics = service.last_translation_metrics
    assert metrics is not None
    assert metrics.duration_ms == 250
    assert metrics.number_of_cues == 2
    assert metrics.success is True


def test_subtitle_service_end_to_end_translation_metrics(monkeypatch):
    import json as json_module

    from application.services.subtitle_service import SubtitleItem, SubtitleService

    provider = FakeProvider()
    monkeypatch.setattr(
        ProviderRegistry, "get", lambda name, config_service=None: provider
    )
    service = SubtitleService(
        TranslationService(config_service=MemoryConfig(), fallbacks={})
    )
    items = [SubtitleItem(index=1, start_ms=0, end_ms=1000, text="hello world")]
    result = service.translate_subtitles(
        items, target_language="es", source_language="en", engine="fake", parallel=False
    )
    assert [item.text for item in result] == ["translated"]
    metrics = service.last_translation_metrics
    assert metrics is not None
    assert metrics.provider == "fake"
    assert metrics.requested_provider == "fake"
    assert metrics.number_of_cues == 1
    assert metrics.success is True
    assert metrics.estimated_cost is None
    assert json_module.loads(json_module.dumps(metrics.to_dict()))["provider"] == "fake"


def test_ollama_alias_preserves_requested_provider_and_config(monkeypatch):
    captured = {}

    class FakeOllamaBackend(TranslationProvider):
        name = "openai"

        def __init__(self, config_service=None):
            captured["base_url"] = config_service.get("openai_base_url")
            captured["model"] = config_service.get("openai_model")

        def translate(self, text, source_language, target_language, *, context=None):
            return "Hola"

        def translate_detailed(
            self, text, source_language, target_language, *, context=None
        ):
            return ProviderResponse("Hola", model=captured["model"])

    monkeypatch.setitem(
        ProviderRegistry._factories,
        "ollama",
        lambda config_service=None: FakeOllamaBackend(config_service),
    )
    try:
        config = MemoryConfig(
            openai_base_url="http://localhost:11434/v1",
            openai_model="llama3",
            openai_api_key="",
        )
        service = TranslationService(config_service=config)
        result = service.translate_with_metrics("Hello", "es", provider="ollama")
        assert result.text == "Hola"
        assert result.metrics.requested_provider == "ollama"
        assert result.metrics.providers_used == ["ollama"]
        assert result.metrics.model == "llama3"
        assert captured["base_url"] == "http://localhost:11434/v1"
        # openai and llm resolve to the same compatible implementation.
        assert ProviderRegistry.get("openai", config).name == "openai"
        assert ProviderRegistry.get("llm", config).name == "openai"
    finally:
        from application.services.translation_providers import OpenAICompatibleProvider

        ProviderRegistry._factories["ollama"] = lambda config_service=None: (
            OpenAICompatibleProvider(config_service)
        )


def test_translation_result_serializes_all_metric_fields(monkeypatch):
    provider = FakeProvider()
    provider.response = ProviderResponse(
        "translated",
        model="test-model",
        input_tokens=4,
        output_tokens=2,
        total_tokens=6,
        estimated_cost=None,
    )
    monkeypatch.setattr(
        ProviderRegistry, "get", lambda name, config_service=None: provider
    )
    service = TranslationService(config_service=MemoryConfig(), fallbacks={})
    result = service.translate_with_metrics("hello world", "es", "en", provider="fake")
    payload = json.loads(json.dumps(result.to_dict()))
    expected = {
        "provider",
        "model",
        "source_language",
        "target_language",
        "number_of_cues",
        "characters_input",
        "characters_output",
        "words_input",
        "words_output",
        "duration_ms",
        "success",
        "error_type",
        "retry_count",
        "fallback_used",
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "estimated_cost",
        "requested_provider",
        "providers_used",
        "error_message",
        "fallback_error_type",
    }
    assert expected <= set(payload["metrics"])
    assert payload["metrics"]["input_tokens"] == 4
    assert payload["metrics"]["estimated_cost"] is None
