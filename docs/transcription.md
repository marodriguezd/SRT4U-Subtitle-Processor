# Transcripción audiovisual con Whisper (local, opcional)

SRT4U convierte audio/vídeo en subtítulos que entran directamente al flujo
existente: Analytics → QA → limpieza → traducción → exportación → burn-in.

## Arquitectura

```
TranscriptionProvider (ABC, application/services/transcription_providers.py)
        │ registry TranscriptionRegistry ("whisper")
        ▼
WhisperProvider (transcription_whisper.py, faster-whisper perezoso)
        │ TranscriptionResult + TranscriptionMetrics (transcription_models.py)
        ▼
TranscriptionService (coordinador: valida medio, resuelve backend, renderiza)
        │ to_subtitle_items() → SubtitleItem existentes
        ▼
SubtitleService.format_output() → SRT/VTT → Analytics/QA/history
```

GUI, CLI y API comparten `TranscriptionService`; las rutas no contienen
lógica y el dominio nunca importa FastAPI ni PyQt. La interfaz es extensible:
otro motor se añade implementando `TranscriptionProvider` y registrándolo.

## Decisión de backend: faster-whisper

| Opción | Veredicto |
|---|---|
| **faster-whisper (elegido)** | pip-instalable (Win/Linux/macOS), rápido en CPU (`int8` vía CTranslate2), CUDA opcional, modelos versionados de Hugging Face, timestamps por segmento, VAD opcional |
| openai-whisper | descartado: arrastra torch (~2 GB), lento en CPU, peor para distribuir |
| whisper.cpp / bindings | descartado: instalación frágil por plataforma, más pegamento nativo |

`faster-whisper` nunca se importa en el arranque: el import es perezoso y su
ausencia produce `provider_not_installed` con la instrucción de instalación.
Sin GPU todo funciona en CPU (`int8`); con CUDA disponible se usa `float16`.

## Instalación

La base funciona sin Whisper. Solo transcripción:

```bash
python -m pip install '.[transcription]'
```

## Modelos

| Modelo | Tamaño aprox. | Uso |
|---|---|---|
| tiny | ~75 MB | pruebas, borradores rápidos |
| base | ~145 MB | ligero aceptable |
| small | ~465 MB | **equilibrio recomendado (defecto)** |
| medium | ~1.5 GB | mejor calidad, más lento |
| large-v3 | ~3 GB | máxima calidad, más RAM |
| turbo | ~1.6 GB | rápido con buena calidad |

El modelo se descarga **una vez** desde Hugging Face a su caché; CLI, API y
GUI avisan antes (`Modelo whisper/small (…): se descarga una vez si no está
en caché`). Caché reubicable con `SRT4U_WHISPER_MODEL_DIR`. Si el modelo no
está disponible → `model_unavailable` controlado, sin trazas al usuario.

## Formatos de entrada

Vídeo: mp4, mkv, webm, mov, avi, m4v, mpg, mpeg. Audio: mp3, wav, m4a, ogg,
oga, opus, flac, aac, wma. Sin parser propio: el backend decodifica (FFmpeg
vía sus dependencias); si FFmpeg falta o el archivo es ilegible →
`ffmpeg_unavailable` / `invalid_file`.

## CLI

```bash
python -m application.cli transcribe video.mp4 \
    --model small --language auto --format srt -o subs.srt
python -m application.cli transcribe audio.mp3 --language es --format vtt
```

`--language auto` (defecto) detecta el idioma. `--device auto|cpu|cuda`.
`--stats-json` emite métricas; `--db/--no-history` controlan el historial.
Headless, mismos códigos que el resto del CLI (0 ok, 2 error).

## API

`POST /api/v1/transcribe` (multipart, tope 500 MB) → `202 {job_id}` y
`GET /api/v1/jobs/{id}` con el resultado (`output_content`, `language`,
`metrics`). Mismo `TranscriptionService` que CLI/GUI; el trabajo pesado
corre en `JobManager`, nunca en el request. Sin backend → job `failed` con
mensaje seguro (`provider_not_installed`).

```bash
curl -F file=@clip.mp4 -F model=tiny -F language=es \
  http://127.0.0.1:8000/api/v1/transcribe
```

## GUI

Página **Transcribir** (icono play): elegir archivo, modelo, idioma, formato,
dispositivo, iniciar con `ProgressModal`, cancelación cooperativa (el backend
revisa la cancelación entre segmentos; sin porcentajes inventados: muestra
segmentos, % real si se conoce la duración, o tiempo transcurrido), guardado
`*_transcribed.srt` y reutilización de la página de resultado (abrir archivo/
carpeta). Sin Whisper: aviso + botón desactivado, la app sigue funcionando.

## Segmentación y salida

Cada segmento validado → `SubtitleItem` (reindexado, `end > start`, vacíos
descartados). SRT/VTT reutilizan `SubtitleService.format_output()`; desde ahí
valen `analyze_subtitles`, `qa_subtitles`, limpieza, traducción y burn-in sin
cambios. Sin alineamiento por palabra en esta fase (los timestamps de
segmento son suficientes).

## Métricas (`TranscriptionMetrics`)

`provider, model, source_language (detectado), segment_count,
characters/words_output, media_duration_ms, processing_duration_ms,
real_time_factor (= processing/media, solo si ambos conocidos),
success, error_type, device`. JSON-serializables.

## Historial (`operation = transcription`)

Por ejecución: archivo, formato de salida, provider, modelo, idioma
detectado, nº cues, duración del medio (`media_duration_ms`, columna nueva
por migración v2), tiempo de proceso, éxito y tipo de error. **Nunca**: audio,
vídeo, textos del transcript, claves ni secretos.

## Errores normalizados

`provider_not_installed, model_unavailable, invalid_file,
ffmpeg_unavailable, unsupported_format, out_of_memory, cancelled, unknown`.
Mensajes cortos al usuario; detalle solo en log; sin stack traces en
CLI/API/GUI.

## Privacidad

Inferencia 100% local; el único tráfico es la descarga única del modelo.
No se registra contenido, no se guarda multimedia, no se loguean textos.

## Rendimiento

Sin optimización prematura: se registran modelo, duración del medio, tiempo
de proceso, dispositivo y RTF por ejecución (historial + `--stats-json`).

## Limitaciones (fase 9)

Sin diarización, sin hablantes, sin alineamiento por palabra, sin streaming,
sin traducción simultánea, sin resumen/embeddings/RAG, sin nube. La
cancelación es cooperativa entre segmentos (un segmento largo termina antes
de abortar). Los jobs en memoria se pierden al reiniciar.

## Packaging

- App base (PyInstaller) compila **sin** faster-whisper: el import perezoso y
  el extra opcional lo garantizan; la GUI detecta la ausencia y la explica.
- Variante con transcripción: incluir el extra `transcription` + FFmpeg en el
  sistema/instalador; **no** empaquetar modelos (se descargan una vez con
  aviso, ~75 MB–3 GB según modelo).
- CTranslate2 aporta ruedas para Win/Linux/macOS x86_64 y ARM; CUDA solo
  donde haya drivers; CPU `int8` como denominador común.

## Tests

```bash
python -m pytest -q tests/test_transcription.py -m "not network"  # 22, fake
SRT4U_TEST_REAL_WHISPER=1 SRT4U_TEST_MEDIA=clip.mp4 \
  python -m pytest tests/test_transcription_real.py -q -s  # opcional, omitido por defecto
```

El test real exige extra instalado, medio local y modelo `tiny` (lento
potencialmente); nunca corre en la suite normal.
