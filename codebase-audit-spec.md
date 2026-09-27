# Spec: Auditoría integral del codebase (incongruencias y sobrantes)

**Nombre corto:** `codebase-audit`
**Estado:** Aprobado para ejecución (aún sin ejecutar)
**Fecha:** 2026-09-26
**Idioma del documento y del informe final:** Español
**Restricción dura:** Esta tarea NO modifica código, lógica ni comportamiento. Es 100% análisis y reporte.

---

## 1. Objetivo

Analizar el 100% del codebase del proyecto **SRT4U – Subtitle Processor** para detectar:

- **Incongruencias** (contradicciones entre dos o más partes del proyecto: código vs código, código vs docs, docs vs docs, infra vs realidad).
- **Sobrantes / ruido** (comentarios innecesarios, docstrings redundantes o desactualizados, código muerto, código comentado, imports/variables no usados).
- **Riesgos de coherencia** (nombres inconsistentes, lógica duplicada, cumplimiento de las reglas internas del proyecto en `GEMINI.md`).

El resultado es un **informe de auditoría** más una **checklist de aceptación** que permita validar y repetir el análisis. **No se aplica ningún cambio de código.** Las correcciones, si se proponen, se describen únicamente en texto.

---

## 2. Contexto del proyecto (relevamiento previo)

- **Tipo:** Aplicación de escritorio (GUI) para traducir, editar, limpiar y convertir subtítulos (`.srt`, `.vtt`, `.ass`, `.txt`) y quemarlos en vídeo.
- **Stack:** Python 3.10+, PyQt6 (GUI), `deep-translator`, `requests`. FFmpeg embebido para hardsub.
- **Empaquetado:** PyInstaller / AppImage / DMG vía GitHub Actions (`build.yml`).
- **Tests:** `pytest` en `tests/` (parsing, cleaning, conversion, translation_free, ui_and_batch, video_burner, i18n).
- **Tamaño aproximado:** ~6.932 líneas Python.

### 2.1 Estructura relevante

```
main.py                                  # entrypoint + carga de icono multiplataforma
conftest.py                              # asegura raíz en sys.path
requirements.txt
build_exe.bat
srt4u.desktop
GEMINI.md                                # reglas y aprendizajes del proyecto
README.md  README_es.md  CHANGELOG.md  RELEASE_NOTES.md
application/
  services/
    file_service.py          (37)
    config_service.py        (65)
    translation_service.py   (172)
    video_burner_service.py  (440)
    subtitle_service.py      (513)
    i18n_service.py          (1264)     # 6 idiomas: en, es, pt, de, it, zh-CN
  ui/
    __init__.py              (3)
    icons.py                 (185)
    styles.py                (185)
    burn_in_dialog.py        (685)
    widgets.py               (1034)
    main_window.py           (1639)
tests/                                   # 7 archivos de test + fixtures
.github/workflows/build.yml
assets/                                  # iconos, previews, preview HTML
```

### 2.2 Entorno / evidencia

- El intérprete del sistema (`python`) **no tiene PyQt6** instalado; los tests de UI fallan al recolectar con `ModuleNotFoundError: No module named 'PyQt6'`.
- Existe un `.venv` en el repo. Para la evidencia de tests/linters debe usarse el entorno del proyecto (`.venv`), no el Python global.
- La ejecución de `pytest` y de linters está **permitida** para respaldar hallazgos (no modifica código). Ver `README.md` (badge "29 passed") como afirmación a verificar.

---

## 3. Alcance

Se audita **todo** el proyecto. En concreto:

- **Código Python:** `application/` (services + ui) y `main.py`.
- **Tests:** `tests/` y `conftest.py`.
- **Docs y metadatos:** `README.md`, `README_es.md`, `CHANGELOG.md`, `RELEASE_NOTES.md`, `GEMINI.md`.
- **Infra / build:** `requirements.txt`, `build_exe.bat`, `.github/workflows/build.yml`, `.gitignore`, `srt4u.desktop`.
- **Assets:** iconos (`icon.icns/ico/png/svg`), previews (`preview*.png`, `demo-screenshot.png`, `icon-preview.html`) y `tests/fixtures/`.

### 3.1 Fuera de alcance

- **No** se modifica código, lógica, estructura, nombres de archivos ni assets.
- **No** se refactoriza, **no** se borran archivos, **no** se crean tests nuevos.
- **No** se toca `.venv/`, `__pycache__/`, `.pytest_cache/`, `.git/` (generados, no se auditan como fuente).
- La spec y el informe son documentación; no cuentan como "cambio de código".

---

## 4. Definiciones acordadas

