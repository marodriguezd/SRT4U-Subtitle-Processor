"""Offline analysis of TranslationBenchmark exports (stdlib core).

Pandas/Matplotlib are optional bridges used only by ``to_dataframe`` and the
``plot_*`` helpers; every statistic needed by the test-suite and by
``run_analysis`` is computed with the standard library so the analysis never
depends on the network or on heavy packages being importable.
"""

import csv
import json
import statistics
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from application.services.translation_benchmark import BENCHMARK_CSV_COLUMNS

#: Throughput metrics analyzed descriptively. Subtitle CPS is a different
#: metric and is intentionally absent from this list.
THROUGHPUT_METRICS: List[str] = [
    "duration_ms",
    "cues_per_second",
    "characters_per_second",
    "words_per_second",
    "latency_per_cue_ms",
    "latency_per_1k_chars_ms",
]

#: Columns that must hold numeric-or-null values after cleaning.
NUMERIC_COLUMNS: List[str] = [
    "number_of_cues",
    "characters_input",
    "characters_output",
    "words_input",
    "words_output",
    "duration_ms",
    "retry_count",
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "estimated_cost",
    "cues_per_second",
    "characters_per_second",
    "words_per_second",
    "latency_per_cue_ms",
    "latency_per_1k_chars_ms",
]

MIN_RUNS_PER_PROVIDER = 3


def _to_bool(value: Any) -> Optional[bool]:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    return None


def _to_number(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number


def _to_int(value: Any) -> Optional[int]:
    number = _to_number(value)
    if number is None:
        return None
    return int(number)


def load_report(path: str) -> Dict[str, Any]:
    """Load a benchmark JSON export produced by ``BenchmarkReport.to_json``."""
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict) or not isinstance(payload.get("runs"), list):
        raise ValueError(f"not a benchmark report: {path}")
    return payload


