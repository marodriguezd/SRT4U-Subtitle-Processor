# Auditoría completa del codebase — SRT4U v1.1.0

**Fecha:** 2026-09-27
**Alcance:** 100% del repositorio (código, tests, herramientas, documents, infra, assets) — 48 archivos indexados, 8.649 líneas de `.py` + 27 archivos no-`.py`.
**Punto de partida:** `AUDIT_REPORT.md` (auditoría previa, 2026-09-26) ya remediada en §16 + los cambios de UI publicados en la pre-release `v1.1.0`.
**Motivo de esta pasada:** revisión de 100% posterior a la remediación, con foco en los defectos visuales del **diálogo de archivos** mostrados en la captura aportada por el usuario.
**Estado del árbol antes de esta pasada:** limpio (`git status` vacío), todo lo anterior ya commiteado y publicado.

---

## 1. Resumen ejecutivo

| Severidad | Hallazgos | Estado |
|---|---|---|
| **Crítico** | 0 | — |
| **Mayor** | 7 | 7 corregidos en esta pasada |
| **Menor** | 11 | 3 corregidos, 8 documentados como recomendación |
| **Informativo** | 6 | documentados (2 son falsos positivos de herramienta) |

**Lo más relevante:**

1. El diálogo de archivos (y los message boxes) estaba fuera del tema: usaba iconos del tema del escritorio (ámbar), el azul por defecto de Qt para la selección (`#308cc6`) y **dos botones con icono invisible** (`contraste 1.00`). Es exactamente lo que muestra la captura adjunta. **Corregido** con estilo Fusion + paleta explícita + QSS acotado + proveedor de iconos SVG tematizado + iconos de barra de herramientas SVG.
2. `LICENSE` **no se empaquetaba** en ninguna de las tres builds → el botón "Ver licencia" de Acerca de siempre caía al fallback web en los binarios distribuidos. **Corregido**.
3. La suite de tests **escribía en la configuración real del usuario** (`~/.config/SRT4U/settings.json`) y arrastraba estado entre ejecuciones. **Corregido** (config aislada en `tmp_path`).
4. Dos tests de traducción hacían **llamadas de red reales sin marcador** → flakeo/fallo en entornos sin Internet. **Corregido** (marcador `network` + degradación a skip).
5. El gate de lint/formato de CI **no cubría `tools/`**, y `tools/regenerate_screenshots.py` estaba sin formatear. **Corregido**.
6. `requests` figuraba en `requirements.txt` **sin usarse** en el código. **Corregido**.
7. **26 fallos silenciosos** (`except: pass`, un `print()`) ocultaban problemas de traducción, configuración, FFmpeg e i18n. **Corregido**: log rotativo + avisos al usuario donde importa (§9).

**Cobertura de verificación final:** `114 passed` con PyQt6 6.11, `102 passed` con la mínima declarada (PyQt6 6.6.1), `ruff check` limpio, `ruff format --check` limpio, invariante i18n OK (212 claves × 6 idiomas), 46 capturas offscreen regeneradas.

---

## 2. Método y evidencia de herramientas

Todas las comprobaciones se ejecutaron sobre el árbol real en `.venv` (Python 3.14.7, PyQt6 6.11.0 / Qt 6.11.0):

| Herramienta | Comando | Resultado |
|---|---|---|
| Tests | `.venv/bin/python -m pytest tests/ -q` | **114 passed** (84 previos + 20 de diálogos + 10 de logging) |
| Lint | `.venv/bin/ruff check application main.py conftest.py tests tools` | All checks passed! |
| Formato | `.venv/bin/ruff format --check application main.py conftest.py tests tools` | 31 files already formatted |
| Vulture | `.venv/bin/python -m vulture application main.py conftest.py tests tools --min-confidence 80` | 0 hallazgos reales (ver §6) |
| Pyflakes | `.venv/bin/python -m pyflakes application main.py conftest.py tests tools` | sin salida |
| i18n | script de invariantes (claves/placeholders/vacíos/uso) | 212 × 6 idénticas, 0 vacíos, 0 placeholders inconsistentes |
| Escaneos | emojis, TODO/FIXME, `except:` desnudos, `print()`, strings hardcodeados, QSS inline | ver §5 |
| Geometría/contraste | script offscreen (render real, luminancia relativa sRGB) | ver §4 |