- **Incongruencia:** contradicción verificable entre dos partes del proyecto. Ejemplos: un string de UI hardcodeado en un idioma mientras el resto usa i18n; una feature documentada en `README.md` que no existe en el código; una métrica de tests desactualizada; un icono/asset referenciado que no existe o un asset existente que ya no se referencia.
- **Sobrante / ruido:** elemento que no aporta (import no usado, variable/parámetro muerto, rama inalcanzable, bloque comentado, TODO huérfano, docstring que repite la firma).
- **Comentario innecesario (criterio ESTRICTO):** se reporta **cualquier comentario que no aporte valor**, incluyendo redundantes que repiten el código, obsoletos, y comentarios en un idioma distinto al dominante del archivo.
- **Requiere decisión:** hallazgo ambiguo o de criterio subjetivo (podría ser intencional). No se lista como hallazgo firme; va en sección aparte.

---

## 5. Metodología

1. **Recorrido manual exhaustivo** de cada archivo en alcance (revisión línea por línea de las fuentes; lectura dirigida en archivos grandes).
2. **Análisis estático con herramientas** permitido y requerido cuando aporte: `ruff`, `pyflakes`, `mypy`, `vulture` (u equivalentes disponibles en el `.venv`). Adjuntar la salida cruda como evidencia.
3. **Verificación de afirmaciones** mediante ejecución: `pytest` para contrastar el badge/métrica del README y el estado real de la suite. Sin modificar nada.
4. **Comparación cruzada** docs ↔ código ↔ infra ↔ assets.
5. **Coherencia i18n:** comparar las **6 tablas de claves** (`en`, `es`, `pt`, `de`, `it`, `zh-CN`) entre sí: claves faltantes, duplicadas o sobrantes por idioma, y valores vacíos/placeholder.
6. **Validación de reglas internas** documentadas en `GEMINI.md`.

---

## 6. Categorías de hallazgos

Todas las categorías fueron solicitadas como parte del análisis:

1. **Strings hardcodeados** que deberían pasar por i18n.
2. **Código muerto:** funciones/clases/ramas nunca usadas.
3. **Imports, variables y parámetros no usados.**
4. **Comentarios** redundantes, obsoletos o que repiten el código (criterio estricto).
5. **Docstrings** sobrantes o desactualizados.
6. **Código comentado** (bloques muertos).
7. **TODO / FIXME / HACK / XXX** pendientes.
8. **Nombres inconsistentes** (archivos, funciones, variables, `objectName` de Qt).
9. **Lógica duplicada / copy-paste.**
10. **Docs vs código** (features, métricas, rutas, versión) — **eje central**.
11. **Estilos/temas:** colores, tamaños y estilos inline vs lo centralizado en `Styles`.
12. **Reglas `GEMINI.md` (categoría propia):** sin emojis en la UI; uso de iconos vectoriales SVG vía `Icons.get_icon`/`get_pixmap`; cadenas i18n libres de prefijos de emojis; `StartupWMClass=SRT4U` en el `.desktop`; icono en Linux vía `icon.png`/`icon.svg`.

---

## 7. Formato de cada hallazgo

Por cada hallazgo:

```
[ID] [Severidad] [Categoría]
Ubicación: archivo:línea
Descripción: qué es y por qué es una incongruencia/sobrante.
Fix sugerido (texto, NO aplicado): cómo se corregiría.
Evidencia: salida de herramienta / cita, si aplica.
```

- **Ubicación siempre en formato `archivo:línea`**, también para archivos no-Python (README, workflows, etc.).
- Se incluye **fix sugerido en texto** (no se aplica).
- Se incluye **evidencia** (salida de linter o ejecución) cuando respalde el hallazgo.

---

## 8. Severidad

Clasificación de 4 niveles aplicada a cada hallazgo:

- **Crítico:** rompe funcionalidad o contradice de forma grave una promesa del producto (ej. feature documentada inexistente, icono roto).
- **Mayor:** afecta coherencia/comportamiento relevante (ej. string de UI sin i18n, lógica duplicada divergente).
- **Menor:** ruido de calidad (ej. import no usado, comentario obsoleto).
- **Informativo:** observación de higiene, sin impacto (ej. nombre poco descriptivo, asset huérfano).

---

## 9. Estructura del informe

1. **Resumen ejecutivo** con conteos por severidad y top archivos problemáticos.
2. **Métricas** (nº de hallazgos por categoría, archivos cubiertos).
3. **Índice por categoría** (agrupación principal).
4. **Índice por archivo** (navegación alternativa; doble índice).
5. **Sección "Requiere decisión"** (ambiguos/subjetivos).
6. **Sección "Falsos positivos / intencionalmente así"** (lo revisado y descartado, para no repetir revisión).
7. **Plan de remediación priorizado** por severidad y esfuerzo estimado (aunque no se aplique ahora).
8. **Checklist de aceptación**.

---

## 10. Checklist de aceptación

Debe garantizar (todas marcadas como requeridas):