def load_runs_csv(path: str) -> List[Dict[str, Any]]:
    """Load a benchmark CSV export; one dict per execution row."""
    with open(path, "r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    cleaned, _ = clean_runs(rows)
    return cleaned


def clean_runs(
    rows: Sequence[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Coerce types without silently dropping problematic data.

    Failed executions are kept (they are data). A row is dropped only when it
    is not a mapping at all; every other anomaly is normalized to ``None``
    and described in the returned notes.
    """
    notes: List[str] = []
    cleaned: List[Dict[str, Any]] = []
    dropped = 0
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            dropped += 1
            continue
        item: Dict[str, Any] = dict(row)
        for column in NUMERIC_COLUMNS:
            if column in item:
                item[column] = _to_number(item.get(column))
                if item[column] is not None and column in {
                    "number_of_cues",
                    "characters_input",
                    "characters_output",
                    "words_input",
                    "words_output",
                    "duration_ms",
                    "retry_count",
                    "input_tokens",
                    "output_tokens",
                    "total_tokens",
                }:
                    item[column] = int(item[column])
        for column in ("success", "fallback_used"):
            if column in item:
                item[column] = _to_bool(item.get(column))
        providers_used = item.get("providers_used")
        if isinstance(providers_used, str):
            try:
                parsed = json.loads(providers_used)
                item["providers_used"] = parsed if isinstance(parsed, list) else []
            except (json.JSONDecodeError, TypeError):
                item["providers_used"] = []
                notes.append(f"row {index}: unparsable providers_used kept as []")
        item.setdefault("requested_provider", item.get("provider"))
        cleaned.append(item)
    if dropped:
        notes.append(f"dropped {dropped} non-mapping rows")
    notes.append(f"cleaned {len(cleaned)} rows; failures preserved as data")
    return cleaned, notes


def _values(rows: Sequence[Dict[str, Any]], metric: str) -> List[float]:
    values: List[float] = []
    for row in rows:
        value = _to_number(row.get(metric))
        if value is not None:
            values.append(value)
    return values


def _percentile(sorted_values: Sequence[float], percent: float) -> Optional[float]:
    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = (len(sorted_values) - 1) * (percent / 100.0)
    low = int(rank)
    high = min(low + 1, len(sorted_values) - 1)
    fraction = rank - low
    return sorted_values[low] + (sorted_values[high] - sorted_values[low]) * fraction


def _stats(values: Sequence[float]) -> Dict[str, Optional[float]]:
    ordered = sorted(values)
    count = len(ordered)
    mean = statistics.fmean(ordered) if ordered else None
    stdev = statistics.stdev(ordered) if count >= 2 else None
    quartiles: List[float] = []
    try:
        quartiles = list(statistics.quantiles(ordered, n=4)) if count >= 2 else []
    except statistics.StatisticsError:
        quartiles = []
    iqr = (quartiles[2] - quartiles[0]) if len(quartiles) == 3 else None
    return {
        "count": count,
        "mean": mean,
        "median": statistics.median(ordered) if ordered else None,
        "min": ordered[0] if ordered else None,
        "max": ordered[-1] if ordered else None,
        "stdev": stdev,
        "p10": _percentile(ordered, 10),
        "p25": _percentile(ordered, 25),
        "p75": _percentile(ordered, 75),
        "p90": _percentile(ordered, 90),
        "iqr": iqr,
        "cv": (stdev / mean) if stdev is not None and mean else None,
    }


def _group_key(row: Dict[str, Any], group_by: Sequence[str]) -> str:
    return "|".join(
        "" if row.get(key) is None else str(row.get(key)) for key in group_by
    )


def describe(
    rows: Sequence[Dict[str, Any]],
    group_by: Sequence[str] = ("requested_provider",),
    successful_only: bool = True,
) -> List[Dict[str, Any]]:
    """Descriptive stats per group over successful executions with duration.

    ``successful_only=False`` includes failed rows in counts but numeric stats
    still use rows where each metric is present.
    """
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(_group_key(row, group_by), []).append(row)
    summary: List[Dict[str, Any]] = []
    for key in sorted(groups):
        members = groups[key]
        usable = [
            row
            for row in members
            if (row.get("success") is True)
            and _to_number(row.get("duration_ms")) is not None
        ]
        entry: Dict[str, Any] = {
            "group": key,
            "n_total": len(members),
            "n_success": sum(1 for row in members if row.get("success") is True),
            "n_failed": sum(1 for row in members if row.get("success") is False),
        }
        criticized = usable if successful_only else members
        for metric in THROUGHPUT_METRICS:
            for stat, value in _stats(_values(criticized, metric)).items():
                entry[f"{metric}.{stat}"] = value
        summary.append(entry)
    return summary


def error_summary(
    rows: Sequence[Dict[str, Any]],
    group_by: Sequence[str] = ("requested_provider",),
) -> List[Dict[str, Any]]:
    """Success/failure rates, error types, retries and fallback per group."""
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(_group_key(row, group_by), []).append(row)
    summary: List[Dict[str, Any]] = []
    for key in sorted(groups):
        members = groups[key]
        total = len(members)
        failed = [row for row in members if row.get("success") is False]
        error_types: Dict[str, int] = {}
        fallback_errors: Dict[str, int] = {}
        for row in failed:
            if row.get("error_type"):
                error_types[str(row["error_type"])] = (
                    error_types.get(str(row["error_type"]), 0) + 1
                )
            if row.get("fallback_error_type"):
                fallback_errors[str(row["fallback_error_type"])] = (
                    fallback_errors.get(str(row["fallback_error_type"]), 0) + 1
                )
        retries = _values(members, "retry_count")
        summary.append(
            {
                "group": key,
                "n_total": total,
                "success_rate": (total - len(failed)) / total if total else None,
                "failure_rate": len(failed) / total if total else None,
                "error_types": error_types,
                "fallback_error_types": fallback_errors,
                "retry_mean": statistics.fmean(retries) if retries else None,
                "retry_max": max(retries) if retries else None,
                "fallback_used_count": sum(
                    1 for row in members if row.get("fallback_used") is True
                ),
                "fallback_rate": sum(
                    1 for row in members if row.get("fallback_used") is True
                )
                / total
                if total
                else None,
            }
        )
    return summary


def _pearson(xs: Sequence[float], ys: Sequence[float]) -> Optional[float]:
    if len(xs) != len(ys) or len(xs) < 2:
        return None
    mean_x = statistics.fmean(xs)
    mean_y = statistics.fmean(ys)
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
    denominator = (
        sum((x - mean_x) ** 2 for x in xs) * sum((y - mean_y) ** 2 for y in ys)
    ) ** 0.5
    if not denominator:
        return None
    return numerator / denominator


def size_relationship(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Pearson correlation between input size and time/throughput (successes)."""
    usable = [
        row
        for row in rows
        if row.get("success") is True and _to_number(row.get("duration_ms")) is not None
    ]
    pairs = {
        "chars_in_vs_duration": ("characters_input", "duration_ms"),
        "words_in_vs_duration": ("words_input", "duration_ms"),
        "cues_vs_duration": ("number_of_cues", "duration_ms"),
        "chars_in_vs_latency_per_cue": ("characters_input", "latency_per_cue_ms"),
        "chars_in_vs_chars_per_second": ("characters_input", "characters_per_second"),
    }
    correlations: Dict[str, Optional[float]] = {}
    for name, (left, right) in pairs.items():
        xs = _values(usable, left)
        ys = _values(usable, right)
        correlations[name] = _pearson(xs, ys)
    return {"n_successful": len(usable), "pearson": correlations}


def validate_runs(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Structural validation: columns, nulls, types, failures, impossible data."""
    rows = list(rows)
    null_counts: Dict[str, int] = {}
    for row in rows:
        for column in BENCHMARK_CSV_COLUMNS:
            if row.get(column) is None or row.get(column) == "":
                null_counts[column] = null_counts.get(column, 0) + 1
    impossible: List[str] = []
    for index, row in enumerate(rows):
        for column in (
            "duration_ms",
            "characters_input",
            "words_input",
            "number_of_cues",
        ):
            value = _to_number(row.get(column))
            if value is not None and value < 0:
                impossible.append(f"row {index}: negative {column}")
        if row.get("success") is True and row.get("error_type"):
            impossible.append(f"row {index}: success with error_type set")
    providers: Dict[str, int] = {}
    models: Dict[str, int] = {}
    for row in rows:
        providers[str(row.get("requested_provider"))] = (
            providers.get(str(row.get("requested_provider")), 0) + 1
        )
        models[str(row.get("model"))] = models.get(str(row.get("model")), 0) + 1
    run_gaps: Dict[str, List[int]] = {}
    for row in rows:
        key = str(row.get("requested_provider"))
        index = _to_int(row.get("run_index"))
        if index is not None:
            run_gaps.setdefault(key, []).append(index)
    incomplete = {
        provider: sorted(indices)
        for provider, indices in run_gaps.items()
        if sorted(indices) != list(range(max(indices) + 1)) and indices
    }
    return {
        "row_count": len(rows),
        "null_counts": null_counts,
        "failed_runs": sum(1 for row in rows if row.get("success") is False),
        "fallback_runs": sum(1 for row in rows if row.get("fallback_used") is True),
        "providers": providers,
        "models": models,
        "impossible_values": impossible,
        "incomplete_run_sequences": incomplete,
    }


def data_quality(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Explicit data-quality findings with counts; nothing is hidden."""
    rows = list(rows)
    findings: List[Dict[str, Any]] = []
    by_provider: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        by_provider.setdefault(str(row.get("requested_provider")), []).append(row)

    def add(check: str, count: int, detail: str) -> None:
        findings.append({"check": check, "count": count, "detail": detail})

    add(
        "fallback_runs",
        sum(1 for row in rows if row.get("fallback_used") is True),
        "executions whose effective provider differs from the requested one",
    )
    add(
        "missing_tokens",
        sum(1 for row in rows if row.get("total_tokens") is None),
        "providers/endpoints that do not report usage",
    )
    add(
        "null_estimated_cost",
        sum(1 for row in rows if row.get("estimated_cost") is None),
        "no reliable tariff available for any provider in this phase",
    )
    add(
        "missing_model",
        sum(1 for row in rows if not row.get("model")),
        "providers without a model identifier (e.g. Google/DeepL here)",
    )
    add(
        "missing_duration",
        sum(
            1
            for row in rows
            if row.get("success") is True and _to_number(row.get("duration_ms")) is None
        ),
        "successful runs without measurable duration",
    )
    small = sorted(
        provider
        for provider, members in by_provider.items()
        if len(members) < MIN_RUNS_PER_PROVIDER
    )
    add(
        "small_samples",
        len(small),
        f"providers with fewer than {MIN_RUNS_PER_PROVIDER} runs: {small or 'none'}",
    )
    impossible = validate_runs(rows)["impossible_values"]
    add("impossible_values", len(impossible), "; ".join(impossible) or "none found")
    return findings


def to_dataframe(rows: Sequence[Dict[str, Any]]):
    """Return a pandas DataFrame; requires pandas in the analysis env."""
    try:
        import pandas as pd
    except ImportError as exc:
        raise ImportError(
            "pandas is required for to_dataframe; install it in the analysis "
            "environment (it is not a runtime dependency of SRT4U)"
        ) from exc
    return pd.DataFrame(list(rows))


def export_summary_csv(path: str, summary: Sequence[Dict[str, Any]]) -> None:
    rows = list(summary)
    if not rows:
        raise ValueError("nothing to export")
    fieldnames = list(rows[0].keys())
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: (
                        json.dumps(value, ensure_ascii=False, sort_keys=True)
                        if isinstance(value, (dict, list))
                        else value
                    )
                    for key, value in row.items()
                }
            )


def save_cleaned_csv(path: str, rows: Sequence[Dict[str, Any]]) -> None:
    rows = list(rows)
    if not rows:
        raise ValueError("nothing to export")
    fieldnames = list(BENCHMARK_CSV_COLUMNS) + [
        key for key in rows[0] if key not in BENCHMARK_CSV_COLUMNS
    ]
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: (
                        json.dumps(value, ensure_ascii=False, sort_keys=True)
                        if isinstance(value, (dict, list))
                        else value
                    )
                    for key, value in row.items()
                }
            )


