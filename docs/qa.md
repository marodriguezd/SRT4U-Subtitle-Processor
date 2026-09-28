# Subtitle QA determinista

SRT4U ofrece QA como una etapa independiente y reutilizable del procesamiento. Trabaja sobre el modelo existente `SubtitleItem`; no depende de PyQt6, de la CLI ni de Analytics. Desde código se puede invocar `SubtitleQA.validate(items, ...)`, o usar el servicio:

```python
from application.services.subtitle_qa import QARules
from application.services.subtitle_service import SubtitleService

service = SubtitleService(qa_rules=QARules(max_cps=17, max_lines=2))
report = service.qa_file("input.srt")  # QA solamente; no calcula Analytics
for finding in report.findings:
    print(finding.severity, finding.rule, finding.subtitle_index, finding.message)
```

Para cues ya parseados se usa `service.qa_subtitles(items, file_format=..., source_content=...)`. Si también se necesitan métricas, `analyze_file()` devuelve `(analytics, report)` y comparte el resultado de QA. Los mismos inputs producen los mismos hallazgos. No se usa IA ni se infiere calidad lingüística.

## Qué valida

| Regla | Severidad | Criterio |
|---|---|---|
| `invalid_index`, `duplicate_index` | error | Índices de cue no enteros/positivos o repetidos. En SRT también se verifican índices de origen; saltos de secuencia se reportan como `invalid_format` warning. |
| `invalid_timecode` | error | Timecode no interpretable, inicio negativo o intervalo con inicio mayor/igual al final. |
| `invalid_format` | error/warning | Estructura básica SRT/VTT/ASS/SSA inválida. La cabecera VTT ausente y secciones/campos básicos ASS/SSA inválidos son error. |
| `empty_file`, `empty_subtitle` | warning | Archivo vacío o cue sin texto visible. |
| `duration_too_short`, `duration_too_long` | warning | Duración fuera de los límites configurados. |
| `overlap` | warning | Cue que comparte al menos 1 ms con otro intervalo. Los extremos consecutivos (fin igual a inicio) no se solapan. Se emite un hallazgo por cada cue afectado, con un cue representativo en `metadata.overlaps_with`; no se enumeran todos los pares para evitar crecimiento cuadrático en entradas muy solapadas. |
| `cps_exceeded` | warning | Caracteres visibles por segundo por encima del límite. Etiquetas HTML/ASS reconocidas se excluyen del cálculo. |
| `line_too_long`, `too_many_lines`, `empty_line` | warning | Longitud por línea, exceso de líneas o líneas vacías. |
| `duplicate_subtitle` | warning | Texto visible duplicado ignorando mayúsculas, minúsculas y espacios repetidos. |
| `malformed_formatting_tag` | warning | Etiquetas HTML/ASS reconocidas desequilibradas o incompletas. |
| `formatting_tag_mismatch` | warning | Al proporcionar cues de referencia, el conjunto de etiquetas de formato difiere. |
| `non_monotonic_order` | info | Un cue válido empieza antes que el cue válido precedente en el orden de entrada. |

No se juzgan gramática, traducción, sincronización respecto a audio/video, ni convenciones lingüísticas. Los formatos SRT/VTT/ASS/SSA pasan validaciones estructurales deterministas; no se promete implementar cada extensión opcional de esos estándares. TXT conserva el comportamiento del parser actual y no tiene estructura fuente de timecodes que validar.

## Severidades y política

- **error**: invalidez estructural o temporal; `QAReport.passed` es falso.
- **warning**: archivo procesable con una preocupación de calidad; la política por defecto sigue pasando.
- **info**: observación que no implica fallo.

`QAReport.strict_passed` falla con cualquier error o warning, pero no con info. Los hallazgos usan una estructura común: `severity`, `rule`, `subtitle_index` (o `null` si no hay cue concreto), `message` y `metadata`. `to_dict()` ofrece además totales y los indicadores `passed` y `strict_passed`.

## Límites configurables

`QARules` es inmutable, se valida al construirse y no requiere un archivo de configuración ni dependencias adicionales:

| Campo | Valor predeterminado | Unidad / significado |
|---|---:|---|
| `max_cps` | 20 | caracteres visibles por segundo; warning solo si se supera |
| `max_characters_per_line` | 42 | caracteres visibles en una línea |
| `max_lines` | 2 | líneas de diálogo |
| `min_duration_ms` | 1000 | duración mínima en milisegundos |
| `max_duration_ms` | 7000 | duración máxima en milisegundos |

Los valores exactamente iguales al límite son válidos. Para otros estándares, pasa valores apropiados al crear `QARules`; por ejemplo:

```python
rules = QARules(
    max_cps=17,
    max_characters_per_line=40,
    max_lines=2,
    min_duration_ms=800,
    max_duration_ms=6000,
)
```

## Reglas extensibles

`SubtitleQARule` es la interfaz pequeña para reglas locales. Una regla determinista implementa `validate(items, rules, findings)` y añade instancias `QAFinding`; se puede componer con las reglas integradas mediante `SubtitleQA(rule_set=...)`. Las reglas predeterminadas son stateless y no se requiere framework externo. Analytics consume el informe existente; su servicio y métricas no necesitan cambios al añadir hallazgos.

## CLI y códigos de salida

```bash
python -m application.cli qa input.srt
python -m application.cli qa input.srt --json
python -m application.cli qa input.srt --csv
python -m application.cli qa input.srt --strict --json
python -m application.cli qa input.srt --format csv --output report.csv
```

Formatos:

- **Humano**: formato predeterminado, resumen de totales seguido por hallazgos.
- **JSON**: `--json`, `--format json`, o `--output report.json`. Para QA, la raíz contiene `passed`, `strict_passed`, los totales y `findings`. Cada hallazgo incluye `metadata` como objeto JSON.
- **CSV**: `--csv`, `--format csv`, o `--output report.csv`. Una fila por hallazgo, con columnas `severity,rule,subtitle_index,message,metadata`; metadata se codifica como JSON en esa columna. Para un informe sin hallazgos se produce la cabecera sin filas.

`--json` y CSV no se pueden combinar. `--strict` solo está disponible para `qa`: código 1 con cualquier error o warning, código 0 sin errores ni warnings. Sin `--strict`, se mantiene el comportamiento anterior: código 1 con errores, código 0 si solo hay warnings/info.

| Código | Significado |
|---:|---|
| `0` | QA pasa según la política seleccionada; o comando `analyze` completado. |
| `1` | QA encontró errores; con `--strict`, encontró errores o warnings. |
| `2` | No se pudo leer el archivo, guardar el informe, o los argumentos/formato de exportación son inválidos. Los argumentos inválidos se notifican mediante argparse. |

Ejemplos de automatización:

```bash
python -m application.cli qa subtitles.srt --strict --json > qa.json
python -m application.cli qa subtitles.srt --csv --output findings.csv
```

## Arquitectura y alcance

`SubtitleQA` coordina unidades de regla sobre cues ya parseados y puede validar también el contenido original para recuperar errores de estructura que el parser existente omita. `SubtitleService.qa_file()` y `qa_subtitles()` exponen QA de forma independiente a la presentación y Analytics; `analyze_file()` sigue ofreciendo ambos informes sin duplicar el parsing. El solapamiento se detecta con barrido ordenado y heap, evitando producir todos los pares si hay solapamientos densos. Así, QA ya se puede insertar como etapa `process → clean → translate → qa → output` sin implementar aquí el sistema de pipelines. No se introduce FastAPI, persistencia, benchmarking ni IA.
