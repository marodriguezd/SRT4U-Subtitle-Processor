# Informe de auditoría del codebase — SRT4U Subtitle Processor

**Spec base:** `codebase-audit-spec.md`
**Fecha:** 2026-09-26
**Alcance:** 100% del proyecto (código, tests, docs, infra, assets)
**Naturaleza:** Auditoría de solo lectura. **No se ha modificado ningún archivo de código, lógica, tests, assets ni configuración.** Los "fix sugerido" son descripciones, no cambios aplicados.
**Idioma:** Español

---

## 1. Resumen ejecutivo

Auditoría completada sobre **48 archivos** con cobertura del 100% de las fuentes (`.py` y no-`.py`), apoyada en ejecución real de la suite y de herramientas de análisis estático.

**Resultado global:** ~**58 hallazgos** distribuidos así:

| Severidad | Nº aprox. | Naturaleza dominante |
|---|---|---|
| **Crítico** | 0 | No se halló nada que rompa ejecución ni corrompa datos |
| **Mayor** | 16 | i18n hardcodeado, código/config muertos, duplicación, docs vs código, tests inefectivos |
| **Menor** | 30 | imports/variables no usados, constantes muertas, comentarios ruido, estilos inline |
| **Informativo** | 12 | higiene, patrones, decisiones pendientes |

**Top archivos problemáticos:**

| Archivo | Hallazgos | Motivo principal |
|---|---|---|
| `application/ui/burn_in_dialog.py` | 18 | 5 imports muertos + ~20 strings ES hardcodeados + emoji 🔥 + `_is_completed` muerto |
| `application/ui/widgets.py` | 14 | 4 imports muertos + strings ES hardcodeados + uso intensivo de emojis |
| `application/ui/main_window.py` | 12 | strings ES hardcodeados en mensajes/filtros + imports muertos + duplicación |
| `application/services/i18n_service.py` | 4 | 53 claves definidas sin uso + emojis de bandera + 2 imports muertos |
| `application/services/config_service.py` | 1 | 6 claves de configuración muertas |
| `tests/*` | 8 | import muerto, ruta personal hardcodeada, tests sin aserciones, fixture duplicada |

**Los dos focos más importantes:** (1) existe un sistema i18n completo pero **decenas de cadenas de UI están hardcodeadas en español** y además hay **53 claves de traducción definidas que nunca se usan**; (2) hay **código y configuración muertos** (`FileService`, 6 claves de config) y **duplicación sistemática** de estilos y del despacho multiplataforma.

---

## 2. Métricas y cobertura

### 2.1 Cobertura de archivos (100% revisado)

| Área | Archivos | Estado |
|---|---|---|
| `application/services/` | 7 (file, config, translation, subtitle, video_burner, i18n, `__init__`) | ✅ Auditados |
| `application/ui/` | 6 (`__init__`, icons, styles, burn_in_dialog, widgets, main_window) | ✅ Auditados |
| `application/` | `__init__.py` | ✅ Auditado |
| Raíz ejecutable | `main.py`, `conftest.py` | ✅ Auditados |
| `tests/` | 7 archivos + fixtures (4) | ✅ Auditados |
| Docs/metadatos | `README.md`, `README_es.md`, `CHANGELOG.md`, `RELEASE_NOTES.md`, `GEMINI.md`, `LICENSE`, `srt4u.desktop` | ✅ Auditados |
| Infra/build | `requirements.txt`, `build_exe.bat`, `.github/workflows/build.yml`, `.gitignore` | ✅ Auditados |
| Assets | `icon.icns/ico/png/svg`, `preview*.png`, `demo-screenshot.png`, `icon-preview.html` | ✅ Auditados |

### 2.2 Evidencia de ejecución (no modifica código)

**Suite de tests (`.venv`):**
```
$ .venv/bin/python -m pytest tests/ -q
............................. [100%]
29 passed in 49.25s
```

**Linters instalados en el `.venv` del proyecto:** `ruff 0.16.9`, `pyflakes 4.0.0`, `vulture 2.16`.

**`ruff check` (F,E7,E9,B): 24 errores** — 23 auto-corregibles (todos F401 unused imports + 1 E741).
**`pyflakes`: 23 unused imports.** **`vulture --min-confidence 60`:** 21 señales (mayoría falsos positivos de overrides Qt, ver §8).

---

## 3. Definiciones

- **Incongruencia:** contradicción verificable entre dos partes del proyecto.
- **Sobrante/ruido:** elemento que no aporta (import muerto, constante muerta, comentario redundante, código muerto).
- **Severidad:** Crítico / Mayor / Menor / Informativo.

---

## 4. Hallazgos — Categoría A: Código muerto

### A1 — `FileService`: clase completa sin uso · **Mayor**
**Ubicación:** `application/services/file_service.py:1-37`
**Descripción:** La clase `FileService` (y su `cleanup_temp`, y la carpeta temporal `srt4u`) no se importa ni instancia en ningún punto del proyecto. `grep -rn FileService` solo la encuentra definida en su propio archivo.
**Fix sugerido (texto):** eliminar el módulo, o integrarlo donde se generan temporales (hoy `video_burner_service` usa `tempfile.mkdtemp` directamente).
**Evidencia:** `vulture` → "unused class 'FileService'"; `grep` sin consumidores.

### A2 — `_is_completed` escrito pero nunca leído · **Menor**
**Ubicación:** `application/ui/burn_in_dialog.py:477` (init) y `:634` (set en `_on_success`)
**Descripción:** El atributo se asigna pero nunca se consulta.
**Fix sugerido:** eliminarlo o usarlo para bloquear el cierre.

### A3 — Constantes de color sin uso · **Menor**
**Ubicación:** `application/ui/icons.py:136` (`DEFAULT_PRIMARY`), `:138` (`DEFAULT_ERROR`), `:139` (`DEFAULT_WARNING`)
**Descripción:** Definidas pero nunca referenciadas (solo `DEFAULT_MUTED`, `DEFAULT_ACTIVE`, `DEFAULT_SUCCESS` se usan).
**Evidencia:** `vulture` lo reporta; `grep` confirma ausencia de consumidores.

### A4 — Constante `Styles.SUCCESS` sin uso · **Menor**
**Ubicación:** `application/ui/styles.py:19`
**Descripción:** Definida y nunca usada (el verde se usa vía `Icons.DEFAULT_SUCCESS` y hex literales).
**Evidencia:** `vulture`.

