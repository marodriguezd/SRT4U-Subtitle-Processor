# Pipeline audiovisual end-to-end

La pipeline convierte las capacidades de las fases 1–9 en un flujo coherente
y reutilizable, sin duplicar lógica de dominio:

```
MEDIA/SUBTÍTULO
→ transcripción (TranscriptionService, solo si la entrada es audio/vídeo)
→ parse (SubtitleService, solo si la entrada ya es subtítulo)
→ limpieza (SubtitleService.clean_subtitles)
→ analytics (SubtitleAnalyticsService)
→ QA (SubtitleQA, findings "antes")
→ traducción opcional (TranslationService vía SubtitleService.translate_subtitles)
→ analytics final
→ QA final (findings "después", distinguibles de los previos)
→ exportación (SubtitleService.format_output, SRT/VTT)
→ burn-in opcional (FFmpeg, misma receta que VideoBurnerService)
```

## Arquitectura

`application/services/media_pipeline.py`:

- `PipelineConfig`: configuración explícita y validada. `validate()` separa
  errores de configuración (`PipelineConfigError`: falta el archivo,
  extensión incompatible, `--target` sin `--translate`, burn-in sin vídeo ni
  `--video-output`, salida que pisa la entrada) de errores de ejecución.
- `MediaPipeline`: orquestador, una instancia por ejecución (nunca compartido
  entre hilos). Cada etapa delega en el servicio que ya la posee; la pipeline
  solo mide tiempos, registra estados y serializa.
- `PipelineResult`: `success`, `failed_stage`, `cancelled`, `stages`
  (nombre/estado/duración/detalle por etapa), `transcription_result`,
  `translation_metrics`, `analytics_before/after`, `qa_before/after`,
  `cleaning`, `output_content`, salidas, duraciones, `errors` (etapa +
  `error_type` + mensaje) y `warnings`. `to_dict()` es JSON-seguro, sin bytes
  multimedia.

La entrada puede ser audio/vídeo (se transcribe) o subtítulo (se parsea y se
salta la transcripción): la misma pipeline cubre ambos casos.

## Etapas y errores por etapa

| Etapa | Origen reutilizado | Error típico |
|---|---|---|
| transcription | `TranscriptionService` | `provider_not_installed`, `model_unavailable`, `invalid_file`, `cancelled` |
| parse | `SubtitleService` parse/detect | `invalid_file` |
| cleaning | `clean_subtitles` | — (cuenta líneas) |
| analytics / analytics_final | `analyze_subtitles` | — |
| qa / qa_final | `qa_subtitles` | `qa_failed` (solo con `--strict`, misma semántica que `srt4u qa`) |
| translation | `translate_subtitles` + `TranslationMetrics` | `error_type` del provider, `translation_error` |
| export | `format_output` + escritura | `export_error` |
| burn_in | `run_burn_in_sync` | `ffmpeg_unavailable`, `burn_in_error`, `cancelled` |

El QA no estricto nunca detiene: deja avisos y continúa, como el `process`
actual. La traducción hereda el comportamiento existente (fallo total →
etapa fallida; fallos parciales → aviso, texto original conservado).
La cancelación es cooperativa entre etapas (y dentro de transcripción y
burn-in): detiene nuevas etapas, conserva el parcial en `PipelineResult` y
registra `cancelled` en historial/jobs.

## Métricas

Sin duplicados: se reutilizan `TranscriptionMetrics`, `TranslationMetrics`,
`SubtitleAnalytics` y los dicts de QA. Propias de la pipeline: `total_duration_ms`,
`media_duration_ms`, `stages_completed`, `failed_stage`, `success`/`cancelled`,
`cleaning {lines_removed, items_before/after}`.

## Historial

Un registro principal `operation='pipeline'` con archivo, formato, provider
(traducción o transcripción), modelo Whisper, idiomas, nº cues, duración del
medio y total, éxito, tipo de error, QA final y fallos de traducción. Sin
transcript, sin multimedia, sin claves. El detalle por etapa vive en el
`PipelineResult` devuelto, no en SQLite.

## CLI

```bash
srt4u pipeline video.mp4 --model small --language es --clean --qa \
  --translate --target en --provider google --format srt \
  -o subs_en.srt --stats-json
srt4u pipeline subs.srt --no-clean --translate --target en -o out.srt
srt4u pipeline video.mp4 --burn-in --video-output final.mp4
```

`--transcribe/--no-transcribe` (defecto: auto según entrada), `--strict`,
`--max-retries/--no-fallback`, `--db/--no-history`. Salida humana (tabla de
etapas) o `--stats-json` estable. Códigos: 0 ok, 1 fallo de ejecución,
2 error de configuración.

## API

`POST /api/v1/pipeline` (multipart + formularios espejo del CLI, sin burn-in:
el job server-side no fija rutas de vídeo) → `202 {job_id}`;
`GET /api/v1/jobs/{id}` con el `PipelineResult` serializado. Mismo
`JobManager`, errores sanitizados, sin claves ni trazas ni multimedia.

## GUI

Página **Pipeline** (icono zap): archivo, modelo/idioma, destino/provider,
formato, toggles de limpieza/traducción/QA/estricto/burn-in (+ vídeo salida),
`PipelineWorker(QThread)` + `ProgressModal` existentes. El progreso muestra
etapas reales con % solo cuando hay ratio real (transcripción/burn-in);
cancelación cooperativa; al completar reutiliza la página de resultado y
registra el historial.

## Burn-in headless

`BurnInWorker` es Qt-bound, así que `run_burn_in_sync()` ejecuta la misma
receta sin Qt: `get_ffmpeg_path` → duración/dimensiones → `generate_ass_script`
→ mismo comando ffmpeg (`libx264`, `-progress pipe:1` para % real) →
terminación ante cancelación y limpieza de parciales. Requiere FFmpeg (y
PyQt6 instalado para importar el generador ASS); si falta, error claro
`ffmpeg_unavailable`/`burn_in_error`.

## Ejemplo realista

```bash
srt4u pipeline charla.mp4 --model small --language auto --clean --qa \
  --translate --source auto --target en --provider deepl \
  --format srt -o charla_en.srt --stats-json --db historial.db
```

## Límites

Sin diarización, hablantes, streaming, resumen, embeddings, nube ni auth.
La traducción cancela al terminar el cue en curso (se comprueba tras cada cue,
no a mitad de uno). Los jobs en memoria se pierden al reiniciar.