def _figure(title: str, xlabel: str, ylabel: str):
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise ImportError(
            "matplotlib is required for plots; install it in the analysis "
            "environment (it is not a runtime dependency of SRT4U)"
        ) from exc
    figure, axis = plt.subplots()
    axis.set_title(title)
    axis.set_xlabel(xlabel)
    axis.set_ylabel(ylabel)
    return figure, axis


def plot_latency_distribution(rows: Sequence[Dict[str, Any]], out_path: str) -> str:
    values = _values(
        [row for row in rows if row.get("success") is True], "latency_per_cue_ms"
    )
    figure, axis = _figure(
        "Latency per cue distribution (successful runs)",
        "latency_per_cue_ms",
        "executions",
    )
    if values:
        axis.hist(values, bins=min(20, max(5, len(values))))
    else:
        axis.text(0.5, 0.5, "no successful runs", ha="center")
    figure.tight_layout()
    figure.savefig(out_path)
    return out_path


def plot_latency_boxplot(rows: Sequence[Dict[str, Any]], out_path: str) -> str:
    groups: Dict[str, List[float]] = {}
    for row in rows:
        if row.get("success") is True:
            value = _to_number(row.get("latency_per_cue_ms"))
            if value is not None:
                groups.setdefault(str(row.get("requested_provider")), []).append(value)
    figure, axis = _figure(
        "Latency per cue by provider", "requested_provider", "latency_per_cue_ms"
    )
    if groups:
        labels = sorted(groups)
        axis.boxplot([groups[label] for label in labels], tick_labels=labels)
    else:
        axis.text(0.5, 0.5, "no successful runs", ha="center")
    figure.tight_layout()
    figure.savefig(out_path)
    return out_path