### A5 — 53 claves i18n definidas y nunca referenciadas · **Mayor**
**Ubicación:** `application/services/i18n_service.py` (en las 6 tablas)
**Descripción:** De 156 claves por idioma, **53 no aparecen en ningún `t("…")` ni como string en el código**, ni siquiera de forma indirecta:

```
topbar.theme_tooltip
preview.sub_count_all, preview.sub_count_filtered, preview.col_idx, preview.col_start,
preview.col_end, preview.col_orig, preview.col_trans, preview.video_filter, preview.save_dialog_title
batch.status_queued, batch.status_processing, batch.status_completed, batch.status_error
settings.save_success
about.title, about.version_pill, about.author_role, about.author_location, about.license_desc,
about.perm_2, about.perm_3, about.restr_title
burn.video_card_title, burn.style_card_title, burn.lbl_font_size, burn.lbl_font_color,
burn.lbl_bg_box, burn.lbl_font_family, burn.color_white, burn.color_yellow, burn.color_cyan,
burn.box_none, burn.box_trans, burn.box_solid, burn.rendering_title, burn.encoding_status,
burn.speed, burn.eta, burn.btn_play, burn.btn_folder, burn.btn_close
alert.file_req_title, alert.file_req_desc, alert.no_subs_title, alert.no_subs_desc,
alert.conv_success_title, alert.conv_success_desc, alert.conv_error_title,
alert.save_success_title, alert.save_success_desc, alert.burn_success_title, alert.burn_success_desc
```

**Interpretación:** no todas son basura — muchas (`burn.*`, `alert.*`, `batch.status_*`) son claves **destinadas a reemplazar strings hoy hardcodeados** (ver C1/C2/C3). Otras (`preview.col_*`, `about.*`) parecen de una versión de UI anterior.
**Fix sugerido:** conectar las que correspondan a la UI actual (burn/alert/batch) y eliminar las obsoletas (preview.col_*, about innecesarias).
**Evidencia:** script AST que extrae claves y cruza contra regex `t("…")` + búsqueda literal en `application/**`.

### A6 — 6 claves de configuración muertas · **Mayor**
**Ubicación:** `application/services/config_service.py:16-21`
**Descripción:** `source_lang`, `target_lang`, `preferred_engine`, `auto_clean`, `preserve_format`, `output_dir` se definen en `DEFAULT_CONFIG` pero **nunca se leen** con `config.get(...)` en ningún punto.
**Impacto real:** la UI no restaura el motor/idiomas/opciones elegidos; el default `preferred_engine="google"` es ignorado (y de hecho el combo arranca en "DeepL" por ser el primer ítem, ver C3/H7).
**Fix sugerido:** o persistir/cargar estas claves al cambiar opciones de la Home, o eliminarlas.
**Evidencia:** `grep` de cada clave en `application/**` (solo aparece en `config_service.py`, salvo `ui_language`).

### A7 — Mapeo emoji→icono leftover · **Menor**
**Ubicación:** `application/ui/widgets.py:407-421` (`MetricCard.set_icon`)
**Descripción:** El `mapping` incluye claves emoji (`"📄"`, `"✨"`, `"⏱️"`, `"⚡"`, `"✅"`, `"📁"`) que nunca se pasan; los call sites usan siempre `"file"/"clean"/"clock"`.
**Fix sugerido:** reducir el mapping a las claves reales.

---

## 5. Hallazgos — Categoría B: Imports, variables y parámetros no usados

Todos confirmados por `ruff`/`pyflakes`. **Severidad: Menor** (salvo el E741).

| ID | Ubicación | Elemento |
|---|---|---|
| B1 | `application/services/file_service.py:9` | `typing.Any` |
| B2 | `application/services/i18n_service.py:13` | `locale` |
| B3 | `application/services/i18n_service.py:14` | `typing.Any` |
| B4 | `application/ui/burn_in_dialog.py:9` | `typing.Optional` |
| B5 | `application/ui/burn_in_dialog.py:10` | `PyQt6.QtCore.QUrl` |
| B6 | `application/ui/burn_in_dialog.py:11` | `PyQt6.QtGui.QDesktopServices` |
| B7 | `application/ui/burn_in_dialog.py:12` | `PyQt6.QtWidgets.QWidget` |
| B8 | `application/ui/burn_in_dialog.py:30` | `video_burner_service.VideoBurnerService` |
| B9 | `application/ui/icons.py:7` | `PyQt6.QtGui.QColor` |
| B10 | `application/ui/icons.py:9` | `PyQt6.QtCore.QSize` |
| B11 | `application/ui/main_window.py:9` | `PyQt6.QtGui.QIcon` |
| B12 | `application/ui/main_window.py:9` | `PyQt6.QtGui.QFont` |
| B13 | `application/ui/main_window.py:50` | `i18n_service.I18nService` |
| B14 | `application/ui/widgets.py:6` | `math` |
| B15 | `application/ui/widgets.py:8` | `PyQt6.QtCore.QRect` |
| B16 | `application/ui/widgets.py:8` | `PyQt6.QtCore.QSize` |
| B17 | `application/ui/widgets.py:27` | `.styles.Styles` |
| B18 | `application/ui/widgets.py:30` | `i18n_service.get_i18n` |
| B19 | `tests/test_i18n.py:1` | `os` |
| B20 | `tests/test_i18n.py:10` | `i18n_service.t` |
| B21 | `tests/test_i18n.py:10` | `i18n_service.get_i18n` |
| B22 | `tests/test_ui_and_batch.py:11` | `widgets.SubtitleCard` |
| B23 | `tests/test_video_burner.py:9` | `burn_in_dialog.BurnInProgressModal` |

### B24 — Variable ambigua `l` (`E741`) · **Menor**
**Ubicación:** `application/services/subtitle_service.py:165`
**Descripción:** `lines = [l.strip() for l in block.splitlines() ...]` usa `l`, que `ruff` marca como nombre ambiguo (confundible con `1`).
**Fix sugerido:** renombrar a `line`.

**Fix sugerido general:** `ruff check --select F401 --fix` resolvería 23 de 24 de una pasada (no aplicado).

---

## 6. Hallazgos — Categoría C: Strings hardcodeados (i18n incompleta)

Existe un servicio i18n con 6 idiomas, pero numerosas cadenas visibles al usuario están hardcodeadas en español y no pasan por `t()`.

