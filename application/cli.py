"""Headless command-line interface for SRT4U subtitle processing."""

import argparse
import csv
import io
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .services.history_store import record_result_safely, record_safely
from .services.subtitle_service import SubtitleService

SUPPORTED_EXTENSIONS = {".srt", ".vtt", ".ass", ".ssa", ".txt"}
PIPELINE_OPTIONS = {
    "clean",
    "translate",
    "source_language",
    "target_language",
    "engine",
    "target_format",
    "convert_to",
    "parallel",
}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="srt4u",
        description="Procesa y analiza subtítulos sin iniciar la interfaz de escritorio.",
    )
    parser.add_argument("--version", action="version", version="1.4.9")
    subparsers = parser.add_subparsers(dest="command", required=True)
    process = subparsers.add_parser(
        "process", help="limpia, traduce o convierte uno o varios archivos"
    )
    process.add_argument(
        "input", nargs="+", help="archivo(s) o directorio(s) de entrada"
    )
    process.add_argument(
        "-o",
        "--output",
        help="archivo de salida o directorio para procesamiento por lote",
    )
    process.add_argument(
        "--config", help="preset de pipeline declarativo en formato JSON"
    )
    process.add_argument(
        "--clean",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="limpia las líneas promocionales (usar --no-clean para desactivarlo)",
    )
    process.add_argument(
        "--translate",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="traduce los subtítulos (usar --no-translate para desactivarlo)",
    )
    process.add_argument(
        "--source", dest="source_language", help="idioma de origen (por defecto: auto)"
    )
    process.add_argument(
        "--target",
        dest="target_language",
        help="idioma de destino; obligatorio al traducir",
    )
    process.add_argument(
        "--engine",
        choices=("google", "deepl", "openai", "ollama", "llm"),
        help="motor configurado en SRT4U (Ollama/OpenRouter usan el endpoint compatible OpenAI)",
    )
    process.add_argument(
        "--format",
        dest="target_format",
        choices=("srt", "vtt", "ass", "ssa", "txt"),
        help="formato de salida; por defecto conserva el formato de cada entrada",
    )
    process.add_argument(
        "--sequential",
        action="store_true",
        default=None,
        help="desactiva la traducción paralela",
    )
    process.add_argument(
        "--stats",
        action="store_true",
        help="muestra métricas de traducción al final sin cambiar la salida predeterminada",
    )
    process.add_argument(
        "--stats-json",
        action="store_true",
        help="emite las métricas de traducción como JSON sin cambiar la salida predeterminada",
    )
    process.add_argument(
        "--db",
        default=None,
        help="ruta de la base de historial (por defecto: historial del usuario)",
    )
    process.add_argument(
        "--no-history",
        action="store_true",
        help="no registra esta ejecución en el historial local",
    )

    for command, help_text in (
        ("analyze", "calcula métricas de contenido, tiempo y calidad"),
        ("qa", "valida reglas deterministas de calidad de subtítulos"),
    ):
        analysis = subparsers.add_parser(command, help=help_text)
        analysis.add_argument("input", help="archivo de subtítulos")
        analysis.add_argument(
            "--json", action="store_true", help="emite JSON válido en stdout"
        )
        analysis.add_argument(
            "--csv", action="store_true", help="emite CSV (equivalente a --format csv)"
        )
        if command == "qa":
            analysis.add_argument(
                "--strict",
                action="store_true",
                help="devuelve código 1 si hay errores o advertencias",
            )
        analysis.add_argument("-o", "--output", help="guarda el informe en un archivo")
        analysis.add_argument(
            "--format", choices=("json", "csv"), help="formato de exportación"
        )

    benchmark = subparsers.add_parser(
        "benchmark", help="compara providers sobre un dataset fijo de subtítulos"
    )
    benchmark.add_argument(
        "dataset",
        nargs="?",
        default=None,
        help="archivo o directorio del dataset (por defecto: dataset interno versionado)",
    )
    benchmark.add_argument(
        "--providers",
        default="google",
        help="providers separados por coma (p. ej. google,deepl,ollama)",
    )
    benchmark.add_argument(
        "--source", dest="source_language", default="en", help="idioma de origen"
    )
    benchmark.add_argument(
        "--target", dest="target_language", default="es", help="idioma de destino"
    )
    benchmark.add_argument(
        "--runs", type=int, default=1, help="repeticiones por provider (por defecto: 1)"
    )
    benchmark.add_argument(
        "--output", help="guarda el informe JSON en un archivo (stdout si se omite)"
    )
    benchmark.add_argument("--output-csv", help="guarda las ejecuciones en CSV")
    benchmark.add_argument(
        "--include-texts",
        action="store_true",
        help="conserva textos de entrada/salida en el informe",
    )
    benchmark.add_argument(
        "--max-retries",
        type=int,
        default=0,
        help="reintentos ante errores transitorios (por defecto: 0)",
    )
    benchmark.add_argument(
        "--no-fallback",
        action="store_true",
        help="desactiva el fallback entre providers",
    )
    benchmark.add_argument(
        "--store",
        action="store_true",
        help="guarda los resultados en el historial local SQLite",
    )
    benchmark.add_argument(
        "--db",
        default=None,
        help="ruta de la base de historial (por defecto: historial del usuario)",
    )

    history = subparsers.add_parser(
        "history", help="consulta el historial local de ejecuciones"
    )
    history.add_argument("--provider", default=None, help="filtra por provider")
    history.add_argument(
        "--operation",
        default=None,
        choices=("process", "analyze", "qa", "benchmark", "transcription", "pipeline"),
        help="filtra por tipo de operación",
    )
    history.add_argument(
        "--limit", type=int, default=20, help="número máximo de filas (por defecto: 20)"
    )
    history.add_argument(
        "--errors-only", action="store_true", help="solo ejecuciones fallidas"
    )
    history.add_argument(
        "--fallback-only", action="store_true", help="solo ejecuciones con fallback"
    )
    history.add_argument(
        "--json", action="store_true", help="emite JSON válido en stdout"
    )
    history.add_argument(
        "--stats", action="store_true", help="muestra agregados en lugar de filas"
    )
    history.add_argument(
        "--db",
        default=None,
        help="ruta de la base de historial (por defecto: historial del usuario)",
    )

    transcribe = subparsers.add_parser(
        "transcribe", help="transcribe audio/vídeo a subtítulos (Whisper local)"
    )
    transcribe.add_argument("input", help="archivo de audio o vídeo")
    transcribe.add_argument(
        "-o",
        "--output",
        help="archivo de salida (.srt/.vtt; por defecto: *_transcribed)",
    )
    transcribe.add_argument(
        "--model",
        default="small",
        choices=("tiny", "base", "small", "medium", "large-v3", "turbo"),
        help="modelo Whisper (por defecto: small)",
    )
    transcribe.add_argument(
        "--language",
        default="auto",
        help="idioma (código) o auto para detección (por defecto: auto)",
    )
    transcribe.add_argument(
        "--format",
        dest="target_format",
        default="srt",
        choices=("srt", "vtt"),
        help="formato de subtítulos (por defecto: srt)",
    )
    transcribe.add_argument(
        "--device",
        default="auto",
        choices=("auto", "cpu", "cuda"),
        help="dispositivo de inferencia (por defecto: auto)",
    )
    transcribe.add_argument(
        "--db",
        default=None,
        help="ruta de la base de historial (por defecto: historial del usuario)",
    )
    transcribe.add_argument(
        "--no-history",
        action="store_true",
        help="no registra esta ejecución en el historial local",
    )
    transcribe.add_argument(
        "--stats-json",
        action="store_true",
        help="emite las métricas de transcripción como JSON",
    )

    pipeline = subparsers.add_parser(
        "pipeline",
        help="pipeline audiovisual: transcribe/limpia/QA/traduce/exporta/burn-in",
    )
    pipeline.add_argument("input", help="audio, vídeo o subtítulo de entrada")
    pipeline.add_argument(
        "-o", "--output", help="subtítulo de salida (por defecto: *_pipeline.srt/vtt)"
    )
    pipeline.add_argument(
        "--transcribe",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="transcribe la entrada multimedia (por defecto: auto según entrada)",
    )
    pipeline.add_argument(
        "--model",
        default="small",
        choices=("tiny", "base", "small", "medium", "large-v3", "turbo"),
        help="modelo Whisper (por defecto: small)",
    )
    pipeline.add_argument(
        "--language",
        default="auto",
        help="idioma de transcripción o auto (por defecto: auto)",
    )
    pipeline.add_argument(
        "--device",
        default="auto",
        choices=("auto", "cpu", "cuda"),
        help="dispositivo de inferencia (por defecto: auto)",
    )
    pipeline.add_argument(
        "--clean",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="limpieza (usar --no-clean para desactivarla)",
    )
    pipeline.add_argument(
        "--qa",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="QA determinista (usar --no-qa para omitirlo)",
    )
    pipeline.add_argument(
        "--strict",
        action="store_true",
        help="el QA estricto detiene la pipeline ante errores o avisos",
    )
    pipeline.add_argument(
        "--translate",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="traducción (usar --no-translate para desactivarla)",
    )
    pipeline.add_argument(
        "--source", dest="source_language", default="auto", help="idioma de origen"
    )
    pipeline.add_argument(
        "--target", dest="target_language", help="idioma de destino al traducir"
    )
    pipeline.add_argument(
        "--provider",
        default="google",
        choices=("google", "deepl", "openai", "ollama", "llm"),
        help="provider de traducción (por defecto: google)",
    )
    pipeline.add_argument(
        "--max-retries",
        type=int,
        default=0,
        help="reintentos ante errores transitorios (por defecto: 0)",
    )
    pipeline.add_argument(
        "--no-fallback",
        action="store_true",
        help="desactiva el fallback entre providers",
    )
    pipeline.add_argument(
        "--format",
        dest="target_format",
        default="srt",
        choices=("srt", "vtt"),
        help="formato de subtítulos (por defecto: srt)",
    )
    pipeline.add_argument(
        "--burn-in",
        action="store_true",
        help="burn-in del subtítulo final en el vídeo (requiere --video-output)",
    )
    pipeline.add_argument("--video-output", help="vídeo de salida con subtítulos")
    pipeline.add_argument(
        "--db",
        default=None,
        help="ruta de la base de historial (por defecto: historial del usuario)",
    )
    pipeline.add_argument(
        "--no-history",
        action="store_true",
        help="no registra esta ejecución en el historial local",
    )
    pipeline.add_argument(
        "--stats-json",
        action="store_true",
        help="emite el resultado estructurado como JSON",
    )

    serve = subparsers.add_parser("serve", help="inicia la API REST local (FastAPI)")
    serve.add_argument(
        "--host",
        default="127.0.0.1",
        help="interfaz de escucha (por defecto: 127.0.0.1, solo local)",
    )
    serve.add_argument(
        "--port", type=int, default=8000, help="puerto de escucha (por defecto: 8000)"
    )
    return parser


