import csv
import io
import json

import pytest

from application.services.translation_benchmark import (
    BENCHMARK_CSV_COLUMNS,
    BENCHMARK_DATASET_VERSION,
    BenchmarkConfig,
    TranslationBenchmark,
    load_benchmark_dataset,
)
from application.services.translation_models import TranslationMetrics
from application.services.translation_providers import (
    ProviderRateLimitError,
    ProviderRegistry,
    ProviderResponse,
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


CUES = ["Hello.", "Good morning, how are you?", "See you later!"]


def _service(**kwargs):
    kwargs.setdefault("config_service", MemoryConfig())
    kwargs.setdefault("fallbacks", {})
    return TranslationService(**kwargs)


def _frozen_clock(monkeypatch):
    """Wall-time of each benchmark pass is exactly 1000 ms."""
    import application.services.translation_benchmark as benchmark_module

    state = {"calls": 0}

    def fake_perf_counter():
        state["calls"] += 1
        return 100.0 if state["calls"] % 2 else 101.0

    monkeypatch.setattr(benchmark_module.time, "perf_counter", fake_perf_counter)


def test_benchmark_single_run_records_metrics(monkeypatch):
    provider = FakeProvider()
    monkeypatch.setattr(
        ProviderRegistry, "get", lambda name, config_service=None: provider
    )
    _frozen_clock(monkeypatch)
    config = BenchmarkConfig(providers=["fake"], runs=1)
    report = TranslationBenchmark(config, translation_service=_service()).run(CUES)

    assert report.dataset_version == BENCHMARK_DATASET_VERSION
    assert report.dataset_size == 3
    assert len(report.runs) == 1
    run = report.runs[0]
    assert run.run_index == 0
    assert run.provider == "fake"
    assert run.requested_provider == "fake"
    assert run.model == "test-model"
    assert (run.source_language, run.target_language) == ("en", "es")
    assert run.number_of_cues == 3
    assert run.characters_input == sum(len(text) for text in CUES)
    assert run.words_input == sum(len(text.split()) for text in CUES)
    assert run.duration_ms == 1000
    assert run.success is True
    assert run.error_type is None
    assert run.estimated_cost is None
    assert run.input_tokens is None
    assert run.input_texts is None
    assert run.output_texts is None


def test_benchmark_derived_throughput_metrics(monkeypatch):
    provider = FakeProvider()
    monkeypatch.setattr(
        ProviderRegistry, "get", lambda name, config_service=None: provider
    )
    _frozen_clock(monkeypatch)
    cues = ["ab cd", "ef gh", "ij kl", "mn op"]
    run = (
        TranslationBenchmark(
            BenchmarkConfig(providers=["fake"]), translation_service=_service()
        )
        .run(cues)
        .runs[0]
    )

    assert run.duration_ms == 1000
    assert run.cues_per_second == pytest.approx(4.0)
    assert run.characters_per_second == pytest.approx(20.0)
    assert run.words_per_second == pytest.approx(8.0)
    assert run.latency_per_cue_ms == pytest.approx(250.0)
    assert run.latency_per_1k_chars_ms == pytest.approx(50000.0)


def test_benchmark_multiple_providers_and_runs_are_individual_rows(monkeypatch):
    providers = {"a": FakeProvider(), "b": FakeProvider()}
    monkeypatch.setattr(
        ProviderRegistry, "get", lambda name, config_service=None: providers[name]
    )
    config = BenchmarkConfig(providers=["a", "b"], runs=3)
    report = TranslationBenchmark(config, translation_service=_service()).run(CUES)

    assert len(report.runs) == 6
    assert [(run.requested_provider, run.run_index) for run in report.runs] == [
        ("a", 0),
        ("b", 0),
        ("a", 1),
        ("b", 1),
        ("a", 2),
        ("b", 2),
    ]
    assert len({run.benchmark_id for run in report.runs}) == 1


def test_benchmark_failure_records_error_without_texts(monkeypatch):
    from application.services.translation_providers import ProviderAuthenticationError

    provider = FakeProvider()
    provider.error = ProviderAuthenticationError("credentials rejected")
    monkeypatch.setattr(
        ProviderRegistry, "get", lambda name, config_service=None: provider
    )
    run = (
        TranslationBenchmark(
            BenchmarkConfig(providers=["fake"]), translation_service=_service()
        )
        .run(CUES)
        .runs[0]
    )

    assert run.success is False
    assert run.error_type == "authentication"
    assert run.error_message is None
    assert "credentials rejected" not in json.dumps(run.to_dict())


def test_benchmark_counts_retries(monkeypatch):
    provider = FakeProvider()
    provider.error = ProviderRateLimitError("limited")
    monkeypatch.setattr(
        ProviderRegistry, "get", lambda name, config_service=None: provider
    )
    service = TranslationService(
        config_service=MemoryConfig(), fallbacks={}, max_retries=2
    )
    report = TranslationBenchmark(
        BenchmarkConfig(providers=["fake"]), translation_service=service
    ).run(["hello"])
    assert report.runs[0].retry_count == 2
    assert report.runs[0].success is False


def test_benchmark_fallback_distinguishes_requested_from_effective(monkeypatch):
    primary = FakeProvider()
    primary.error = ProviderRateLimitError("limited")
    backup = FakeProvider()
    backup.response = ProviderResponse("backup translation", model="backup-model")
    providers = {"primary": primary, "backup": backup}
    monkeypatch.setattr(
        ProviderRegistry, "get", lambda name, config_service=None: providers[name]
    )
    service = TranslationService(
        config_service=MemoryConfig(), fallbacks={"primary": ["backup"]}
    )
    run = (
        TranslationBenchmark(
            BenchmarkConfig(providers=["primary"]), translation_service=service
        )
        .run(CUES)
        .runs[0]
    )

    assert run.success is True
    assert run.requested_provider == "primary"
    assert run.requested_provider != run.provider
    assert run.provider == "backup"
    assert run.fallback_used is True
    assert run.providers_used == ["backup"]
    assert run.fallback_error_type == "rate_limit"


def test_benchmark_unknown_provider_records_failure(monkeypatch):
    run = (
        TranslationBenchmark(
            BenchmarkConfig(providers=["missing-provider"]),
            translation_service=_service(),
        )
        .run(CUES)
        .runs[0]
    )

    assert run.success is False
    assert run.error_type == "configuration"
    assert run.requested_provider == "missing-provider"


def test_benchmark_rejects_invalid_config():
    with pytest.raises(ValueError, match="at least one provider"):
        BenchmarkConfig(providers=[])
    with pytest.raises(ValueError, match="positive integer"):
        BenchmarkConfig(providers=["google"], runs=0)
    with pytest.raises(ValueError, match="positive integer"):
        BenchmarkConfig(providers=["google"], runs=True)


def test_benchmark_rejects_empty_dataset():
    config = BenchmarkConfig(providers=["google"])
    with pytest.raises(ValueError, match="empty"):
        TranslationBenchmark(config, translation_service=_service()).run([])
    with pytest.raises(ValueError, match="empty"):
        TranslationBenchmark(config, translation_service=_service()).run(["   "])


def test_benchmark_include_texts_is_opt_in(monkeypatch):
    provider = FakeProvider()
    monkeypatch.setattr(
        ProviderRegistry, "get", lambda name, config_service=None: provider
    )
    service = _service()
    plain = (
        TranslationBenchmark(
            BenchmarkConfig(providers=["fake"]), translation_service=service
        )
        .run(CUES)
        .runs[0]
    )
    assert plain.input_texts is None
    assert plain.output_texts is None

    full = (
        TranslationBenchmark(
            BenchmarkConfig(providers=["fake"], include_texts=True),
            translation_service=service,
        )
        .run(CUES)
        .runs[0]
    )
    assert full.input_texts == CUES
    assert full.output_texts == ["translated"] * len(CUES)


def test_benchmark_json_roundtrip_and_csv_shape(monkeypatch):
    providers = {"a": FakeProvider(), "b": FakeProvider()}
    monkeypatch.setattr(
        ProviderRegistry, "get", lambda name, config_service=None: providers[name]
    )
    report = TranslationBenchmark(
        BenchmarkConfig(providers=["a", "b"], runs=2),
        translation_service=_service(),
    ).run(CUES)

    payload = json.loads(report.to_json())
    assert payload["benchmark_id"] == report.benchmark_id
    assert payload["dataset_version"] == BENCHMARK_DATASET_VERSION
    assert set(payload["config"]) >= {
        "providers",
        "source_language",
        "target_language",
        "runs",
        "include_texts",
    }
    assert set(payload["environment"]) >= {"python", "platform"}
    assert len(payload["runs"]) == 4
    assert json.loads(json.dumps(payload)) == payload

    rows = list(csv.DictReader(io.StringIO(report.to_csv())))
    assert len(rows) == 4
    assert list(rows[0].keys()) == BENCHMARK_CSV_COLUMNS
    assert {row["requested_provider"] for row in rows} == {"a", "b"}
    assert {row["run_index"] for row in rows} == {"0", "1"}


def test_benchmark_tokens_and_cost_stay_null_without_data(monkeypatch):
    provider = FakeProvider()
    monkeypatch.setattr(
        ProviderRegistry, "get", lambda name, config_service=None: provider
    )
    run = (
        TranslationBenchmark(
            BenchmarkConfig(providers=["fake"]), translation_service=_service()
        )
        .run(CUES)
        .runs[0]
    )
    assert run.input_tokens is None
    assert run.output_tokens is None
    assert run.total_tokens is None
    assert run.estimated_cost is None


def test_load_benchmark_dataset_defaults_and_files(tmp_path):
    builtin = load_benchmark_dataset()
    assert builtin["version"] == BENCHMARK_DATASET_VERSION
    assert len(builtin["cues"]) >= 8

    fixture = load_benchmark_dataset("tests/fixtures/benchmark/sample_en.srt")
    assert len(fixture["cues"]) == 8
    assert fixture["cues"][0] == "Hello."

    directory = load_benchmark_dataset("tests/fixtures/benchmark")
    assert directory["cues"] == fixture["cues"]

    empty = tmp_path / "empty.srt"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="no cues"):
        load_benchmark_dataset(str(empty))
    with pytest.raises(ValueError, match="not found"):
        load_benchmark_dataset(str(tmp_path / "missing.srt"))


