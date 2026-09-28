# Deuda técnica y veredictos de auditoría (Fase 11)

Aceptado conscientemente para la release candidate. Nada de aquí bloquea;
cada punto indica por qué no se toca.

## Deuda aceptada

1. **Batch page síncrona**: `_run_batch_processing` procesa en el hilo UI
   (bloquea en lotes grandes). Preexistente; transcripción y pipeline usan
   workers. Migrar a worker cuando haya demanda real.
2. **API analyze/qa síncronas en handlers async**: trabajo CPU acotado por el
   tope de 5 MB; sin necesidad demostrada de `to_thread`.
3. **PyQt6 en `i18n_service` y `video_burner_service`**: import a nivel de
   módulo. Verificado que CLI/API/servicios/historial/pipeline importan sin
   Qt (hasta probado con wheel sin PyQt6); burn-in headless usa import
   perezoso con error claro. Extraerlos rompería i18n reactiva sin beneficio.
4. **Exit codes CLI**: fallo de ejecución → 1 (`process`, `pipeline`),
   QA no superado → 1, configuración/uso → 2. Intencional y documentado.
5. **CI ejecuta la suite completa con red**: los runners la tienen; en local
   la RC se valida con `-m "not network"`.
6. **Jobs en memoria**: se pierden al reiniciar. Por diseño local (sin broker).
7. **Descarga única del modelo Whisper**: requiere internet la primera vez,
   siempre anunciada con tamaño. Por diseño.
8. **Cancelación cooperativa**: la etapa de traducción termina su trabajo
   actual; transcripción y burn-in sí abortan a mitad. Documentado.
9. **Sin purga de historial**: filas agregadas diminutas; no hace falta gestión.
10. **Overlap QA es warning**: `passed` lo tolera, `strict` lo frena.
    Semántica verificada en tests, no un bug.
11. **`build_exe.bat` cubre la variante BASE**: FULL documentado con flags en
    el propio `.bat` (modelos nunca empaquetados).

## Veredictos (comprobado, no se toca)

- Sin imports circulares; el dominio no importa FastAPI/Pydantic; solo UI y
  burn-in requieren PyQt6.
- Sin secretos en logs/errores/respuestas (grep + tests que buscan textos y
  `Traceback` en salidas).
- Fallback sin ciclos (cadena acotada a 8, error ante repetición);
  `max_retries` acotado en API (0–10) y no negativo en servicios/CLI.
- Temporales API siempre eliminados (incluido cancel en cola vía `on_drop`;
  la exportación pipeline usa temporal hermano y no expone rutas internas).
- SQLite: migraciones v1→v2, `record_safely` nunca rompe ejecución, sin
  transcript/audio/vídeo/claves (tests lo afirman para transcription y
  pipeline), GUI/CLI/API aíslan errores con `HistoryError`.
- OpenAPI con 13 paths; jobs con 404/409 y proyección sin campos internos.
- Wheel construido e importado sin PyQt6 ni extras: base con cero
  dependencias runtime.
