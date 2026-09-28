# Deuda técnica y veredictos (hardening final)

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
12. **Hex restantes sin constante**: tras la normalización selectiva quedan
    literales con semántica propia (blancos puros de pintura, colores de
    previsualización elegibles, superficies permanentes oscuras, hover
    `#059669`). Sin equivalencia exacta en `Styles`; no se inventan
    constantes de un solo uso.

## Decisiones del hardening final (comprobado, no se toca)

- **Contrato de instalación**: `pip install .` instala la base funcional
  (GUI + CLI: PyQt6 + deep-translator); `requirements.txt` es la vía rápida
  del checkout/CI con los mismos pines; `desktop` se conserva como alias;
  `api`/`transcription`/`dev` siguen opcionales. Veredicto anterior de
  "base con cero dependencias" queda sustituido por este (test
  `test_install_contract_base_has_desktop_stack`).
- **`translation_failures` del pipeline** registra fallos reales
  (`PipelineResult.translation_failures`), nunca `number_of_cues`.
  Regresión cubierta en `test_history_partial_translation_failure_count`.
- **Gap icono/texto de la navegación** lo define el QSS `nav-btn`, sin
  espacios literales (`test_nav_labels_have_no_layout_whitespace`).
- **`srt4u.desktop` del repo** es launcher del checkout (rutas relativas);
  las distribuciones instalan su propio launcher (AppImage: `Exec=SRT4U`).
- **Fuente multiplataforma**: `Styles.ui_font()` (Segoe UI solo en Windows,
  fuente general del sistema en Linux/macOS); sin fuentes empaquetadas.
- **Reproductor**: el icono play/pause se sincroniza con `playbackState`
  (cubre fin/error); arrastrar volumen sale de mute; reset visual al cargar
  vídeo nuevo.
- **Flujos de error UI verificados sin cambios**: completado / cancelado /
  fallo se distinguen; cancelar es silencioso; los fallos muestran diálogos
  sanitizados; el historial nunca rompe la ejecución.

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
- Wheel/base importan sin extras opcionales: CLI/API/servicios/historial/
  pipeline funcionan sin Qt (transcripción y burn-in con import perezoso y
  error claro).