def test_benchmark_integration_dataset_to_json(monkeypatch):
    provider = FakeProvider()
    monkeypatch.setattr(
        ProviderRegistry, "get", lambda name, config_service=None: provider
    )
    dataset = load_benchmark_dataset("tests/fixtures/benchmark/sample_en.srt")
    report = TranslationBenchmark(
        BenchmarkConfig(providers=["fake"], source_language="en", target_language="es"),
        translation_service=_service(),
    ).run(dataset["cues"])

    payload = json.loads(report.to_json())
    assert payload["dataset_size"] == 8
    assert payload["runs"][0]["number_of_cues"] == 8
    assert payload["runs"][0]["words_input"] == sum(
        len(text.split()) for text in dataset["cues"]
    )


def test_cli_benchmark_writes_json_and_csv(tmp_path, monkeypatch):
    import application.cli as cli

    provider = FakeProvider()
    monkeypatch.setattr(
        ProviderRegistry, "get", lambda name, config_service=None: provider
    )
    output = tmp_path / "bench.json"
    output_csv = tmp_path / "bench.csv"
    exit_code = cli.main(
        [
            "benchmark",
            "tests/fixtures/benchmark/sample_en.srt",
            "--providers",
            "fake",
            "--source",
            "en",
            "--target",
            "es",
            "--runs",
            "2",
            "--output",
            str(output),
            "--output-csv",
            str(output_csv),
        ]
    )
    assert exit_code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert len(payload["runs"]) == 2
    assert payload["runs"][0]["requested_provider"] == "fake"
    rows = list(csv.DictReader(io.StringIO(output_csv.read_text(encoding="utf-8"))))
    assert len(rows) == 2
    assert rows[0]["number_of_cues"] == "8"


