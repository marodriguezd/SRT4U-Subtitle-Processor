# Análisis de resultados del benchmark

Capa offline sobre los exports de `TranslationBenchmark`. No toca lógica de
traducción, no usa red, no evalúa calidad lingüística y nunca decide un
"ganador": describe latencia, rendimiento, errores y calidad de los datos.

## Cargar resultados

```python
from analysis.benchmark_analysis import load_report, to_dataframe

report = load_report("benchmark.json")          # export JSON del benchmark
df = to_dataframe(report["runs"])               # requiere pandas (solo análisis)
df.groupby("requested_provider")["latency_per_cue_ms"].median()
```

También `load_runs_csv("benchmark.csv")`. Pandas/NumPy/Matplotlib viven solo
en el entorno de análisis; **no** están en `requirements.txt` del runtime.

## Ejecutar el análisis

Notebook reproducible: `notebooks/benchmark_analysis.ipynb` (usa
`analysis/sample_benchmark.json`, datos sintéticos de stub providers). Para
cualquier export real, cambia `REPORT` y ejecuta las celdas.

Sin Jupyter, el mismo pipeline corre headless:

```bash
python -m analysis.benchmark_analysis benchmark.json --out reports/benchmark
python -m analysis.benchmark_analysis benchmark.json --out reports/benchmark --no-plots
```

Genera en `--out` (nunca sobrescribe el dataset original):

- `summary.csv` — descriptivos por provider;
- `cleaned_dataset.csv` — ejecuciones con tipos coercionados;
- `analysis_report.json` — validación, descriptivos, errores, correlaciones,
  calidad de datos y conclusiones;
- `plots/*.png` — 7 gráficos.

## Limpieza y validación

`clean_runs` coerciona numéricos/booleans y `providers_used`; conserva los
fallos como datos. Solo se descartan filas que no son mapeos (contadas en
`notes`). `validate_runs` informa nulos por columna, fallos, fallbacks,
providers/models, valores imposibles (duración negativa, éxito con
`error_type`) y secuencias de `run_index` incompletas.

## Métricas

Descriptivos sobre ejecuciones exitosas con duración, por provider (también
agrupable por modelo o éxito): count, mean, median, min, max, stdev, p10,
p25, p75, p90, IQR y CV para `duration_ms`, `cues_per_second`,
`characters_per_second`, `words_per_second`, `latency_per_cue_ms` y
`latency_per_1k_chars_ms`. Errores: tasas de éxito/fallo, `error_type`,
media/máx de `retry_count`, tasa de fallback por provider.

## Gráficos (una pregunta cada uno)

- `latency_distribution.png` — ¿cómo se distribuye la latencia?
- `latency_boxplot.png` — ¿qué provider es más rápido/variable?
- `throughput_bars.png` — throughput mediano por provider.
- `runs_variability.png` — ¿deriva la latencia entre runs?
- `errors_by_provider.png` — tasa de fallo por provider.
- `latency_vs_characters.png` / `latency_vs_cues.png` — ¿escala la duración
  con el tamaño de entrada?

## Calidad de datos y limitaciones

`data_quality` marca: runs con fallback, sin tokens, coste `null`, sin
modelo, duraciones ausentes, muestras < 3 runs y valores imposibles. Límites:
con un único dataset fijo, las correlaciones tamaño↔duración son `null`
(varianza cero en el tamaño); latencias mezclan red/CPU/carga externa; los
stubs del sample no representan providers reales; sin juicio de calidad.

## Interpretación

Las conclusiones citan siempre dataset, configuración y runs, p. ej.:
"El provider X presentó menor mediana de latencia en este dataset",
"Y% de las ejecuciones recurrieron a fallback". Ver `conclusions` en
`analysis_report.json`.

## Pruebas

```bash
python -m pytest -q tests/test_benchmark_analysis.py
```