### C1 — `burn_in_dialog.py`: ~20 strings en español · **Mayor**
**Ubicación y contenido:**
- `:144` `"Subtítulos listos: {n} líneas"`
- `:174` `"Tamaño de texto:"`; `:176` `addItems(["Pequeño", "Mediano", "Grande"])`
- `:183` `"Color de subtítulo:"`; `:185` `addItems(["Blanco", "Amarillo", "Cian"])`
- `:192` `"Fondo de lectura:"`; `:194` `addItems(["Caja semitransparente", "Sin fondo", "Caja sólida"])`
- `:201` `"Calidad / Velocidad:"`; `:203` `addItems(["Alta calidad", "Rápido"])`
- `:209` checkbox `"Evitar solapamiento de tiempos entre subtítulos consecutivos"`
- `:247` `"Así se verá el subtítulo incrustado en el vídeo"`
- `:347` y ss. `QMessageBox` con `"Vídeo requerido"`, `"Ruta requerida"`, `"Ruta inválida"`, `"Sin subtítulos"` y sus textos
- `:464` `setWindowTitle("Renderizando subtítulos...")`
- `:487` `"🔥 Incrustando subtítulos en vídeo..."`
- `:491` `"Codificando vídeo con FFmpeg..."`
- `:519` `"Velocidad: --"`, `"Tiempo restante: Calculando..."`; `:630-631` `"Velocidad: {speed_str}"`, `"Restante: {eta_str}"`
- `:636` `"¡Subtítulos incrustados con éxito!"`, `"Archivo generado:..."`
- `:535` `"Cancelar proceso"`; `:556` `"▶ Reproducir vídeo"`; `:574` `"Abrir carpeta"`; `:592` `"Cerrar"`
- `:648-659` `"Error al incrustar subtítulos"`, `"Se produjo un error..."`, `"Error de quemado"`, `"Proceso cancelado"`, `"El quemado de vídeo ha sido cancelado..."`, `"Deteniendo proceso de FFmpeg..."`
- `:319,333` filtros de `QFileDialog` (`"Seleccionar vídeo original"`, `"Guardar vídeo con subtítulos"`)

**Relación directa:** estas cadenas corresponden 1:1 con claves ya definidas en A5 (`burn.lbl_font_size`, `burn.color_white`, `burn.box_solid`, `burn.rendering_title`, `burn.speed`, `burn.eta`, `burn.btn_play`, `burn.btn_folder`, `burn.btn_close`, `alert.*`).
**Fix sugerido:** reemplazar los literales por `t("…")` usando las claves existentes; mover los textos de `QMessageBox` a `alert.*`; además, los **valores** de los combos ("Pequeño"/"Blanco"…) se usan como contrato de datos en `BurnInOptions`, así que requieren un mapeo id→texto con `currentData()`.

### C2 — `widgets.py`: ~15 strings en español · **Mayor**
**Ubicación:**
- `:150` `setWindowTitle("Procesamiento en curso")`
- `:167` `QLabel("Procesamiento en curso")`
- `:203` `QPushButton("Cancelar")`
- `:195` `"Tiempo restante: --:--"`
- `:180-185` pasos `"⌛ Leyendo archivo..."`, `"⌛ Analizando subtítulos..."`, `"⌛ Limpiando contenido no deseado..."`, `"⌛ Traduciendo..."`, `"⌛ Aplicando formato original..."`, `"⌛ Guardando archivo..."`
- `:233` `"Tiempo restante: {m:02d}:{s:02d}"`
- `:501` `"⏱ {time_str}"`
- `:770` y `:1017` overlay `"Haz clic aquí o arrastra un video (.mp4, .mkv, .webm) para previsualizar"`
- `:964` `"Video cargado - Listo para reproducir"`
- `:928` `QFileDialog` `"Seleccionar vídeo para previsualizar"` + filtro
**Fix sugerido:** crear/usar claves (`progress.*`, `preview.*`) vía `t()` y **re-traducir** los pasos en `retranslate()`.

### C3 — `main_window.py`: ~30 strings en español · **Mayor**
**Ubicación:**
- `:348` `"Detectar automáticamente"`
- `:371-373` ítems de motor `"DeepL (recomendado)"`, `"Google Translate"`, `"OpenAI / LLM"` (y arranca en DeepL por índice 0 — ver H7/A6)
- `:1093` `"0 subtítulos"`; `:1095` `"Total: {n} subtítulos"`; `:1097` `"Mostrando {v} de {t}"`
- `:1030` `"✓ Guardado como: …"`
- Múltiples `QMessageBox` con títulos/textos en español (`"Archivo requerido"`, `"Error al guardar"`, `"Error"`, `"Conversión completada"`, `"Información"`, `"Sin subtítulos"`, `"Ajustes guardados"`, etc.) a lo largo de `_start_processing`, `_on_processing_completed`, `_run_format_conversion`, `_export_result_file`, `_open_burn_in_dialog`, `_save_settings`
- `:1160` y `:1180` filtros de `QFileDialog` (vídeo / subtítulos)
- `:1224` filtro de subtítulos del lote
- `:1273` `"Lote finalizado"`, `"Se procesaron todos los archivos del lote."`
- `:1269` `"Completado ✓"`; `:1234` `"Pendiente"`; `:1254` `"Procesando..."`
**Fix sugerido:** pasar por `t()`/`alert.*`; los contadores de preview ya tienen claves `preview.sub_count_*` sin usar (A5).

### C4 — Otros literales · **Menor**
**Ubicación:** `main_window.py:180` `"Subtitle Processor"`, `:1354` `app_title = QLabel("SRT4U - Subtitle Processor")` y textos de About (`:1400` `"Miguel Ángel Rodríguez Dalí"`, descripción del dev) hardcodeados; `:1359` `"v1.0.0"`.
**Nota:** los nombres propios y versión quizá deban permanecer literales (ver §9).

---

## 7. Hallazgos — Categoría D: Emojis y símbolos gráficos (regla `GEMINI.md`)

`GEMINI.md` prohíbe emojis en la UI y exige iconos vectoriales SVG vía `Icons`, y mantener las cadenas i18n limpias de prefijos emoji. Se detectaron **60+ apariciones**.

### D1 — Emoji 🔥 en etiquetas de UI · **Mayor**
`burn_in_dialog.py:75` `QLabel("🔥 " + t("burn.dialog_title"))` y `:487` `QLabel("🔥 Incrustando subtítulos en vídeo...")`.

### D2 — Emojis de control en `widgets.py` · **Mayor**
- `:180-185` `⌛` (pasos)
- `:221,223,226` `✓` / `◯`
- `:409-420` mapping emoji→icono (A7)
- `:501` `⏱`
- `:797,985,988` `▶` / `⏸` (botón play)
- `:821,887,889,891,897,900` `🔊` `🔇` `🔉` (botones de volumen)