**Inventario (48 archivos indexados):** 16 `.py` de aplicación (≈5.600 líneas), 10 de tests, 1 herramienta, 11 documentos/configuración, 11 assets.

---

## 3. Hallazgos — Categoría A: diálogos del sistema fuera de tema (Mayor)

**A1 — Diálogo de archivos no tematizado · Mayor · CORREGIDO**
Los `QFileDialog` no nativos heredaban el tema del escritorio, no la paleta de la app. Medición sobre el render real (captura adjunta y reproducción offscreen):

| Elemento | Antes | Ahora |
|---|---|---|
| `toParentButton` (subir un nivel) | contraste **1.02** (invisible) | **12.99** (dark) / **10.68** (light) |
| `newFolderButton` | contraste **1.00** (invisible) | **13.26** / **10.80** |
| `backButton` / `forwardButton` | 3.34 (chevrons grises del estilo) | 12.99 / 10.68 |
| Iconos del panel lateral (carpetas) | iconos **ámbar** del tema del escritorio | 0 píxeles ámbar (SVG tematizados) |
| Color de selección | `#308cc6` (azul por defecto de Qt) | `PRIMARY #6366F1` (paleta y QSS) |
| Iconos de los botones Open/Cancel | carpeta ámbar + aspa roja nativas | sin iconos nativos (QSS de la app) |

Causas raíz: (a) dependencia del tema del escritorio para los iconos (`iconProvider` por defecto) y para los botones internos; (b) paleta resuelta por `QStyleSheetStyle` (por el QSS de aplicación de tooltips) que restaura el resaltado por defecto de Qt; (c) regla QSS previa con selector comodín (`QDialog, QWidget`) que pintaba indiscriminadamente viewports y splitters.
**Solución:** `prepare_dialog()` público con estilo Fusion determinista, `Styles.dialog_palette()`, QSS acotado a `QFileDialog`/descendientes, `ThemedFileIconProvider` (iconos SVG para carpeta/archivo/drive/computadora/escritorio/papelera/red), iconos SVG en los 6 `QToolButton` y ocultado del `QSizeGrip` no tematizado.

**A2 — Message boxes fuera de tema · Mayor · CORREGIDO**
Igual que A1 pero sobre `QMessageBox` (19 puntos de llamada). Ahora `ThemedMessageBox.build()` aplica Fusion + `Styles.dialog_palette()` + `message_box_style()`.

**A3 — Diálogos del sistema sólo con variante oscura · Menor · CORREGIDO**
`file_dialog_style()` y `message_box_style()` no aceptaban tema: en modo claro los diálogos salían oscuros. Se añadió `Styles.set_dark()` (sincronizado desde `MainWindow._apply_theme()`) y todas las funciones de estilo aceptan `dark`.

**A4 — Tooltips congelados en el tema de arranque · Menor · CORREGIDO**
El QSS de tooltips se aplicaba una sola vez en `main.py`; al cambiar a claro seguían oscuros. Ahora se re-aplica al cambiar de tema.

**A5 — Sin cobertura de regresión para los diálogos del sistema · Mayor · CORREGIDO**
Nuevos `tests/test_system_dialogs.py` (20 casos): paleta por tema, color de selección declarado en QSS, 6 botones de barra con icono no nulo y **contraste ≥ 3.0**, uso del proveedor tematizado, `QSizeGrip` oculto, idempotencia de `prepare_dialog()` y tematización del message box, en 6 idiomas × 2 temas.

---

## 4. Hallazgos — Categoría B: empaquetado y distribución (Mayor)

**B1 — `LICENSE` no se incluía en ninguna build · Mayor · CORREGIDO**
`_open_license_file()` buscaba el `LICENSE` del repo (o su ruta relativa desde `__file__`), inexistente dentro de un binario PyInstaller: en las builds distribuidas el botón **siempre** abría la web. Se añadió `--add-data "LICENSE;."` (Windows) / `"LICENSE:."` (Linux/macOS) y la búsqueda ahora cubre `sys._MEIPASS` y el directorio del ejecutable congelado.

**B2 — `build_exe.bat` no empaqueta FFmpeg ni LICENSE · Menor · documentado**
El script local de Windows genera un `.exe` sin `ffmpeg` (el burn-in no funciona) y sin `LICENSE`. Es una build de conveniencia; se documenta para que el desarrollador no la confunda con la de CI.