def plot_throughput_bars(rows: Sequence[Dict[str, Any]], out_path: str) -> str:
    summary = describe(rows)
    labels = [entry["group"] for entry in summary]
    medians = [entry.get("characters_per_second.median") or 0 for entry in summary]
    figure, axis = _figure(
        "Median throughput by provider",
        "requested_provider",
        "characters_per_second (median)",
    )
    if labels:
        axis.bar(labels, medians)
    figure.tight_layout()
    figure.savefig(out_path)
    return out_path


def plot_runs_variability(rows: Sequence[Dict[str, Any]], out_path: str) -> str:
    groups: Dict[str, Dict[int, List[float]]] = {}
    for row in rows:
        if row.get("success") is True:
            value = _to_number(row.get("latency_per_cue_ms"))
            index = _to_int(row.get("run_index"))
            if value is not None and index is not None:
                provider = str(row.get("requested_provider"))
                groups.setdefault(provider, {}).setdefault(index, []).append(value)
    figure, axis = _figure(
        "Latency per cue across runs", "run_index", "latency_per_cue_ms"
    )
    for provider in sorted(groups):
        points = sorted(groups[provider])
        axis.plot(
            points,
            [statistics.fmean(groups[provider][index]) for index in points],
            marker="o",
            label=provider,
        )
    axis.legend()
    figure.tight_layout()
    figure.savefig(out_path)
    return out_path