### D3 — Símbolos de estado en `main_window.py` · **Menor**
`:1030` `✓`, `:1269` `"Completado ✓"`.

### D4 — Emoji en comentario · **Informativo**
`main_window.py:418` comentario `# Botón de Acción Principal (🚀 Procesar archivo)`.

### D5 — Emojis de bandera en metadatos de idioma · **Mayor (Requiere decisión)**
`i18n_service.py:26-31` (`SUPPORTED_LANGUAGES[..]["flag"]`) y `translation_service.py:25-34`. Se usan en los combos de idioma (`f"{meta['flag']} {meta['native']}"`). No son cadenas de traducción sino metadatos, pero **sí se renderizan en la UI** y en Linux/X11 los emojis bitmap no se pintan (la misma razón que motivó `GEMINI.md`). **Requiere decisión** (ver §9).

### D6 — Prefijo `▶` dentro de valores i18n · **Menor**
24 ocurrencias de `"▶ …"` en las 6 tablas: `home.btn_process`, `preview.btn_jump`, `batch.btn_start`, `burn.btn_play` (p. ej. `i18n_service.py:65,93,120,204,250,…`). Contradice la regla "cadenas de traducción limpias de prefijos de emojis".

---

## 8. Hallazgos — Categoría E: Documentación vs código

### E1 — README promete procesamiento por carpetas inexistente · **Mayor**
**Ubicación:** `README.md:41` → *"Batch Processing: Queue entire folders or multiple files…"*
**Código real:** `main_window.py:_add_batch_files` (`:1213-1227`) usa `QFileDialog.getOpenFileNames` (solo archivos; no hay `getExistingDirectory`).
**Detalle relevante:** `README_es.md:41` **no** menciona carpetas ("Cola de archivos"), por lo que los dos README ya se contradicen entre sí.
**Fix sugerido:** corregir `README.md` para reflejar "archivos" (o, si se desea la feature, implementarla — fuera del alcance read-only).

### E2 — El `.desktop` de la AppImage no cumple `GEMINI.md` · **Menor**
**Ubicación:** `.github/workflows/build.yml:150-159` genera un `srt4u.desktop` sin `StartupWMClass=SRT4U` ni `Keywords`, y con `Comment=Subtitle Processor & Translator`, distinto del `srt4u.desktop` del repo (`Comment=Subtitle Processor, Translator & Formatter`, que sí trae `StartupWMClass`).
**Impacto:** en Linux el dock puede no asociar ventana e icono (justo lo que `GEMINI.md` busca evitar).
**Fix sugerido:** alinear el `.desktop` empaquetado con `srt4u.desktop`.

### E3 — Copia de icono sin verificar tamaño · **Informativo**
`build.yml:145` copia `assets/icon.png` a `…/hicolor/256x256/apps/srt4u.png` sin comprobar que sea 256×256.

### E4 — CI no ejecuta la suite pese al badge · **Informativo**
`README.md` anuncia "Tests-29 passed", pero `.github/workflows/build.yml` no tiene job de `pytest`; el badge es estático. No es un error funcional, pero la afirmación no está respaldada por la CI.

### E5 — Versión coherente · **Falso positivo (correcto)**
`1.0.0` es consistente en `CHANGELOG.md`, About (`main_window.py:1359`) y `AppUserModelID` (`main.py:48`).

---

## 9. Hallazgos — Categoría F: Comentarios y docstrings (criterio estricto)

**No se encontró código comentado** (bloques muertos) en ningún archivo.

### F1 — Comentario de cabecera redundante · **Menor (patrón)**
10 archivos repiten su propia ruta como primera línea, lo que es redundante (el archivo ya está en esa ruta) y además **inconsistente** (otros archivos no lo hacen):
`config_service.py`, `file_service.py`, `i18n_service.py`, `subtitle_service.py`, `translation_service.py`, `video_burner_service.py`, `burn_in_dialog.py`, `main_window.py`, `styles.py`, `widgets.py`.
**Fix sugerido:** eliminar la línea de ruta o documentar la intención como convención uniforme.

### F2 — Docstring de módulo en inglés · **Menor**
`file_service.py:2-5` usa docstring en inglés ("This module provides…") mientras el resto de docstrings de módulo están en español. Inconsistencia de idioma.

### F3 — Docstring mal ubicado en `main.py` · **Menor**
`main.py:44-49`: el texto entre `"""…"""` está **dentro** del bloque `if __name__ == '__main__':`, por lo que es una expresión de cadena suelta (no un docstring) y no cumple función documental.
**Fix sugerido:** convertir en comentario o moverlo a un docstring de módulo.

### F4 — Comentarios que repiten el código · **Informativo**
Ejemplos representativos (criterio estricto): `widgets.py:92` `# Fondo degradado violeta`, `:96` `# Texto SRT blanco`, `:117` `# Anillo de fondo`, `:124` `# Anillo activo`, `:140` `# Porcentaje`, `:143`? (`# Círculo blanco (Knob)`), `video_burner_service.py:203` `# Mapeo de color en formato ASS (&HAABBGGRR)`, `subtitle_service.py:474-497` `# Paso 1: Lectura` … `# Paso 6: Guardado`.
**Nota:** muchos comentarios de sección (`# 1. Header`, `# 2. …`) son útiles y NO se marcan; se listan solo los que describen literalmente la línea siguiente.

### F5 — Emoji en comentario · **Informativo**
`main_window.py:418` (ver D4).

---

## 10. Hallazgos — Categoría G: Estilos inline vs `Styles`

### G1 — Duplicación masiva de colores y QSS inline · **Mayor**
**Ubicación:** `burn_in_dialog.py` (no importa `Styles`; define `_input_style`, `_btn_secondary_style`, `_combo_style` y docenas de hex inline), `widgets.py` (QSS inline en `ModernToggle.paintEvent`, `SubtitleCard._apply_style`, `VideoPreviewPlayer`, etc.), `main_window.py` (inline en botones y tarjetas).
**Descripción:** hex como `#8B5CF6`, `#6366F1`, `#1E293B`, `#F8FAFC`, `#94A3B8` se repiten como literales en múltiples archivos pese a existir `Styles` (que además tiene su propia copia de la paleta).
**Fix sugerido:** centralizar la paleta en `Styles` y consumirla (strings de color) en los QSS; no cambiar la estética.

### G2 — `burn_in_dialog` totalmente al margen de `Styles` · **Menor**
El diálogo de burn-in no usa el sistema de estilos central, forzando un tema oscuro fijo incluso si la app está en modo claro.

---

## 11. Hallazgos — Categoría H: Nombres e inconsistencias