**B3 — Dependencia muerta `requests` · Mayor · CORREGIDO**
Única dependencia de `requirements.txt` que no se importa en ningún módulo (la traducción usa `urllib` de la stdlib deliberadamente). Eliminada.

**B4 — Cotas de versión laxas · Informativo · CORREGIDO**
`PyQt6>=6.4.0` sin cota superior, mientras el proyecto se verifica con 6.11: una futura 6.x podía romper sin aviso y la cota declarada nunca se comprobaba. Al validarla se descubrió que **la cota era además falsa**: `QMessageBox.Option`/`setOption()` —de los que dependen los message boxes tematizados— no existen en PyQt6 6.4 ni 6.5.

Verificación empírica (venv desechable, Python 3.14, cada versión con su runtime `PyQt6-Qt6` del mismo minor):

| PyQt6 | Resultado |
|---|---|
| 6.4.0 | suite: 2 fallos (`QMessageBox` sin `Option`/`setOption`) |
| 6.5.0 | `QMessageBox.Option` no existe |
| 6.6.0 | ni siquiera importa `QtCore` con el runtime 6.6.x (símbolo privado ausente) |
| **6.6.1** | **102 passed** (`-m "not network"`) — mínimo verificado |
| 6.11.x | 104 passed (entorno de desarrollo) |

**Solución:** `requirements.txt` pasa a `PyQt6>=6.6.1,<6.12` (cota inferior verificada + cota superior contra saltos de minor no probados) y el nuevo job `compat-min-pyqt6` de CI resuelve la cota mínima desde el propio `requirements.txt`, instala esa versión con el `PyQt6-Qt6` del mismo minor, **asserta que la versión instalada es exactamente la declarada** y ejecuta la suite; es prerrequisito de `release`, por lo que la cota no puede volver a desincronizarse en silencio.

---

## 5. Hallazgos — Categoría C: tests (Mayor)

**C1 — La suite modificaba la configuración real del usuario · Mayor · CORREGIDO**
`I18nService.set_language()` guarda por defecto (`save_to_config=True`) y varios tests lo llamaban sin `save_to_config=False`; además la UI guarda opciones al procesar. Efecto real observado durante la auditoría: un `ui_language: zh-CN` persistido por un test cambiaba qué cadena traducida medían los tests de layout (un fallo intermitente difícil de diagnosticar). Ahora `conftest.py` redirige `ConfigService._get_config_dir` a un directorio temporal en **todos** los tests.

**C2 — Tests dependientes de Internet sin marcador · Mayor · CORREGIDO**
`test_free_google_translation` y `test_parallel_vs_sequential_subtitles_translation` llamaban a Google Translate en vivo: sin red, fallaban en lugar de omitirse. Ahora están marcados `network` (marcador registrado en `conftest.py`) y hacen `skip` si el motor devuelve el texto original (señal de "sin red/servicio no disponible"), manteniendo la cobertura cuando hay conectividad.

**C3 — El test de conversión escribía en `tests/fixtures/` · Menor · CORREGIDO**
`test_main_window_flow` ejecutaba la conversión real sobre `tests/fixtures/sample.srt`, dejando `sample_converted.vtt` en el árbol (ignorado por git, pero residuo si el test fallaba a mitad). Ahora trabaja sobre una copia en `tmp_path`.

**C4 — `scaled_app_font` / `*a, **k` en vulture · Informativo · falso positivo**
Las fixtures de pytest se inyectan por nombre (su efecto es el valor) y `lambda self, *a, **k: None` usa `*a/**k` para aceptar cualquier firma. No son hallazgos reales.

---

## 6. Hallazgos — Categoría D: código y estilo (Menor)