def test_cli_benchmark_rejects_invalid_arguments(tmp_path, capsys):
    import application.cli as cli

    with pytest.raises(SystemExit) as exc:
        cli.main(["benchmark", "--providers", "fake", "--runs", "0"])
    assert exc.value.code == 2
    with pytest.raises(SystemExit) as exc:
        cli.main(["benchmark", str(tmp_path / "missing.srt"), "--providers", "fake"])
    assert exc.value.code == 2
    capsys.readouterr()


def test_benchmark_service_factory_per_provider(monkeypatch):
    seen = []

    def factory(provider):
        seen.append(provider)
        provider_instance = FakeProvider()
        monkeypatch.setattr(
            ProviderRegistry,
            "get",
            lambda name, config_service=None: provider_instance,
        )
        return TranslationService(config_service=MemoryConfig(), fallbacks={})

    config = BenchmarkConfig(providers=["x", "y"])
    report = TranslationBenchmark(config, service_factory=factory).run(CUES)
    assert seen == ["x", "y"]
    assert len(report.runs) == 2

    with pytest.raises(ValueError, match="must return a TranslationService"):
        TranslationBenchmark(config, service_factory=lambda name: object()).run(CUES)


def test_benchmark_metrics_use_real_translation_metrics_model():
    metrics = TranslationMetrics.for_text(
        provider="fake",
        model="m",
        source_language="en",
        target_language="es",
        source_text="hello world",
        translated_text="hola mundo",
        duration_ms=10,
        success=True,
    )
    assert metrics.characters_input == 11
    assert metrics.words_output == 2
