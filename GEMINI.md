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