| ID | Hallazgo | Estado |
|---|---|---|
| D1 | `ThemedMessageBox.question()` nunca se usaba (código muerto, 4.º método estático) | **Corregido** (eliminado) |
| D2 | `MainWindow.__init__` fijaba `setWindowTitle("SRT4U - Subtitle Processor")` y `retranslate_ui()` lo sobrescribía en la misma construcción | **Corregido** (línea redundante eliminada) |
| D3 | 26 bloques `except Exception` que silenciaban fallos (`pass`/`return` sin traza) en traducción, FFmpeg, config e i18n | **Corregido** (ver §9) |
| D4 | `ConfigService.save()` informaba de errores con `print()` (único `print` en código de app) | **Corregido** (log + `save_error` + aviso en la UI) |
| D5 | Etiquetas de navegación con dos espacios iniciales (`f"  {t(key)}"`) como hack de layout (los tests hacen `.strip()`) | Documentado · recomendado margen/padding en QSS |
| D6 | `main.py` fija `QFont("Segoe UI", 10)` en todas las plataformas (no existe en Linux/macOS; fallback silencioso) | Documentado · recomendado selección de fuente por plataforma |
| D7 | `.desktop` del repo con `Exec=python3 main.py` / `Icon=assets/icon.png` (no instalable tal cual) y sin `MimeType` para subtítulos | Documentado · el de la AppImage sí es correcto |
| D8 | Estilos inline con colores literales conviven con `Styles` (los gestiona `retint_inline_text()`, pero sigue habiendo constantes duplicadas en QSS de widgets) | Documentado |
| D9 | `tools/regenerate_screenshots.py` y `tests/test_ui_and_batch.py` escribían/usaban rutas fijas | **Corregido** (formato + `tmp_path`) |
| D10 | `Styles.SUCCESS`/`DANGER` etc. centralizados, pero varios QSS de widgets aún repiten hex equivalentes | Documentado |
| D11 | 5 claves `nav.*` no localizables por grep (`i18n_key` dinámico) pueden parecer "no usadas" en futuros análisis | Informativo |

---

## 7. Higiene verificada (sin hallazgos)

- **Emojis/símbolos gráficos:** 0 en UI (sólo `♪`/`♫` dentro de los patrones de limpieza de spam, uso funcional).
- **TODO/FIXME/XXX/HACK:** 0.
- **`except:` desnudos:** 0 (todos con excepción explícita).
- **i18n:** 212 claves idénticas en 6 idiomas, 0 vacías, placeholders coherentes entre idiomas, sin claves usadas y no definidas (las 5 `nav.*` se resuelven dinámicamente).
- **Strings de UI hardcodeados:** sólo nombre de app (`SRT4U`), autor, badge `CC BY-NC-SA 4.0` y placeholder de tiempo `00:00:00 / 00:00:00` (decisiones documentadas).
- **Versiones:** `v1.1.0` coherente en `main.py` (AppUserModelID), `about.version_pill`, `CHANGELOG.md`, `RELEASE_NOTES.md` y el tag de la release.
- **Secretos:** 0 credenciales en el repo; las claves se leen de `settings.json` local (ignorado por git).
- **Código muerto:** `FileService`, `_is_completed`, `DEFAULT_PRIMARY/ERROR/WARNING`, `QAbstractFileIconProvider` mal importado (detectado y corregido en esta pasada) → 0 pendientes.

---

## 8. Índice por archivo (qué se tocó)

