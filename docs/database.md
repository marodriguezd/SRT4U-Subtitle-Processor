# Historial local SQLite

SQLite guarda el historial de ejecuciones (process, analyze, qa, benchmark)
con sus métricas y hallazgos QA para consultas y análisis posterior. Es una
capacidad auxiliar: si la BD falla, el procesamiento continúa y solo se
registra un aviso en el log. JSON/CSV del benchmark coexisten sin cambios.

## Ubicación

`SRT4U/history.db` en el directorio de configuración multiplataforma
(`%APPDATA%`, `~/Library/Application Support`, `~/.config` o
`$XDG_CONFIG_HOME`). `SRT4U_HISTORY_DB` la sustituye (usado por los tests
para no tocar la BD real). Comandos `process`/`benchmark`/`history` aceptan
`--db`; `process` admite `--no-history`.

## Schema (v3)

- `runs`: una fila por ejecución — `timestamp`, `operation`, `file_path`,
  `file_format`, idiomas, `provider`, `requested_provider`, `model`, cues,
  caracteres/palabras in/out, `duration_ms`, `success`, `error_type`,
  `retry_count`, `fallback_used`, `providers_used` (JSON), `fallback_error_type`,
  tokens, `estimated_cost`, `qa_errors`, `qa_warnings`,
  `translation_failures`, `benchmark_id`, `run_index`. Índices en
  `timestamp`, `requested_provider`, `operation`, `benchmark_id`.
  Añadidos por migración: `media_duration_ms` (v2, transcripción/pipeline)
  y `parse_issues` (v3, contador de bloques que el parser no pudo usar;
  asesor, nunca altera `success`; lo registran `process`, `transcription`,
  `pipeline` y el propio `record_run`).
- `qa_findings`: `run_id → runs`, `severity`, `rule`, `subtitle_index`,
  `message`, `metadata` (JSON).

Los benchmarks guardan una fila por `BenchmarkRun` (`operation='benchmark'`).
No se decidió tabla separada para no duplicar: `benchmark_id`/`run_index`
relacionan las filas.

## Privacidad

Nunca se persisten: textos de subtítulos, API keys, headers de
autorización, secretos ni binarios. Solo métricas agregadas, metadatos QA y
la ruta del archivo procesado. Los textos de benchmark siguen siendo opt-in
(`--include-texts`) y solo en JSON/CSV, jamás en SQLite.

## Migraciones

Sin Alembic: `PRAGMA user_version` + `_MIGRATIONS` en
`application/services/history_store.py`. BD nueva → schema v1 directo. BD
v0 → migración controlada. BD más nueva que el código → error explícito sin
modificarla. Nunca se borran datos al migrar.

## Uso programático

```python
from application.services.history_store import HistoryStore

with HistoryStore() as store:
    rows = store.recent_runs(limit=20, provider="ollama", only_fallbacks=True)
    stats = store.run_stats()
    findings = store.get_findings(run_id)

import pandas as pd
df = pd.DataFrame(store.export_rows(operation="benchmark"))
```

Toda la SQL usa parámetros; la UI/CLI/servicios nunca tocan SQLite
directo: `HistoryStore` es la única capa (`record_*_safely` para el modo
auxiliar que nunca lanza).

## CLI

```bash
python -m application.cli history --limit 20
python -m application.cli history --provider ollama --fallback-only
python -m application.cli history --errors-only --json
python -m application.cli history --stats
python -m application.cli benchmark ... --store
```

## GUI

La página History (navegación, icono reloj) muestra las 100 ejecuciones más
recientes con refresco manual; sin BD legible muestra el estado vacío. Las
páginas existentes no cambian.

## Robustez y rendimiento

BD corrupta → `HistoryError` y el procesamiento sigue. Una transacción por
ejecución (benchmark: una para todo el informe). Sin conexiones por métrica
ni commits por fila.

## Pruebas

```bash
python -m pytest -q tests/test_history_store.py -m "not network"
```

Siempre sobre BD temporales (`tmp_path` + `SRT4U_HISTORY_DB` en `conftest.py`).
