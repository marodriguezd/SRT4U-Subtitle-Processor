# Reglas y Aprendizajes del Proyecto (SRT4U)

## Iconos y Compatibilidad Multiplataforma (Linux/X11, Windows, macOS)

1. **Sin emojis en interfaz:**
   - En PyQt6 sobre Linux/X11, el motor FreeType/Qt no renderiza fuentes bitmap a color (`Noto Color Emoji`), dejándolos completamente transparentes o invisibles.
   - En componentes UI (botones, barras laterales, etiquetas, diálogos), **usar siempre iconos vectoriales SVG** a través de `application/ui/icons.py` (`Icons.get_icon(...)` y `Icons.get_pixmap(...)`).
   - Mantener las cadenas de traducción en `i18n_service.py` limpias de prefijos de emojis.

2. **Icono de aplicación y barra de tareas en Linux:**
   - No limitar la carga a `icon.ico` (exclusivo de Windows).
   - En Linux/X11 y Wayland, cargar preferentemente `assets/icon.png` (alta resolución) y `assets/icon.svg` mediante `load_app_icon()`.
   - Establecer `app.setApplicationName("SRT4U")`, `app.setDesktopFileName("srt4u")` y aplicar el icono tanto en `QApplication` como en la ventana principal (`QMainWindow.setWindowIcon`).
   - El archivo `srt4u.desktop` debe mantener `StartupWMClass=SRT4U` para que el gestor de ventanas y dock lo asocien sin errores.

## Release 1.1.0 estable (2026-09-27)

3. **Checklist previo a tag:**
   - Badges `README.md`/`README_es.md` = suite local con media real (`156`; en CI sin media son `130` porque `test_e2e_real_media.py` hace skip sin `SRT4U_E2E_MEDIA`).
   - `CHANGELOG.md`: `[Unreleased]` vacío al publicar; la entrada e2e vive dentro de `[1.1.0]`.
   - `RELEASE_NOTES.md` estable sin banner `Pre-release`; `build.yml` con `prerelease: false`.
   - Flota local en verde: `ruff check`, `ruff format --check` (33 ficheros) y `pytest tests/ -q` (`156 passed` con media en `/home/marodriguezd/Video_srt4u`).

4. **Mover un tag pre-release ya publicado:**
   - `git tag -f v1.1.0` + `git push origin v1.1.0 --force` dispara rebuild completo (test + compat-min + 3 builds + publish).
   - El release conserva `published_at` original y NO pasa a `Latest` solo: tras el CI ejecutar `gh release edit v1.1.0 --latest` y verificar con `gh api .../releases/latest`.
   - i18n de referencia: `223 claves × 6 idiomas`, 0 vacías; UI con `0` emojis (solo `♪/♫` funcionales en `subtitle_service.py`).