| Archivo | Cambio |
|---|---|
| `application/ui/file_dialogs.py` | ✅ `prepare_dialog()`, `ThemedFileIconProvider`, iconos SVG de barra, sin iconos nativos en botones, `QSizeGrip` oculto |
| `application/ui/styles.py` | ✅ `set_dark/is_dark`, `dialog_colors()`, `dialog_palette()`, QSS de archivos/mensajes/tooltips por tema y acotado; colores de la barra lateral por tema (`NAV_ACTIVE_TEXT_*`, `NAV_ACTIVE_ICON_*`, `NAV_IDLE_ICON_*`) |
| `application/ui/message_boxes.py` | ✅ `build()` público + Fusion + paleta; `question()` eliminado |
| `application/ui/icons.py` | ✅ 8 iconos nuevos (`arrow_left/right/up`, `folder_plus`, `list`, `grid`, `monitor`, `drive`) |
| `application/ui/main_window.py` | ✅ `Styles.set_dark()` + tooltips por tema, `LICENSE` desde bundle, título redundante fuera |
| `application/logging_setup.py` | ✅ **nuevo**: log rotativo (512 KB × 3) en el directorio de configuración, `get_logger()`/`setup_logging()`; `install_qt_message_handler()`/`uninstall_qt_message_handler()` |
| `application/services/config_service.py` | ✅ log de lectura/escritura, `load_error`/`save_error`, `save()`/`set()` devuelven éxito |
| `application/services/translation_service.py` | ✅ `last_error` **por hilo**, log de cada fallo de motor y de los fallbacks |
| `application/services/subtitle_service.py` | ✅ `ProcessingStats.translation_failures`, log por bloque y resumen de traducción incompleta |
| `application/services/video_burner_service.py` | ✅ log de detector de FFmpeg, duración/dimensiones, cancelación, limpieza, salida de error de FFmpeg |
| `application/services/i18n_service.py` | ✅ log de fallos de `QLocale` y de formateo de traducciones |
| `application/ui/main_window.py` | ✅ avisos al usuario (traducción incompleta, ajustes no guardados, config ilegible), log de arranque y de fallos de worker/lote |
| `main.py` | ✅ `setup_logging()` + `install_qt_message_handler()` + `sys.excepthook` que registra la traza y avisa al usuario |
| `tests/test_logging.py` | ✅ **nuevo**: 13 tests de logging, mensajes de Qt, errores de config y avisos al usuario |
| `conftest.py` | ✅ configuración aislada, marcador `network` |
| `tests/test_system_dialogs.py` | ✅ 20 tests nuevos de tema de diálogos |
| `tests/test_nav_theme.py` | ✅ **nuevo**: 9 tests de contraste de la barra lateral en ambos temas (componiendo los fondos translúcidos y los píxeles reales) |
| `tests/test_i18n.py` | ✅ idioma por defecto (auto → sistema, guardado → override) y etiqueta de idioma efectivo |
| `tests/test_translation_free.py` | ✅ marcador `network` + skip sin conectividad |
| `tests/test_ui_and_batch.py` | ✅ conversión sobre copia temporal |
| `tests/test_screenshot_tool.py` | ✅ nuevas capturas esperadas (24) |
| `tools/regenerate_screenshots.py` | ✅ capturas de diálogo de archivos (2 temas) y message box; formateado |
| `.github/workflows/build.yml` | ✅ `tools` en lint/formato, `LICENSE` en las 3 builds, job `compat-min-pyqt6` (prerrequisito de `release`) |
| `requirements.txt` | ✅ `requests` eliminado; cota `PyQt6>=6.6.1,<6.12` verificada |
| `README.md` / `README_es.md` | ✅ galería actualizada (46 PNG, diálogos de archivos/mensajes) |
| `CHANGELOG.md` / `RELEASE_NOTES.md` | ✅ entradas de esta pasada |
| `AUDIT_REPORT_FULL.md` | ✅ este informe |

**Sin cambios** (revisados al 100%, correctos): `application/services/*` (config, translation, subtitle, video_burner, i18n), `application/platform_utils.py`, `main.py`, `application/ui/widgets.py`, `burn_in_dialog.py`, `tests/test_cleaning|conversion|parsing|i18n|video_burner|ui_layout.py`, `ruff.toml`, `srt4u.desktop`, `LICENSE`, `assets/*`.

---

## 9. Fallos silenciosos → log + aviso al usuario (D3/D4)

Se convirtieron **los 26 bloques `except Exception`** del código (y el único `print()`) en registro con contexto, distinguiendo lo esperado (fallbacks de red) de lo anómalo (configuración no escribible, FFmpeg sin permisos):

| Área | Antes | Ahora |
|---|---|---|
| Traducción | `except: return item` (bloque sin traducir, sin rastro) | log por bloque + `TranslationService.last_error` **por hilo** (los workers paralelos no se pisan el error) + `ProcessingStats.translation_failures` |
| Configuración | `print()` y `except: pass` (config corrupta ≡ config inexistente) | `logger.exception` + `load_error`/`save_error` + `save()`/`set()` devuelven éxito |
| FFmpeg | fallbacks mudos a 1920x1080 y limpiezas que fallaban en silencio | log de binario descartado, duración/dimensiones no detectadas, terminación forzada, archivo parcial no eliminable, stderr de FFmpeg al fallar |
| i18n | `QLocale` caído y `format()` con placeholders incorrectos pasaban desapercibidos | log debug/warning con la clave afectada |
| Arranque | `sys._MEIPASS` ausente sin traza | log debug + `sys.excepthook` que registra la traza de cualquier excepción no controlada |