def plot_errors_by_provider(rows: Sequence[Dict[str, Any]], out_path: str) -> str:
    summary = error_summary(rows)
    labels = [entry["group"] for entry in summary]
    failures = [1 - (entry.get("success_rate") or 0) for entry in summary]
    figure, axis = _figure("Failure rate by provider", "requested_provider", "rate")
    if labels:
        axis.bar(labels, failures)
        axis.set_ylim(0, 1)
    figure.tight_layout()
    figure.savefig(out_path)
    return out_path


def plot_latency_vs_size(
    rows: Sequence[Dict[str, Any]], out_path: str, size_metric: str = "characters_input"
) -> str:
    usable = [
        row
        for row in rows
        if row.get("success") is True
        and _to_number(row.get(size_metric)) is not None
        and _to_number(row.get("duration_ms")) is not None
    ]
    figure, axis = _figure(
        f"Duration vs {size_metric}",
        size_metric,
        "duration_ms",
    )
    for row in usable:
        axis.scatter(row[size_metric], row["duration_ms"])
    figure.tight_layout()
    figure.savefig(out_path)
    return out_path


def run_analysis(
    report: Dict[str, Any], out_dir: str, include_plots: bool = True
) -> Dict[str, Any]:
    """Full pipeline: validate → describe → export CSV/JSON (+ PNG plots).

    Never overwrites the source dataset; every artifact lands in ``out_dir``.
    """
    runs, notes = clean_runs(report.get("runs", []))
    validation = validate_runs(runs)
    descriptive = describe(runs)
    errors = error_summary(runs)
    sizes = size_relationship(runs)
    quality = data_quality(runs)
    conclusions = _conclusions(report, descriptive, errors, quality)
    payload = {
        "benchmark_id": report.get("benchmark_id"),
        "timestamp": report.get("timestamp"),
        "dataset_version": report.get("dataset_version"),
        "dataset_size": report.get("dataset_size"),
        "config": report.get("config", {}),
        "environment": report.get("environment", {}),
        "validation": validation,
        "cleaning_notes": notes,
        "descriptive_by_provider": descriptive,
        "errors_by_provider": errors,
        "size_relationship": sizes,
        "data_quality": quality,
        "conclusions": conclusions,
    }
    destination = Path(out_dir).expanduser()
    destination.mkdir(parents=True, exist_ok=True)
    export_summary_csv(str(destination / "summary.csv"), descriptive)
    save_cleaned_csv(str(destination / "cleaned_dataset.csv"), runs)
    with open(destination / "analysis_report.json", "w", encoding="utf-8") as handle:
        handle.write(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        )
    plots: Dict[str, str] = {}
    if include_plots:
        plots_dir = destination / "plots"
        plots_dir.mkdir(parents=True, exist_ok=True)
        plots = {
            "latency_distribution": plot_latency_distribution(
                runs, str(plots_dir / "latency_distribution.png")
            ),
            "latency_boxplot": plot_latency_boxplot(
                runs, str(plots_dir / "latency_boxplot.png")
            ),
            "throughput_bars": plot_throughput_bars(
                runs, str(plots_dir / "throughput_bars.png")
            ),
            "runs_variability": plot_runs_variability(
                runs, str(plots_dir / "runs_variability.png")
            ),
            "errors_by_provider": plot_errors_by_provider(
                runs, str(plots_dir / "errors_by_provider.png")
            ),
            "latency_vs_characters": plot_latency_vs_size(
                runs,
                str(plots_dir / "latency_vs_characters.png"),
                size_metric="characters_input",
            ),
            "latency_vs_cues": plot_latency_vs_size(
                runs,
                str(plots_dir / "latency_vs_cues.png"),
                size_metric="number_of_cues",
            ),
        }
    payload["plots"] = plots
    with open(destination / "analysis_report.json", "w", encoding="utf-8") as handle:
        handle.write(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        )
    return payload