- [ ] **100% de los archivos en alcance** revisados y marcados como auditados (tabla de cobertura).
- [ ] **Cada hallazgo** con `archivo:línea` y severidad.
- [ ] **Docs vs código verificados punto por punto** (cada feature/métrica declarada contrastada).
- [ ] **Evidencia de herramientas adjuntada** (salida de linters/tests).
- [ ] **Sección de falsos positivos incluida.**
- [ ] **Coherencia de las 6 tablas i18n** comparada y reportada.
- [ ] **Reglas de `GEMINI.md`** verificadas como categoría propia.
- [ ] Resumen ejecutivo y plan de remediación presentes.
- [ ] Ningún cambio de código, lógica o archivos realizado.

---

## 11. Entregables y ubicación

- **Informe final:** archivo **en el repo**, propuesto como `AUDIT_REPORT.md` (en español).
- **Spec:** este archivo (`codebase-audit-spec.md`).
- Formato Markdown, con referencias `archivo:línea` navegables.

---

## 12. Restricciones y principios

- **Read-only:** prohibido editar código, lógica, tests, assets o configuración. Solo lectura + creación de documentación.
- No inventar hallazgos: cada uno debe ser verificable con ubicación exacta.
- Ante duda o subjetividad, mover el ítem a "Requiere decisión" en lugar de forzarlo como hallazgo.
- Las correcciones se describen, nunca se aplican.
- Tono del informe: objetivo y factual.

---

## 13. Señales conocidas a verificar (semillas, sin confirmar)

Detectadas durante el relevamiento previo. Deben confirmarse con línea exacta en la auditoría; se listan como hipótesis iniciales, no como hallazgos cerrados:

1. **Strings en español hardcodeados pese a existir i18n:**
   - `application/ui/burn_in_dialog.py:321`, `:335` (filtros de archivo)
   - `application/ui/widgets.py:930` (filtro de archivo)
   - `application/ui/main_window.py:1160` (filtro de archivo), `:1273` (mensaje "Lote finalizado")
2. **Emojis de bandera en `SUPPORTED_LANGUAGES`** (`application/services/i18n_service.py`, ~líneas 30–37: 🇬🇧 🇪🇸 🇵🇹 🇩🇪 🇮🇹 🇨🇳) frente a la regla de `GEMINI.md` de i18n libre de emojis. *Posible "Requiere decisión" (¿son metadatos, no strings de traducción?).*
3. **Assets posiblemente sobrantes:** `assets/demo-screenshot.png`, `assets/preview.png`, `assets/preview_es.png` frente a `README.md`/`README_es.md` (que referencia `assets/preview_en.png`). Verificar referencias.
4. **Métrica del README:** badge "Tests-29 passed" — contrastar con el conteo real de `pytest` ejecutado en `.venv`.
5. **Alias de UI:** `application/ui/__init__.py` exporta `MainWindow` como `GlassMainWindow`; verificar consistencia de uso en todo el proyecto.
6. **Coherencia i18n entre los 6 idiomas:** claves ausentes/duplicadas/sobrantes.
7. **Coherencia de versión:** `1.0.0` en `CHANGELOG.md`, `main.py` (`AppUserModelID` usa `...1.0`), `README`, `RELEASE_NOTES`, workflows.

---

## 14. Decisiones de la entrevista (resumen)

| Pregunta | Decisión |
|---|---|
| Alcance | Todo el proyecto (código, tests, docs, infra, assets) |
| Entregable | Informe + checklist de aceptación |
| Idioma | Español |
| Docs vs código | Eje central del análisis |
| Herramientas automáticas | Sí, ejecutar y adjuntar evidencia |
| Categorías | Todas las 11 + reglas `GEMINI.md` |
| Fix sugerido | Sí, en texto (no aplicado) |
| Criterio de comentarios | Estricto (reportar todo comentario sin valor) |
| Estructura informe | Por categoría, con severidad (+ índice por archivo) |
| Severidad | Crítico / Mayor / Menor / Informativo |
| Formato hallazgo | `archivo:línea` + descripción + fix sugerido |
| Reglas `GEMINI.md` | Categoría propia |
| Falsos positivos | Sección obligatoria |
| Checklist | 100% archivos, ubicación+severidad, docs-vs-código, evidencia, falsos positivos |
| Ubicación informe | Archivo en el repo (`AUDIT_REPORT.md`) |
| Remediación | Plan priorizado por severidad y esfuerzo |
| Ambiguos | Sección "Requiere decisión" |
| Verificación | Ejecutar tests/linters como evidencia permitido |
| Nombre spec | `codebase-audit` |
| Coherencia i18n | Comparar las 6 tablas entre sí |
| Resumen | Resumen ejecutivo + métricas |
| Refs no-Python | Mismo formato `archivo:línea` que Python |