def _load_pipeline(config_path: Optional[str]) -> Dict[str, Any]:
    if not config_path:
        return {}
    try:
        with open(config_path, "r", encoding="utf-8") as config_file:
            document = json.load(config_file)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"no se pudo leer el preset JSON ({type(exc).__name__})"
        ) from exc
    if not isinstance(document, dict):
        raise ValueError("el preset debe ser un objeto JSON")
    pipeline = document.get("pipeline", document)
    if not isinstance(pipeline, dict):
        raise ValueError("la propiedad 'pipeline' debe ser un objeto JSON")
    unknown = set(pipeline) - PIPELINE_OPTIONS
    if unknown:
        raise ValueError(
            f"opciones desconocidas en el preset: {', '.join(sorted(unknown))}"
        )
    normalized = dict(pipeline)
    if "convert_to" in normalized:
        if "target_format" in normalized:
            raise ValueError("usa 'convert_to' o 'target_format', no ambos")
        normalized["target_format"] = normalized.pop("convert_to")
    for key in ("clean", "translate", "parallel"):
        if key in normalized and not isinstance(normalized[key], bool):
            raise ValueError(f"'{key}' debe ser true o false")
    return normalized


def _resolve_options(
    args: argparse.Namespace, parser: argparse.ArgumentParser
) -> Dict[str, Any]:
    try:
        options = _load_pipeline(args.config)
    except ValueError as exc:
        parser.error(str(exc))
    cli_options = {
        "clean": args.clean,
        "translate": args.translate,
        "source_language": args.source_language,
        "target_language": args.target_language,
        "engine": args.engine,
        "target_format": args.target_format,
    }
    for key, value in cli_options.items():
        if value is not None:
            options[key] = value
    if args.sequential:
        options["parallel"] = False
    options.setdefault("clean", False)
    options.setdefault("translate", False)
    options.setdefault("source_language", "auto")
    options.setdefault("engine", "google")
    options.setdefault("parallel", True)
    if options.get("translate") and not options.get("target_language"):
        parser.error("--target es obligatorio cuando se activa --translate")
    if options.get("target_format") not in (None, "srt", "vtt", "ass", "ssa", "txt"):
        parser.error("el preset contiene un formato de salida no soportado")
    if not isinstance(options["engine"], str) or options["engine"] not in {
        "google",
        "deepl",
        "openai",
        "ollama",
        "llm",
    }:
        parser.error("el preset contiene un motor de traducción no soportado")
    if not isinstance(options["parallel"], bool):
        parser.error("'parallel' debe ser true o false")
    if not isinstance(options["source_language"], str):
        parser.error("'source_language' debe ser un código de idioma")
    if options.get("target_language") is not None and not isinstance(
        options["target_language"], str
    ):
        parser.error("'target_language' debe ser un código de idioma")
    return options