def _conclusions(
    report: Dict[str, Any],
    descriptive: Sequence[Dict[str, Any]],
    errors: Sequence[Dict[str, Any]],
    quality: Sequence[Dict[str, Any]],
) -> List[str]:
    """Data-bound observations; never a global winner."""
    config = report.get("config", {}) or {}
    context = (
        f"(dataset v{report.get('dataset_version')}, "
        f"{report.get('dataset_size')} cues, "
        f"{config.get('runs')} runs, "
        f"{config.get('source_language')}→{config.get('target_language')})"
    )
    lines: List[str] = []
    medians = [
        (entry["group"], entry.get("latency_per_cue_ms.median"))
        for entry in descriptive
        if entry.get("latency_per_cue_ms.median") is not None
    ]
    if medians:
        best = min(medians, key=lambda item: item[1] or float("inf"))
        lines.append(
            f"Provider '{best[0]}' showed the lowest median latency per cue "
            f"({best[1]:.2f} ms) {context}."
        )
    spreads = [
        (entry["group"], entry.get("latency_per_cue_ms.stdev"))
        for entry in descriptive
        if entry.get("latency_per_cue_ms.stdev") is not None
    ]
    if spreads:
        widest = max(spreads, key=lambda item: item[1] or 0)
        lines.append(
            f"Provider '{widest[0]}' showed the highest variability "
            f"(stdev {widest[1]:.2f} ms) {context}."
        )
    for entry in errors:
        rate = entry.get("failure_rate")
        fallback = entry.get("fallback_rate")
        if rate:
            lines.append(
                f"Provider '{entry['group']}' failed {rate * 100:.1f}% of executions "
                f"{context}."
            )
        if fallback:
            lines.append(
                f"{fallback * 100:.1f}% of '{entry['group']}' executions used "
                f"fallback {context}."
            )
    for finding in quality:
        if (
            finding["check"] in {"null_estimated_cost", "missing_tokens"}
            and finding["count"]
        ):
            lines.append(
                f"Data gap: {finding['count']} executions {finding['detail']}."
            )
    if not lines:
        lines.append(f"No conclusive observations {context}.")
    return lines


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI: ``python -m analysis.benchmark_analysis REPORT_JSON --out DIR``."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Analyze a TranslationBenchmark JSON export."
    )
    parser.add_argument("report", help="benchmark JSON file")
    parser.add_argument("--out", default="reports/benchmark", help="output directory")
    parser.add_argument(
        "--no-plots", action="store_true", help="skip PNG plot generation"
    )
    args = parser.parse_args(argv)
    try:
        report = load_report(args.report)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 2
    payload = run_analysis(report, args.out, include_plots=not args.no_plots)
    print(
        f"Analyzed {payload['validation']['row_count']} executions; "
        f"artifacts in {args.out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
