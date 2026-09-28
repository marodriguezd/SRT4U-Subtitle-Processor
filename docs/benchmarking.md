# Benchmarking de providers de traducción

El benchmark ejecuta un dataset fijo de subtítulos contra varios providers y
registra métricas objetivas de ejecución por cada par (provider, run). No
decide qué provider es "mejor" y no evalúa calidad lingüística: produce datos
para análisis offline posterior (Python/Pandas/Jupyter).

## Arquitectura

```text
dataset (builtin o .srt/.vtt/.ass/.txt)
        ↓
TranslationBenchmark (application/services/translation_benchmark.py)
        ↓ per-cue, secuencial
TranslationService.translate_with_metrics() → TranslationMetrics
        ↓ agregación + métricas derivadas
BenchmarkReport → JSON / CSV
```

Sin PyQt6, sin Pandas, sin red en tests (mocks). `TranslationService` no se
duplica: el benchmark solo orquesta y mide wall-time de cada pasada.

## Dataset

- Por defecto: lista interna versionada (`BENCHMARK_DATASET_VERSION = "1"`,
  10 cues originales en inglés: cortas, medias, largas, diálogo, multilínea,
  etiquetas, puntuación, nombres propios).
- `tests/fixtures/benchmark/sample_en.srt`: 8 cues equivalentes en SRT para
  reproducibilidad desde archivo.
- CLI acepta un archivo o directorio de subtítulos; el parsing reutiliza
  `SubtitleService`. Al cambiar los cues, subir la versión del dataset para no
  mezclar resultados de revisiones distintas.

## Métricas por ejecución

Cada `BenchmarkRun` conserva: `benchmark_id`, `timestamp`, `run_index`,
`dataset_version`, `dataset_size`, `provider`, `requested_provider`, `model`,
idiomas, `number_of_cues`, caracteres/palabras in/out, `duration_ms`
(wall-time de la pasada), `success`, `error_type`, `retry_count`,
`fallback_used`, `providers_used`, `fallback_error_type`, tokens,
`estimated_cost` (`null` sin tarifa fiable) y `error_message` (`null` en
fallos de provider por política de seguridad).

Derivadas (rendimiento, nombres sin `cps` para no confundir con el CPS de
subtítulos): `cues_per_second`, `characters_per_second`,
`words_per_second`, `latency_per_cue_ms`, `latency_per_1k_chars_ms`
(`null` si la duración es desconocida o cero).

## CLI

```bash
python -m application.cli benchmark tests/fixtures/benchmark \
    --providers google,deepl,ollama \
    --source en --target es --runs 3 \
    --output benchmark.json --output-csv benchmark.csv
```

Opciones: `--providers` (coma), `--source/--target`, `--runs`,
`--output`, `--output-csv`, `--include-texts` (conserva textos in/out),
`--max-retries`, `--no-fallback`. Exit 0 si el benchmark corre (los fallos
de traducción son datos, se resumen en stderr); 2 ante configuración o
E/S inválidas.

Providers remotos necesitan su API key (`deepl_api_key`, `openai_api_key`
en ajustes); `ollama`/`llm` usan el endpoint OpenAI-compatible configurado
(`openai_base_url`, `openai_model`). La suite normal no hace red.

## JSON / CSV

- JSON: cabecera (`benchmark_id`, `timestamp`, `dataset_version`,
  `dataset_size`, `config`, `environment` con Python/plataforma) + `runs`.
- CSV: una fila por ejecución, columnas estables en
  `BENCHMARK_CSV_COLUMNS`, listas como JSON inline. Carga directa:

```python
import pandas as pd
df = pd.read_csv("benchmark.csv")
df.groupby("requested_provider")["latency_per_cue_ms"].median()
```

Ejemplo de fila (JSON):

```json
{
  "provider": "ollama",
  "requested_provider": "ollama",
  "model": "llama3",
  "duration_ms": 1234,
  "success": true,
  "fallback_used": false,
  "latency_per_cue_ms": 154.25
}
```

## Runs y fallback

Cada repetición se conserva individual: agregados (media/mediana/p90) se
calculan offline, nunca en el benchmark. El fallback nunca se oculta:
`requested_provider` conserva la intención, `provider` el efectivo,
`providers_used` la cadena y `fallback_used`/`fallback_error_type` el hecho.

## Reproducibilidad y limitaciones

El informe registra dataset, providers, modelo, idiomas, runs, config,
fecha y entorno. No se afirma comparabilidad perfecta: red, carga del
servidor local/remoto y CPU distorsionan latencias. Sin evaluación
semántica (sin LLM-as-a-judge), sin SQLite/FastAPI/dashboard: ejecutar →
medir → registrar → exportar.

## Pruebas

```bash
python -m pytest -q tests/test_translation_benchmark.py -m "not network"
```