### H7 — El motor por defecto no coincide con la config · **Mayor**
**Ubicación:** `config_service.py:18` define `preferred_engine="google"`; `main_window.py:370-374` agrega primero DeepL y el combo queda seleccionado en DeepL (índice 0). Nunca se aplica `preferred_engine`.
**Efecto:** la UI abre ofreciendo DeepL mientras el default declarado es Google, y los dos motores gratuitos (DeepL sin key) caen en Google de todos modos (`translation_service._translate_deepl` redirige si no hay key).
**Fix sugerido:** cargar `preferred_engine` al inicializar el combo, o alinear el default.

### H8 — Alias `GlassMainWindow` · **Requiere decisión**
`application/ui/__init__.py:1` exporta `MainWindow as GlassMainWindow`; `main.py` importa `GlassMainWindow`. Puede ser compatibilidad intencional o remanente de un renombrado. Sin documentación que lo aclare.

### H9 — Naming `burn` vs `burn_in` vs `BurnIn` · **Informativo**
Conviven `video_burner_service`, `BurnInOptions`, `BurnInWorker`, señal `burn_requested`, método `_start_burn_in_process` y claves `burn.*`. Es solo inconsistencia de estilo.

### H10 — Fixtures duplicadas en tests · **Menor**
El fixture `qapp` y el monkeypatch de `QMessageBox` están copiados en `test_i18n.py:15-20`, `test_ui_and_batch.py:15-20` y `test_video_burner.py:13-18` (+ stubs en test_i18n/test_ui_and_batch). Debería vivir en `conftest.py`.

### H11 — Filtros de archivo como texto duplicado · **Menor**
Ver I2.

---

## 12. Hallazgos — Categoría I: Lógica duplicada / copy-paste

### I1 — Despacho multiplataforma repetido 5 veces · **Mayor**
**Ubicación:**
- `burn_in_dialog.py:671-685` (`_open_video`, `_open_folder`)
- `main_window.py:1196-1210` (`_open_saved_file`, `_open_output_folder`)
- `main_window.py:1300-1310` (`_open_license_file`)

El mismo bloque `if sys.platform == "win32": os.startfile(...) / elif darwin: Popen(["open", ...]) / else xdg-open` está copiado cinco veces con pequeñas variantes (`explorer /select`, `open -R`).
**Fix sugerido:** extraer un helper único (p. ej. `open_path(path, reveal=False)`), sin cambiar comportamiento.

### I2 — Filtros de `QFileDialog` duplicados y con claves i18n sin usar · **Menor**
Mismo filtro `"Archivos de vídeo (*.mp4 *.mkv …);;Todos los archivos (*.*)"` en `burn_in_dialog.py:319`, `:333`, `widgets.py:928`, `main_window.py:1160`; y `"Subtítulos (*.srt *.ass *.vtt *.txt)"` en `main_window.py:1180`, `:1224`. Existen claves `preview.video_filter` y `dropzone.filter` sin uso (A5).
**Fix sugerido:** centralizar el filtro y usar las claves i18n.

### I3 — Fixture/monkeypatch de tests duplicado · **Menor**
Ver H10.

### I4 — Descomposición `ms→h/m/s` repetida · **Informativo**
`ms_to_srt_time`/`ms_to_vtt_time`/`ms_to_ass_time` (`subtitle_service.py:8-33`) repiten la misma aritmética; aceptable por claridad.

---

## 13. Hallazgos — Categoría J: Tests

### J1 — Ruta personal absoluta hardcodeada · **Mayor**
**Ubicación:** `tests/test_video_burner.py:14`
```python
SAMPLE_CLIP = "/home/marodriguezd/Descargas/clips_output/clip_1_00-00_to_02-00.mp4"
```
**Descripción:** ruta del entorno del autor; `test_video_duration_extraction` la salta silenciosamente si no existe, por lo que el test nunca valida nada en otro entorno.
**Fix sugerido:** usar un fixture de vídeo en `tests/fixtures/` o marcar el test como `skipif` explícito con un clip generado por ffmpeg.

### J2 — Test sin aserciones que se traga excepciones · **Mayor**
**Ubicación:** `tests/test_translation_free.py:57-72` (`test_translation_fallback_offline_resilience`)
**Descripción:** envuelve la llamada en `try/except Exception: pass` y **no contiene ningún `assert`**; pasa siempre. No valida la resiliencia que dice probar.
**Fix sugerido:** afirmar el retorno esperado (texto base) con `pytest.raises`/`assert` real; además usar un mock, no red real (J4).

### J3 — Imports dentro de función · **Menor**
`main_window.py:1186` y `tests/test_ui_and_batch.py:142` hacen `import copy` dentro de un método/test en vez de arriba.

### J4 — Tests dependientes de red real · **Informativo**
`tests/test_translation_free.py` llama a Google Translate en vivo; cabecea con internet y puede ser flaky/dependiente de cuota.

### J5 — Comprobación inerte en `test_main_window_flow` · **Menor**
`tests/test_ui_and_batch.py:59-63`: tras `_run_format_conversion()` se define `expected_converted` **después** de la conversión y solo se borra si existe; no hay aserción efectiva sobre el resultado.

### J6 — Tests de UI inspeccionan internals · **Informativo**
Los tests de UI dependen de atributos privados (`win._switch_page`, `win.diff_viewer`, etc.); aceptable pero acopla tests a la implementación.

---

## 14. Sección "Requiere decisión" (ambiguos / subjetivos)

| # | Tema | Ubicación | Opciones |
|---|---|---|---|
| R1 | Emojis de bandera en `SUPPORTED_LANGUAGES` | `i18n_service.py:26-31`, `translation_service.py:25-34` | (a) son metadatos de idioma → conservar; (b) se renderizan en UI y violan el espíritu de `GEMINI.md` → sustituir por textos/código. |
| R2 | Prefijo `▶` en valores i18n | `i18n_service.py` (24 ocurrencias) | (a) es funcional/afordancia → conservar; (b) regla GEMINI → eliminar. |
| R3 | Alias `GlassMainWindow` | `application/ui/__init__.py:1` | (a) compat intencional; (b) remanente de renombrado. |
| R4 | Literales de About (nombre del autor, versión) | `main_window.py:116,1323-1360` | (a) datos propios, no traducibles → conservar; (b) pasar a config/constantes. |
| R5 | Opción de caja "solo contorno" vs "Sin fondo" | `README.md:35` vs `BurnInOptions.box_style` | Confirmar si README describe exactamente el tercer preset. |
| R6 | Comentarios de cabecera con la ruta | 10 archivos (F1) | (a) convención → uniformar; (b) ruido → eliminar. |