def _paths_refer_to_same_file(first: Path, second: Path) -> bool:
    if first.resolve() == second.resolve():
        return True
    try:
        return first.samefile(second)
    except OSError:
        return False


def _collect_inputs(
    input_values: Iterable[str], output_directory: Optional[Path]
) -> Tuple[List[Path], Dict[Path, Path]]:
    """Collect supported files and their relative output paths before writing anything."""
    sources: List[Path] = []
    relative_paths: Dict[Path, Path] = {}
    output_root = output_directory.resolve() if output_directory else None
    for value in input_values:
        path = Path(value).expanduser().resolve()
        if path.is_file():
            candidates = [(path, Path(path.name))]
        elif path.is_dir():
            candidates = []
            for candidate in sorted(path.rglob("*")):
                resolved = candidate.resolve()
                if output_root and (
                    resolved == output_root or output_root in resolved.parents
                ):
                    continue
                if (
                    candidate.is_file()
                    and candidate.suffix.lower() in SUPPORTED_EXTENSIONS
                ):
                    candidates.append((resolved, candidate.relative_to(path)))
        else:
            raise ValueError(f"no existe la entrada: {path}")
        for source, relative in candidates:
            if source.suffix.lower() not in SUPPORTED_EXTENSIONS:
                raise ValueError(f"formato de entrada no soportado: {source}")
            if source not in relative_paths:
                sources.append(source)
                relative_paths[source] = relative
    if not sources:
        raise ValueError("no se encontraron archivos de subtítulos compatibles")
    destinations = list(relative_paths.values())
    if len(destinations) != len(set(destinations)):
        raise ValueError("hay archivos de entrada con la misma ruta relativa de salida")
    return sources, relative_paths