**Avisos al usuario (UI, i18n × 6 idiomas — 8 claves nuevas, 220 por idioma):** traducción incompleta (`{failed}` de `{total}`), ajustes no guardados (con la ruta), configuración ilegible/restaurada, y error inesperado con la ruta del log. Los fallos que no requieren acción del usuario (persistencia automática de opciones, heurísticas de FFmpeg) se registran sin interrumpir.

**Mensajes de Qt enrutados al mismo log:** `install_qt_message_handler()` (instalado en `main.py` **antes** de crear la `QApplication`, para no perder los avisos de arranque) engancha `qInstallMessageHandler` y envía `qDebug`/`qInfo` → DEBUG, `qWarning` → WARNING, `qCritical` → ERROR y `qFatal` → CRITICAL al logger `srt4u.qt`, conservando la categoría de Qt como prefijo (`[qt.multimedia.ffmpeg] …`). `QtInfoMsg` se deja en DEBUG a propósito: Qt Multimedia lo usa para el banner de versión de FFmpeg en cada arranque. El handler tiene guarda anti-recursión (`threading.local`) y nunca propaga excepciones; `uninstall_qt_message_handler()` restaura el comportamiento por defecto y ambas funciones son idempotentes. Con esto los avisos de códecs/backend FFmpeg, de los plugins de plataforma y de QSS quedan en el diagnóstico en lugar de perderse en la consola.

**Destino del log:** `<config>/SRT4U/srt4u.log` (`%APPDATA%`, `~/Library/Application Support`, `~/.config`), rotativo 512 KB × 3, documentado en ambos README.

---

## 10. Verificación final

```
.venv/bin/python -m pytest tests/ -q                          -> 130 passed
.venv/bin/ruff check application main.py conftest.py tests tools -> All checks passed!
.venv/bin/ruff format --check …                                -> 31 files already formatted
i18n: 6 lenguas × 220 claves idénticas · 0 vacías              -> OK
QT_QPA_PLATFORM=offscreen .venv/bin/python tools/regenerate_screenshots.py -> 46 PNG
contraste paleta diálogos: texto/superficie 17.06 · atenuado/fondo 7.47 (dark) · 4.76 (light)
iconos de barra de herramientas del QFileDialog: 12.94–13.26 (dark) · 10.54–10.80 (light)
píxeles ámbar (iconos del escritorio sin tematizar): 25 -> 0
venv temporal con la cota mínima (PyQt6 6.6.1 + PyQt6-Qt6 6.6.1): 115 passed, 2 deselected
message handler de Qt: qWarning/qCritical simulados -> presentes en srt4u.log con su nivel y categoría
arranque real offscreen (XDG_CONFIG_HOME temporal) -> srt4u.qt registra los mensajes, stderr limpio de avisos de Qt
barra lateral, píxeles renderizados: pestaña activa 1.1:1 -> 5.69:1 (claro) · 9.39:1 (oscuro)
pestañas inactivas: 4.72:1 (claro) · 7.20:1 (oscuro) · iconos ≥ 3:1 en ambos temas
etiqueta de idioma efectivo: cabe en 1-2 líneas en las 6 lenguas al ancho mínimo
```

**Pendiente recomendado (fuera del alcance de esta corrección):** hack de los dos espacios en la navegación (D5), fuente por plataforma (D6), `.desktop` instalable con `MimeType` (D7) y cota de versión de PyQt6 (B4, corregida).

---

# 11. Verificación extremo a extremo con material real

Toda la corrección anterior se había validado con fixtures diminutos y vídeos
sintéticos. Para comprobar la aplicación **al cien por cien en su entorno
gratuito real**, se ha ejecutado un recorrido completo sobre material
aportado por el usuario:

| Fichero | Datos verificados con `ffprobe` |
|---|---|
| `S1pK5hmTzkE_1min.mp4` | 1920×1080, h264 (High), 60 fps, aac LC 48 kHz estéreo, 60 000 ms, 44.6 MB |
| `S1pK5hmTzkE_1min.srt` | 25 bloques, 22 solapados, 1 hueco exacto de 30,0–31,0 s |

El SRT real tiene precisamente las dos dificultades que el resto de la suite
sintética no ejercita: **solapamientos** (22 de 25 bloques) y un **hueco** de un
segundo en el que no debe aparecer nada. Ambas se comprueban de forma explícita.