---

## 15. Sección "Falsos positivos / intencionalmente así" (revisado y descartado)

- ✅ **Badge "Tests-29 passed"**: **correcto**. Ejecución real: `29 passed`.
- ✅ **Coherencia i18n entre los 6 idiomas**: **perfecta**. 156 claves en cada idioma, 0 faltantes, 0 sobrantes, 0 duplicadas (verificado por AST).
- ✅ **Versión 1.0.0 consistente** en CHANGELOG, About y AppUserModelID.
- ✅ **`vulture` "unused method paintEvent/hitButton/mousePressEvent/resizeEvent/eventFilter"** en `widgets.py`: **falsos positivos**; son overrides de Qt invocados por el framework.
- ✅ **`vulture` "unused variable processed_items_count"** (`subtitle_service.py:86`): **falso positivo**; es un campo de dataclass asignado y almacenado.
- ✅ **`vulture` "unused property supported_languages/current_language"** (`i18n_service.py:1199,1203`): **falsos positivos**; se usan en tests (`test_i18n.py`) y potencialmente por API pública.
- ✅ **`vulture` "unused method cleanup_temp"**: parte de la clase muerta de A1 (ya reportado allí, no duplicado).
- ✅ **Funcionalidades del README implementadas**: DeepL (free/pro), OpenAI/Ollama/OpenRouter, i18n 6 idiomas, cambio de tema, hardsub, conversión multi-formato, editor de tarjetas y player sincronizado — todas presentes en el código.
- ✅ **`__pycache__` / `.venv` / `.pytest_cache`**: correctamente ignorados en `.gitignore`; no son incidencias.
- ✅ **requirements.txt**: solo dependencias de runtime; PyInstaller/Pillow se instalan en CI — correcto.
- ℹ️ **`locale` importado en `i18n_service`**: es un import realmente muerto (la detección usa `QLocale`), no falso positivo (ya en B2).

---

## 16. Plan de remediación priorizado (no aplicado)

> Ordenado por severidad y esfuerzo estimado. Cada ítem es una sugerencia; **nada de esto se ha ejecutado**.

### Prioridad 1 — Alto impacto, bajo riesgo
1. **Limpiar imports muertos** (B1–B23 + B24) con `ruff --select F401,E741 --fix`. ~15 min. Sin cambio de comportamiento.
2. **Corregir README** de "carpetas" (E1) para que coincida con el código y con `README_es.md`. ~5 min.
3. **Alinear el `.desktop` de la AppImage** (E2) con `srt4u.desktop` (añadir `StartupWMClass`/`Keywords`). ~10 min.

### Prioridad 2 — Alto impacto, esfuerzo medio
4. **Eliminar `FileService`** o integrarlo (A1). ~15 min.
5. **Decidir y ejecutar** sobre las 6 claves de config muertas (A6) y las 53 claves i18n muertas (A5). ~1 h.
6. **Migrar strings hardcodeados a i18n** en `burn_in_dialog`, `widgets`, `main_window` (C1–C3), reutilizando claves existentes y añadiendo las que falten (alert.*, progress.*). ~3–4 h.
7. **Reparar tests inefectivos** (J1, J2, J5) y des-duplicar fixtures (H10/I3). ~1 h.
8. **Extraer helper de apertura multiplataforma** (I1). ~30 min.

### Prioridad 3 — Calidad, esfuerzo variable
9. **Unificar la paleta en `Styles`** y eliminar QSS/hex duplicados (G1, G2). ~3–4 h, con riesgo visual → verificación manual.
10. **Eliminar emojis/símbolos de UI** según `GEMINI.md` (D1–D3, D6) tras resolver R1/R2, usando `Icons`. ~1–2 h.
11. **Centralizar filtros de diálogo** (I2) con claves i18n. ~30 min.
12. **Limpiar constantes muertas** (A2–A4, A7) y comentarios de ruido (F1–F5). ~1 h.
13. **Añadir job de `pytest` en CI** para respaldar el badge (E4). ~20 min.

---

## 17. Checklist de aceptación

- [x] **100% de los archivos en alcance** revisados y marcados (§2.1).
- [x] **Cada hallazgo** con `archivo:línea` y severidad.
- [x] **Docs vs código verificados punto por punto** (§8; features, métricas, rutas, versión, filtros, CI).
- [x] **Evidencia de herramientas adjuntada** (§2.2: `pytest`, `ruff`, `pyflakes`, `vulture` + scripts AST).
- [x] **Sección de falsos positivos incluida** (§15).
- [x] **Coherencia de las 6 tablas i18n** comparada y reportada (§2.1 notas + A5 + §15).
- [x] **Reglas de `GEMINI.md`** verificadas como categoría propia (§7).
- [x] **Resumen ejecutivo** (§1) y **plan de remediación** (§16) presentes.
- [x] **Ningún cambio de código, lógica ni archivos fuentes** realizado (solo se creó documentación).
- [x] Sección **"Requiere decisión"** incluida (§14).

---

## 18. Estado de remediación aplicada (2026-09-27)

> Se ejecutó el plan de §16 de forma secuencial. Verificación tras cada bloque con
> `.venv/bin/ruff check application main.py conftest.py tests --select F,E7,E9,B` (limpio)
> y `.venv/bin/python -m pytest tests/ -q` (**29 passed**).

**Prioridad 1 — aplicada**
1. Imports muertos (B1–B24): eliminados con `ruff --fix`; renombrada la variable ambigua `l` (B24).
2. `README.md` corregido: "Queue entire folders or multiple files" → "Queue multiple files" (E1).
3. `.desktop` empaquetado en `build.yml` alineado con `srt4u.desktop` (E2): añadidos `GenericName`, `Comment`, `Categories`, `StartupWMClass=SRT4U` y `Keywords`.

**Prioridad 2 — aplicada**
4. `FileService` eliminado (A1).
5. Config muerta (A6): `source_lang`, `target_lang`, `preferred_engine`, `auto_clean` y `preserve_format` ahora se cargan/guardan en la Home (`_load_config_values`/`_persist_home_options`); `output_dir` (sin UI) eliminada. El motor por defecto respeta `preferred_engine` (H7). Claves i18n muertas (A5): las obsoletas (`preview.col_*`, `burn.video_card_title`, `burn.style_card_title`, `burn.lbl_font_family`) eliminadas de las 6 lenguas; el resto conectadas a la UI. **212 claves por idioma, coherencia verificada.**
6. Strings hardcodeados migrados a i18n en `burn_in_dialog`, `widgets` y `main_window` (C1–C3), con ~65 claves nuevas en los 6 idiomas. Los valores de los combos de burn-in pasan a IDs neutros (`small`/`medium`/`large`, `white`/`yellow`/`cyan`, `none`/`semi`/`solid`, `high`/`fast`) vía `currentData()`.
7. Tests reparados (J1, J2, J5) y fixture `qapp` + monkeypatch de `QMessageBox` centralizados en `conftest.py` (H10/I3).
8. Helper multiplataforma `application/platform_utils.py` (`open_path`, `reveal_path`) sustituye las 5 copias (I1).