def _format_for(
    source: Path, options: Dict[str, Any], output_file: Optional[Path]
) -> str:
    selected = options.get("target_format")
    if selected:
        return selected
    if output_file and output_file.suffix:
        output_suffix = output_file.suffix.lower().lstrip(".")
        if output_suffix in {"srt", "vtt", "ass", "ssa", "txt"}:
            return output_suffix
    return (
        "ass" if source.suffix.lower() == ".ssa" else source.suffix.lower().lstrip(".")
    )


def _process(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    options = _resolve_options(args, parser)
    input_paths = [Path(value).expanduser().resolve() for value in args.input]
    has_directory = any(path.is_dir() for path in input_paths)
    batch_mode = has_directory or len(input_paths) > 1
    output_argument = Path(args.output).expanduser() if args.output else None
    if batch_mode:
        if output_argument:
            output_directory = output_argument.resolve()
        elif len(input_paths) == 1 and input_paths[0].is_dir():
            output_directory = (
                input_paths[0].parent / f"{input_paths[0].name}_processed"
            )
        else:
            output_directory = Path.cwd() / "srt4u-output"
        output_file = None
    else:
        output_directory = None
        output_file = output_argument.resolve() if output_argument else None
    try:
        sources, relative_paths = _collect_inputs(args.input, output_directory)
    except ValueError as exc:
        parser.error(str(exc))
    if output_file and any(
        _paths_refer_to_same_file(output_file, source) for source in sources
    ):
        parser.error("el archivo de salida no puede sobrescribir el archivo de entrada")
    if batch_mode:
        if output_directory.exists() and not output_directory.is_dir():
            parser.error("la salida de un lote debe ser un directorio")
        batch_destinations = []
        for source in sources:
            selected_format = _format_for(source, options, None)
            destination = output_directory / relative_paths[source]
            if options.get("target_format") or source.suffix.lower() == ".ssa":
                destination = destination.with_suffix(f".{selected_format}")
            if any(
                _paths_refer_to_same_file(destination, source_file)
                for source_file in sources
            ):
                parser.error("la salida no puede sobrescribir un archivo de entrada")
            batch_destinations.append(destination.resolve())
        if len(batch_destinations) != len(set(batch_destinations)) or any(
            _paths_refer_to_same_file(first, second)
            for index, first in enumerate(batch_destinations)
            for second in batch_destinations[index + 1 :]
        ):
            parser.error("varios archivos producirían la misma ruta de salida")

    service = SubtitleService()
    failed = 0
    translation_failures = 0
    for source in sources:
        if batch_mode:
            destination = output_directory / relative_paths[source]
            selected_format = _format_for(source, options, None)
            if options.get("target_format"):
                destination = destination.with_suffix(f".{selected_format}")
            elif source.suffix.lower() == ".ssa":
                destination = destination.with_suffix(".ass")
        else:
            selected_format = _format_for(source, options, output_file)
            destination = output_file or source.with_name(
                f"{source.stem}_processed.{selected_format}"
            )
        try:
            result = service.process_subtitles(
                file_path=str(source),
                do_clean=options["clean"],
                do_translate=options["translate"],
                target_language=options.get("target_language"),
                source_language=options["source_language"],
                # Single source of truth: pass the identifier through.
                # ProviderRegistry resolves ollama/llm/openai aliases.
                engine=options["engine"],
                target_format=selected_format,
                parallel=options["parallel"],
            )
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(result.output_content, encoding="utf-8")
            translation_failures += result.stats.translation_failures
            print(
                f"OK {source} -> {destination} "
                f"({result.stats.processed_items_count} cues, {result.stats.elapsed_time:.2f}s)"
            )
            if args.stats and result.translation_metrics is not None:
                metrics = result.translation_metrics
                print(
                    f"Provider: {metrics.provider} | Model: {metrics.model or 'unknown'} | "
                    f"Cues: {metrics.number_of_cues} | Duration: "
                    f"{metrics.duration_ms if metrics.duration_ms is not None else 'unknown'}ms | "
                    f"Retries: {metrics.retry_count} | Status: "
                    f"{'success' if metrics.success else metrics.error_type or 'failed'}"
                )
            if args.stats_json and result.translation_metrics is not None:
                print(
                    json.dumps(
                        result.translation_metrics.to_dict(),
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                )
            if result.stats.translation_failures:
                print(
                    f"AVISO: {result.stats.translation_failures} cues no se tradujeron",
                    file=sys.stderr,
                )
            if not args.no_history:
                record_result_safely(
                    result,
                    args.db,
                    operation="process",
                    file_path=str(source),
                    file_format=selected_format,
                    source_language=options["source_language"],
                    target_language=options.get("target_language"),
                    engine=options["engine"],
                )
        except Exception as exc:
            failed += 1
            print(
                f"ERROR: no se pudo procesar el archivo ({type(exc).__name__})",
                file=sys.stderr,
            )
            if not args.no_history:
                record_safely(
                    "process",
                    args.db,
                    file_path=str(source),
                    source_language=options["source_language"],
                    target_language=options.get("target_language"),
                    provider=options["engine"],
                    requested_provider=options["engine"],
                    success=0,
                    error_type="processing",
                )
    print(
        f"Resumen: {len(sources) - failed}/{len(sources)} archivos procesados; "
        f"{translation_failures} fallos de traducción."
    )
    return 1 if failed or translation_failures else 0


def _analysis_payload(command: str, analytics, qa_report) -> Dict[str, Any]:
    if command == "qa":
        return qa_report.to_dict()
    return {"analytics": analytics.to_dict(), "qa": qa_report.to_dict()}


def _csv_report(command: str, payload: Dict[str, Any]) -> str:
    output = io.StringIO(newline="")
    if command == "qa":
        writer = csv.DictWriter(
            output,
            fieldnames=("severity", "rule", "subtitle_index", "message", "metadata"),
        )
        writer.writeheader()
        for finding in payload["findings"]:
            row = dict(finding)
            row["metadata"] = json.dumps(
                row["metadata"], ensure_ascii=False, sort_keys=True
            )
            writer.writerow(row)
        return output.getvalue()

    flattened: Dict[str, Any] = {}
    for group, metrics in payload["analytics"].items():
        for name, value in metrics.items():
            flattened[f"{group}.{name}"] = (
                json.dumps(value, ensure_ascii=False, sort_keys=True)
                if isinstance(value, (dict, list))
                else value
            )
    writer = csv.DictWriter(output, fieldnames=list(flattened))
    writer.writeheader()
    writer.writerow(flattened)
    return output.getvalue()


def _human_report(command: str, payload: Dict[str, Any], strict: bool = False) -> str:
    if command == "qa":
        passed = payload["strict_passed"] if strict else payload["passed"]
        lines = [
            f"QA: {'correcto' if passed else 'problemas encontrados'}; "
            f"{payload['error_count']} errores, {payload['warning_count']} avisos, "
            f"{payload['info_count']} informativos."
        ]
        lines.extend(
            f"{finding['severity'].upper()} [{finding['rule']}] "
            f"cue {finding['subtitle_index']}: {finding['message']}"
            for finding in payload["findings"]
        )
        return "\n".join(lines) + "\n"

    metrics = payload["analytics"]
    content = metrics["content"]
    timing = metrics["timing"]
    quality = metrics["quality"]
    processing = metrics["processing"]
    return (
        f"Subtítulos: {content['subtitle_count']} | duración: "
        f"{timing['total_duration_ms'] / 1000:.3f}s\n"
        f"Palabras: {content['total_words']} | caracteres: "
        f"{content['total_characters']} | líneas: {content['line_count']}\n"
        f"CPS medio/máx/mín: {timing['average_cps']:.3f}/"
        f"{timing['max_cps']:.3f}/{timing['min_cps']:.3f} | solapamientos: "
        f"{timing['overlapping_subtitles']}\n"
        f"QA: {quality['errors']} errores, {quality['warnings']} avisos | "
        f"limpieza: {processing['lines_removed']} líneas eliminadas | "
        f"tiempo: {processing['processing_time_seconds']:.3f}s\n"
    )


def _run_analysis(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    from .services.subtitle_qa import QARules

    source = Path(args.input).expanduser()
    try:
        service = SubtitleService(qa_rules=QARules())
        if args.command == "qa":
            qa_report = service.qa_file(str(source))
            analytics = None
        else:
            analytics, qa_report = service.analyze_file(str(source))
    except FileNotFoundError:
        print("ERROR: archivo de subtítulos no encontrado", file=sys.stderr)
        return 2
    except (OSError, UnicodeError, ValueError) as exc:
        print(
            f"ERROR: no se pudo analizar el archivo ({type(exc).__name__})",
            file=sys.stderr,
        )
        return 2
    except Exception as exc:
        print(
            f"ERROR: no se pudo analizar el archivo ({type(exc).__name__})",
            file=sys.stderr,
        )
        return 2
    payload = (
        qa_report.to_dict()
        if args.command == "qa"
        else _analysis_payload(args.command, analytics, qa_report)
    )
    export_format = args.format
    if args.csv:
        if export_format == "json":
            parser.error("--csv y --format json son incompatibles")
        export_format = "csv"
    output_format = (
        Path(args.output).suffix.lower().lstrip(".") if args.output else None
    )
    if export_format is None and output_format:
        export_format = output_format
    if export_format not in (None, "json", "csv"):
        parser.error("el formato de exportación debe ser json o csv")
    if output_format in {"json", "csv"} and export_format not in (None, output_format):
        parser.error("la extensión de --output no coincide con el formato solicitado")
    if args.json and export_format == "csv":
        parser.error("--json y --format csv son incompatibles")
    if export_format == "csv":
        rendered = _csv_report(args.command, payload)
    elif args.json or export_format == "json":
        rendered = (
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        )
    else:
        rendered = _human_report(
            args.command, payload, strict=getattr(args, "strict", False)
        )

    if args.output:
        try:
            output_path = Path(args.output).expanduser()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(rendered, encoding="utf-8", newline="")
        except OSError as exc:
            print(
                f"ERROR: no se pudo guardar el informe ({type(exc).__name__})",
                file=sys.stderr,
            )
            return 2
        if not args.json:
            print(f"Informe guardado: {output_path}")
    else:
        sys.stdout.write(rendered)
    qa_section = payload if args.command == "qa" else payload.get("qa", {})
    record_safely(
        args.command,
        getattr(args, "db", None),
        file_path=str(source),
        success=1 if qa_section.get("passed", True) else 0,
        qa_errors=qa_section.get("error_count", 0),
        qa_warnings=qa_section.get("warning_count", 0),
    )
    if args.command == "qa":
        passed = qa_report.strict_passed if args.strict else qa_report.passed
        return 0 if passed else 1
    return 0


def _run_benchmark(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    from .services.translation_benchmark import (
        BenchmarkConfig,
        TranslationBenchmark,
        load_benchmark_dataset,
    )
    from .services.translation_service import TranslationService

    providers = [name.strip() for name in (args.providers or "").split(",")]
    providers = [name for name in providers if name]
    if not providers:
        parser.error("--providers requiere al menos un provider")
    if args.runs is None or args.runs < 1:
        parser.error("--runs debe ser un entero positivo")
    if args.max_retries is None or args.max_retries < 0:
        parser.error("--max-retries debe ser un entero no negativo")
    try:
        dataset = load_benchmark_dataset(args.dataset)
    except ValueError as exc:
        parser.error(str(exc))
    try:
        config = BenchmarkConfig(
            providers=providers,
            source_language=args.source_language,
            target_language=args.target_language,
            runs=args.runs,
            include_texts=args.include_texts,
        )
    except ValueError as exc:
        parser.error(str(exc))
    service = TranslationService(
        max_retries=args.max_retries,
        fallbacks={} if args.no_fallback else None,
    )
    try:
        report = TranslationBenchmark(config, translation_service=service).run(
            dataset["cues"]
        )
    except ValueError as exc:
        parser.error(str(exc))
    rendered = report.to_json()
    if args.output:
        try:
            output_path = Path(args.output).expanduser()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(rendered, encoding="utf-8", newline="")
        except OSError as exc:
            print(
                f"ERROR: no se pudo guardar el informe ({type(exc).__name__})",
                file=sys.stderr,
            )
            return 2
        print(f"Informe guardado: {output_path}")
    else:
        sys.stdout.write(rendered)
    if args.output_csv:
        try:
            csv_path = Path(args.output_csv).expanduser()
            csv_path.parent.mkdir(parents=True, exist_ok=True)
            csv_path.write_text(report.to_csv(), encoding="utf-8", newline="")
        except OSError as exc:
            print(
                f"ERROR: no se pudo guardar el CSV ({type(exc).__name__})",
                file=sys.stderr,
            )
            return 2
        print(f"CSV guardado: {csv_path}")
    failed = sum(1 for run in report.runs if not run.success)
    print(
        f"Benchmark: {len(report.runs)} ejecuciones "
        f"({len(providers)} providers × {args.runs} runs, "
        f"{report.dataset_size} cues); {failed} fallidas.",
        file=sys.stderr,
    )
    if args.store:
        from .services.history_store import HistoryError, HistoryStore

        try:
            with HistoryStore(getattr(args, "db", None)) as store:
                store.record_benchmark_report(report)
            print(
                f"Benchmark {report.benchmark_id} guardado en historial.",
                file=sys.stderr,
            )
        except HistoryError as exc:
            print(
                f"AVISO: no se pudo guardar el benchmark ({type(exc).__name__})",
                file=sys.stderr,
            )
    return 0


def _run_history(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    from .services.history_store import HistoryError, HistoryStore

    if args.limit is None or args.limit < 1:
        parser.error("--limit debe ser un entero positivo")
    try:
        with HistoryStore(args.db) as store:
            if args.stats:
                stats = store.run_stats(provider=args.provider)
                if args.json:
                    sys.stdout.write(
                        json.dumps(stats, ensure_ascii=False, indent=2, sort_keys=True)
                        + "\n"
                    )
                else:
                    print(
                        f"Ejecuciones: {stats['total']} "
                        f"({stats['successful']} ok, {stats['failed']} fallidas, "
                        f"{stats['fallbacks']} con fallback)"
                    )
                    avg = stats["avg_duration_ms"]
                    print(
                        "Duración media: "
                        + (f"{avg:.1f}ms" if avg is not None else "desconocida")
                    )
                return 0
            rows = store.recent_runs(
                limit=args.limit,
                provider=args.provider,
                operation=args.operation,
                only_errors=args.errors_only,
                only_fallbacks=args.fallback_only,
            )
    except HistoryError as exc:
        print(
            f"ERROR: no se pudo leer el historial ({type(exc).__name__})",
            file=sys.stderr,
        )
        return 2
    if args.json:
        sys.stdout.write(
            json.dumps(rows, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        )
        return 0
    if not rows:
        print("Sin ejecuciones registradas.")
        return 0
    for row in rows:
        status = "ok" if row.get("success") else (row.get("error_type") or "fallo")
        fallback = " +fallback" if row.get("fallback_used") else ""
        print(
            f"#{row['id']} {row.get('timestamp', '')[:19]} "
            f"[{row.get('operation')}] {row.get('file_path') or row.get('benchmark_id') or ''} "
            f"provider={row.get('requested_provider') or row.get('provider') or '-'} "
            f"status={status}{fallback}"
        )
    return 0


def _run_transcribe(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    from .services.transcription_providers import TranscriptionError
    from .services.transcription_service import TranscriptionService
    from .services.transcription_whisper import WHISPER_MODELS

    source = Path(args.input).expanduser()
    service = TranscriptionService()
    try:
        service.check_available("whisper")
    except TranscriptionError as exc:
        from .services.transcription_whisper import INSTALL_HINT

        message = (
            INSTALL_HINT
            if INSTALL_HINT in str(exc)
            else f"provider de transcripción no disponible ({exc.error_type})"
        )
        print(f"ERROR: {message}", file=sys.stderr)
        return 2
    size, description = WHISPER_MODELS.get(args.model, ("?", ""))
    print(
        f"Modelo whisper/{args.model} ({size}, {description}): "
        "se descarga una vez si no está en caché.",
        file=sys.stderr,
    )

    def _progress(step: str, payload: object) -> None:
        if isinstance(payload, dict) and "segments" in payload:
            ratio = payload.get("ratio")
            suffix = f" ({ratio * 100:.0f}%)" if isinstance(ratio, float) else ""
            print(f"... {payload['segments']} segmentos{suffix}", file=sys.stderr)

    try:
        result = service.transcribe_file(
            str(source),
            provider_name="whisper",
            model=args.model,
            language=args.language,
            device=args.device,
            progress_callback=_progress,
        )
    except TranscriptionError as exc:
        print(f"ERROR: no se pudo transcribir ({exc.error_type})", file=sys.stderr)
        if not args.no_history:
            record_safely(
                "transcription",
                args.db,
                file_path=str(source),
                file_format=args.target_format,
                provider="whisper",
                requested_provider="whisper",
                model=args.model,
                source_language=args.language,
                success=0,
                error_type=getattr(exc, "error_type", "unknown"),
            )
        return 2
    try:
        content = service.render(result, args.target_format)
    except TranscriptionError as exc:
        print(
            f"ERROR: no se pudieron generar los subtítulos ({exc.error_type})",
            file=sys.stderr,
        )
        return 2
    if args.output:
        destination = Path(args.output).expanduser()
    else:
        destination = source.with_name(
            f"{source.stem}_transcribed.{args.target_format}"
        )
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8", newline="")
    except OSError as exc:
        print(
            f"ERROR: no se pudo guardar la transcripción ({type(exc).__name__})",
            file=sys.stderr,
        )
        return 2
    metrics = result.metrics
    print(
        f"OK {source} -> {destination} "
        f"({len(result.segments)} cues, idioma: {result.language})"
    )
    if args.stats_json and metrics is not None:
        print(
            json.dumps(metrics.to_dict(), ensure_ascii=False, sort_keys=True),
        )
    if not args.no_history:
        try:
            from .services.history_store import HistoryStore

            with HistoryStore(args.db) as store:
                store.record_transcription_result(
                    result,
                    file_path=str(source),
                    file_format=args.target_format,
                )
        except Exception as exc:
            print(
                f"AVISO: no se pudo registrar el historial ({type(exc).__name__})",
                file=sys.stderr,
            )
    return 0


def _run_pipeline(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    from .services.media_pipeline import (
        MediaPipeline,
        PipelineConfig,
        PipelineConfigError,
        record_pipeline_result,
    )

    source = str(Path(args.input).expanduser())
    transcribe = args.transcribe
    if transcribe is None:
        suffix = Path(source).suffix.lower()
        transcribe = suffix not in {".srt", ".vtt", ".ass", ".ssa", ".txt"}
    try:
        config = PipelineConfig(
            input_media=source,
            output_subtitle=str(Path(args.output).expanduser())
            if args.output
            else None,
            transcription_enabled=transcribe,
            transcription_model=args.model,
            transcription_language=args.language,
            transcription_device=args.device,
            clean_enabled=args.clean,
            qa_enabled=args.qa,
            qa_strict=args.strict,
            translation_enabled=args.translate,
            source_language=args.source_language,
            target_language=args.target_language,
            provider=args.provider,
            max_retries=args.max_retries,
            fallback_enabled=not args.no_fallback,
            output_format=args.target_format,
            burn_in_enabled=args.burn_in,
            output_video=str(Path(args.video_output).expanduser())
            if args.video_output
            else None,
        ).validate()
    except PipelineConfigError as exc:
        parser.error(str(exc))

    def _progress(stage: str, payload: object) -> None:
        if isinstance(payload, dict) and payload.get("state") == "started":
            print(f"... etapa: {stage}", file=sys.stderr)
        elif stage == "transcription" and isinstance(payload, dict):
            count = payload.get("segments")
            if count:
                print(f"... transcripción: {count} segmentos", file=sys.stderr)

    try:
        result = MediaPipeline().run(config, progress_callback=_progress)
    except Exception as exc:
        print(
            f"ERROR: no se pudo completar la pipeline ({type(exc).__name__})",
            file=sys.stderr,
        )
        return 1
    if not args.no_history:
        record_pipeline_result(result, config, args.db)
    if args.stats_json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    else:
        for stage in result.stages:
            print(f"{stage.status:>9}  {stage.name}")
        if result.success:
            print(f"OK {source} -> {result.output_subtitle}")
            if result.output_video:
                print(f"Vídeo: {result.output_video}")
        elif result.cancelled:
            print("Cancelada.", file=sys.stderr)
        else:
            for error in result.errors:
                print(
                    f"ERROR [{error['stage']}] {error['error_type']}: "
                    f"{error['message']}",
                    file=sys.stderr,
                )
    return 0 if result.success else 1


def _run_serve(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    try:
        import uvicorn  # type: ignore[import-not-found]
    except ImportError:
        print(
            "ERROR: la API requiere el extra 'api' (python -m pip install '.[api]')",
            file=sys.stderr,
        )
        return 2
    if not 1 <= args.port <= 65535:
        parser.error("--port debe estar entre 1 y 65535")
    from .api.app import app as api_app

    print(
        f"SRT4U API en http://{args.host}:{args.port} "
        f"(docs en http://{args.host}:{args.port}/docs)"
    )
    uvicorn.run(api_app, host=args.host, port=args.port, log_level="info")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "process":
        return _process(args, parser)
    if args.command in {"analyze", "qa"}:
        return _run_analysis(args, parser)
    if args.command == "benchmark":
        return _run_benchmark(args, parser)
    if args.command == "history":
        return _run_history(args, parser)
    if args.command == "transcribe":
        return _run_transcribe(args, parser)
    if args.command == "pipeline":
        return _run_pipeline(args, parser)
    if args.command == "serve":
        return _run_serve(args, parser)
    parser.error("comando no reconocido")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