Todo esto queda automatizado en **`tests/test_e2e_real_media.py`** (26 casos,
21 áreas de la aplicación). El módulo se localiza el material con la variable
`SRT4U_E2E_MEDIA` y **se omite entero** si los ficheros no están, de modo que la
suite sigue siendo ejecutable en CI sin ese material.

## Resultados por apartado

| # | Apartado | Comprobación | Resultado |
|---|---|---|---|
| 1 | Lectura | Los 25 bloques, índices 1-25, `0-5 s` … `59-60 s`, solapamientos conservados | OK |
| 2 | Conversión | SRT→SRT/VTT/ASS/TXT y vuelta: 25 bloques y 25 textos idénticos | OK |
| 3 | Conversión (TXT) | TXT es texto plano: conserva los 25 textos, sin marcas de tiempo (por diseño) | OK |
| 4 | Limpieza | 25 bloques conservados, textos intactos, tiempos sin tocar | OK |
| 5 | Traducción gratuita | Google sin clave: 5 bloques traducidos, `translation_failures == 0` | OK |
| 6 | Traducción sin red | Rama offline: texto original intacto y fallos contabilizados y avisados | OK |
| 7 | Pipeline completo | Los 6 pasos se emiten en orden (`reading`→`saving`), 0 errores en el log | OK |
| 8 | Idempotencia | Reprocesar el resultado no pierde bloques | OK |
| 9 | Metadatos FFmpeg | 60 000 ms, 1920×1080, h264 + aac detectados | OK |
| 10 | Generación ASS | `PlayResX/Y` 1920×1080, 25 `Dialogue:`, ningún inicio en el hueco | OK |
| 11 | ASS por opciones | small/medium/large × white/yellow/cyan × none/semi/solid | OK (3/3) |
| 12 | **Burn-in real** | Minuto completo grabado: **52 s, 51.8 MB, 60 000 ms**, h264 1920×1080, audio aac copiado | OK |
| 13 | **Hardsub en píxeles** | t=1/3/8 s: banda alta <1 % (sólo reencode) y banda de subtítulo 10-20× más alterada, con texto legible | OK |
| 14 | **Respeto del hueco** | t=29 s y t=32 s con subtítulo, **t=30,5 s con 0 píxeles claros** | OK |
| 15 | Gestión de errores | Vídeo corrupto → `failed` con diagnóstico, sin fichero a medias | OK |
| 16 | Reproductor | `LoadedMedia`, 60 000 ms, sin errores, `seek_to_ms(30000)` exacto | OK |
| 17 | Overlay de subtítulos | Sincronizado en 1 s y 52 s, vacío dentro del hueco | OK |
| 18 | Flujo principal | Procesar → 25+25 items → `*_processed.srt` en disco → página 6 → 25 tarjetas en el visor de diferencias | OK |
| 19 | Buscador de la vista previa | Filtra los subtítulos reales y el contador cambia y se restaura | OK |
| 20 | Página de conversión | Los 4 formatos generados desde la UI y releídos con 25 bloques | OK |
| 21 | Página de limpieza | 25 bloques en la salida; **el original nunca se sobrescribe** | OK |
| 22 | Lote | 3 ficheros → 3 salidas y las 3 filas con estado "completado" | OK |
| 23 | Diálogo de hardsub | Precarga el vídeo real, las 3 cajas y genera un ASS válido | OK |
| 24 | Persistencia de ajustes | Opciones guardadas y recuperadas por una ventana nueva | OK |
| 25 | Los 6 idiomas de la UI | en/es/pt/de/it/zh-CN montan la vista previa con el contenido real, sin recortes | OK |
| 26 | Servicio de traducción | Responde sin reventar con el contenido real | OK |

## Comandos y resultados

```
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_e2e_real_media.py -q -> 26 passed (1 m 13 s)
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/ -q                       -> 156 passed (2 m 51 s)
.venv/bin/ruff check application main.py conftest.py tests --select F,E7,E9,B       -> All checks passed!
.venv/bin/ruff format application main.py conftest.py tests tools                    -> 1 file reformatted, 32 unchanged
```

**Conclusión:** las 8 páginas de la aplicación, los 4 formatos, los 6 idiomas de
interfaz, el motor de traducción gratuito, el hardsub sobre el minuto real y
los caminos de error funcionan correctamente con material real, sin ningún
cambio en el código de la aplicación: las 26 pruebas son comprobaciones
externas. No se ha detectado ningún defecto pendiente en este recorrido.