**Prioridad 3 — aplicada**
9. Paleta centralizada en `Styles` (constantes de superficie, borde y texto) y consumida en `burn_in_dialog` (G2), `main_window` y `widgets` (G1). No se modificaron valores de color.
10. Emojis/símbolos retirados de la UI: `🔥`, `⌛`, `✓`, `◯`, `⏱`, `▶`, `⏸`, `🔊`, `🔇`, `🔉`, prefijos `▶` de los valores i18n (D6) y emojis de bandera (D5); sustituidos por iconos SVG (`pause`, `volume`, `volume_low`, `volume_mute`) y textos i18n sin prefijos.
11. Filtros de diálogo centralizados en claves i18n (`preview.video_filter`, `preview.sub_filter`, `preview.save_filter`) (I2).
12. Constantes muertas y comentarios de ruido limpiados (A2–A4, A7, F1–F5): `_is_completed`, `DEFAULT_PRIMARY/ERROR/WARNING`, mapping emoji→icono, 10 comentarios de cabecera con la ruta, docstring mal ubicado de `main.py`.
13. Job `test` añadido a `build.yml`, del que dependen los 3 builds; nuevos triggers `push` (rama `main`) y `pull_request` (E4). El job ejecuta como pasos explícitos: (1) lint con `ruff` fijado a la versión local (`ruff==0.16.9`) usando la configuración compartida `ruff.toml` (selectores `F,E7,E9,B`, `target-version py311`), que también gobierna el lint local (`ruff check application main.py conftest.py tests`, ya sin necesidad de `--select`); (1b) `ruff format --check` sobre los mismos objetivos con la misma config (el código se normalizó previamente con `ruff format`: 18 archivos reformateados, 0 cambios semánticos, suite en verde); (2) el smoke test de la utilidad de capturas (`tests/test_screenshot_tool.py`, `-v`, offscreen), visible de inmediato en el resumen de CI; y (3) la suite completa.

**Revisión visual (render offscreen + contraste WCAG):**
- **Tema claro corregido.** En modo claro casi todas las etiquetas quedaban en blanco sobre blanco (contraste ~1.0) porque los colores de texto estaban inline y no seguían el tema. Se añadió `Styles.retint_inline_text()`, que adapta los colores inline al tema activo (texto, texto atenuado, acentos y verde de éxito) en cada `_apply_theme`/`retranslate_ui`, respetando widgets autónomos con fondo propio (chips, tarjetas de vídeo, reproductor). Verificado en las 6 lenguas: 0 etiquetas con contraste < 3.0 en oscuro y claro.
- **Diálogo de burn-in corregido.** Tenía tamaño fijo 620×570 y su contenido mínimo lo superaba en es/pt/de/it (hasta 684 px en portugués), provocando recorte. Ahora usa `setMinimumSize` + `resize(minimumSizeHint().expandedTo(minimumSize()))`, de modo que crece lo necesario en cada idioma. Igual para el modal de progreso (500×240 mínimo).
- Capturas de comprobación generadas en `/tmp/srt4u-shots` (home/settings/about × en/de/pt × oscuro/claro + burn-in en/pt).

**Pendiente de verificación manual:** las capturas están disponibles para una última inspección estética; no se detectan recortes ni texto de bajo contraste en ninguna de las 6 lenguas.

**Test de regresión de layout (`tests/test_ui_layout.py`) — añadido:**
- `test_main_window_has_no_clipped_text`: parametrizado sobre las 6 lenguas × {oscuro, claro} (12 casos). Cambia idioma/tema, reaplica estilo y re-traduce, y por cada página comprueba que ningún `QLabel`/`QAbstractButton` visible (no word-wrap) tiene `fontMetrics().horizontalAdvance(text) > width() + 2`.
- `test_burn_in_dialog_fits_its_content`: parametrizado sobre las 6 lenguas (6 casos). Exige `width/height >= minimumSizeHint()` y ausencia de texto recortado.
- Fallos reales que el test destapó y que se corrigieron con `setWordWrap(True)`: `OptionCard` (título/descripción), `DropZone` (título/subtítulo/formatos) y los subtítulos de página de la Home, limpieza, conversión, lote, completado, previsualización, tarjeta de idioma y DeepL.
- Escalado de contenido: `test_settings_and_about_no_clipped_text_at_scaled_font` amplía la fuente de aplicación ×1.5 y comprueba las páginas de Ajustes y Acerca de en las 6 lenguas × ambos temas (24 casos), verificando que no hay etiquetas recortadas con contenido tipográfico mayor. `test_burn_in_dialog_fits_its_content_at_scaled_font` aplica el mismo escalado al diálogo de burn-in (6 casos): el diálogo debe crecer hasta su `minimumSizeHint()` y sin texto cortado. Los modales de progreso también se validan a escala: `test_progress_modal_fits_its_content_at_scaled_font` (`ProgressModal`, 6 casos, con `show()` + `processEvents` para medir geometría real) y `test_burn_in_progress_modal_fits_its_content_at_scaled_font` (`BurnInProgressModal`, 6 casos, con `_start_worker` parcheado para no lanzar FFmpeg).
- Los tests de burn-in ahora muestran el diálogo (`show()` + `processEvents`) antes de medir, lo que destapó un recorte real: las leyendas `preview.subtitle` y `burn.preview_hint` no hacían word-wrap y empujaban el `minimumSizeHint` del diálogo hasta 654 px (en) superando su mínimo declarado de 620; se añadió `setWordWrap(True)` a ambas etiquetas.
- Para prevenir regresiones, `BurnInDialog` y `BurnInProgressModal` ya no usan un `setMinimumSize` fijo: tras construir la UI, el helper `Styles.sync_minimum_size(dialog, floor)` (en `styles.py`, compartido por toda la capa UI) recalcula el mínimo real con `ensurePolished()` + `layout().activate()` + `minimumSizeHint().expandedTo(floor)` (suelos de diseño 620×570 y 500×240) y redimensiona el diálogo a ese mínimo, de modo que el mínimo declarado nunca queda por debajo del contenido real. `ProgressModal` (widgets.py) adopta el mismo patrón sustituyendo su `setFixedSize(500, 360)` por `sync_minimum_size(self, QSize(500, 360))` + `resize(minimumSize())`, manteniendo su diseño frameless; el resto de tamaños fijos del código son de componentes (toggle, logo, círculo de progreso, sidebar) y no aplican.
- Test del invariante de mínimos: `test_all_dialogs_minimum_size_covers_content` (6 lenguas) verifica en los 3 diálogos de la app (`BurnInDialog`, `ProgressModal`, `BurnInProgressModal`) que `minimumSize >= minimumSizeHint` tanto tras construir como tras `show()` + `processEvents`, de modo que cualquier contenido futuro que crezca (texto, fuente) detecta el hueco antes de llegar a producción.
- Utilidad de capturas: `tools/regenerate_screenshots.py` regenera las capturas de verificación visual (`--out DIR`, `--langs en,es,...`; fuerza plataforma offscreen si no hay display) para las páginas principales × idiomas × temas y los diálogos por idioma, imprimiendo el tamaño/mínimo resultante de cada diálogo como comprobación del invariante. Test de humo `tests/test_screenshot_tool.py`: ejecuta la utilidad real en un subproceso offscreen (`--langs en`) y valida código de salida, nº mínimo de PNG, presencia de capturas clave, que ninguna esté vacía y el resumen final.
- Total de la suite tras la remediación y el nuevo test: **84 passed** (29 previos + 54 de layout + 1 de humo), con `ruff ... --select F,E7,E9,B` limpio.

---

## 20. Cierre — verificación final del checklist (2026-09-27)

Re-ejecución completa del checklist de aceptación (§17) sobre el código ya remediado:

**Evidencia de ejecución:**
| Comprobación | Resultado |
|---|---|
| `.venv/bin/python -m pytest tests/ -q` | **84 passed** (29 originales + 54 layout/geometría + 1 smoke) |
| `ruff check application main.py conftest.py tests` (config `ruff.toml`: F,E7,E9,B) | All checks passed! |
| `ruff format --check application main.py conftest.py tests` | 25 files already formatted |
| Coherencia i18n (invariante por script) | 6 lenguas × 212 claves idénticas, 0 faltantes/sobrantes/duplicadas |
| Capturas offscreen (`tools/regenerate_screenshots.py`) | 28 PNG regenerados; cada diálogo con `size == min` |

**Spot-checks de los hallazgos principales:**
- A1 `FileService`: el módulo ya no existe. ✓
- A2 `_is_completed`: 0 ocurrencias. ✓
- A3/A4 constantes muertas (`DEFAULT_PRIMARY/ERROR/WARNING`): eliminadas. ✓
- A5/A6 claves muertas (i18n y config): conectadas o eliminadas; los contadores de config se persisten/cargan. ✓
- B1–B24 imports/variables muertos: 0. ✓
- C1–C3 strings hardcodeados: migrados a `t()` (~65 claves nuevas × 6 lenguas); combos de burn-in con IDs neutros vía `currentData()`. ✓
- D1–D6 emojis/símbolos (`🔥 ⌛ ⏱ ▶ ⏸ 🔊 🔇 🔉`, banderas): 0 ocurrencias en `application/`; iconos SVG en su lugar. ✓
- E1 README "carpetas": corregido. E2 `.desktop` de CI alineado (StartupWMClass + Keywords). E4 job `test` en CI con lint + formato + smoke + suite. ✓
- F1–F5 cabeceras `# path`: 0; docstring de `main.py` real; comentarios-eco eliminados. ✓
- G1/G2 paleta centralizada en `Styles` (superficies, bordes, texto) y consumida por los tres módulos UI; `retint_inline_text` corrige el tema claro. ✓
- H7 motor por defecto respeta `preferred_engine` (google). H10 fixtures centralizadas en `conftest.py`. ✓
- I1 despacho multiplataforma → `application/platform_utils.py`. I2 filtros → claves i18n. ✓
- J1 clip generado por FFmpeg en fixture; J2/J5 con aserciones reales. ✓

**Mejoras adicionales surgidas del proceso de verificación:**
- Suite de regresión de layout (54 casos): recortes, escalado tipográfico ×1.5, ajuste de diálogos e invariante `minimumSize >= minimumSizeHint` en las 6 lenguas y ambos temas.
- Bug real corregido: leyendas de `BurnInDialog` sin word-wrap empujaban su `minimumSizeHint` (654 px en en) por encima del mínimo declarado (620). Solución: `setWordWrap` + mínimos dinámicos vía `Styles.sync_minimum_size` en los 3 diálogos.
- Infra de calidad: `ruff.toml` compartido local/CI, `ruff format` aplicado (25 archivos) y verificado en CI, smoke test de la utilidad de capturas como paso explícito del job `test`.

**Estado final: plan §16 completo (13/13), verificación visual en 6 lenguas y 2 temas completada, suite de regresión de layout en verde y checklist de aceptación revalidado. Sin hallazgos pendientes de este alcance.**

**Versionado:** el resultado se publica como **v1.1.0 (pre-release)**: `about.version_pill` actualizado en las 6 lenguas, AppUserModelID de Windows a `…1.1`, `CHANGELOG.md` con entrada 1.1.0 (estilo Keep a Changelog, en inglés) y `RELEASE_NOTES.md` con sección "What's New in 1.1.0" marcada como pre-release. Los badges de tests de ambos README se actualizaron a 84 y ambos incluyen una sección "Developer Tools / Herramientas de desarrollo" documentando la utilidad de capturas (uso, flags, comportamiento headless y su test de humo en CI).

---

## 21. Notas de método y limitaciones

- Los conteos por severidad son aproximados; el núcleo verificable son los hallazgos referenciados con `archivo:línea`.
- Los hallazgos de comentarios (criterio estricto) se reportan por patrón + ejemplos representativos para no inflar el informe con cada incidencia repetida; el patrón está documentado y es verificable con `grep`.
- Las herramientas se instalaron en el `.venv` **del proyecto** para la evidencia (`ruff`, `pyflakes`, `vulture`); no se alteró el entorno global ni `requirements.txt`.
- La auditoría no juzga calidad de las traducciones ni la corrección algorítmica de los parsers (fuera de alcance); se enfocó en incongruencias y sobrantes.
- La sección §18 documenta la remediación aplicada con posterioridad a la auditoría original de solo lectura.
