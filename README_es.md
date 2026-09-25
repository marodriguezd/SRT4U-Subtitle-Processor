# SRT4U - Subtitle Processor

[![Licencia: MIT](https://img.shields.io/badge/Licencia-MIT-blue.svg)](LICENSE)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10+-3776AB.svg?logo=python&logoColor=white)](https://python.org)
[![PyQt6](https://img.shields.io/badge/GUI-PyQt6-41CD52.svg?logo=qt&logoColor=white)](https://pypi.org/project/PyQt6/)
[![Plataformas](https://img.shields.io/badge/Plataformas-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey.svg)]()
[![Tests](https://img.shields.io/badge/Tests-19%20superados-success.svg)]()

[**English**](README.md) | [**Español**](README_es.md)

Aplicación de escritorio para traducir, limpiar y convertir archivos de subtítulos (`.srt`, `.vtt`, `.ass`, `.txt`) con reproductor de video sincronizado en tiempo real.

![Vista previa de SRT4U](assets/preview.png)

---

## Funcionalidades principales

- **Motores de traducción**:
  - Google Translate: Capa gratuita integrada lista para usar, sin necesidad de registros ni claves API.
  - DeepL: Soporte para claves API Free y Pro.
  - OpenAI / LLMs locales: Compatible con endpoints de OpenAI, Ollama y OpenRouter.
- **Limpiador automático**: Elimina enlaces de Telegram (`t.me`), URLs, marcas de agua de fansubs, publicidad y notas musicales (`♪`), respetando las etiquetas de formato (`<i>`, `<b>`, estilos ASS).
- **Conversor entre formatos**: Conversión bidireccional entre `.srt`, `.vtt`, `.ass` y texto plano `.txt`.
- **Previsualización con video**: Reproductor integrado para verificar los subtítulos sobre el video antes de guardar.
- **Procesamiento por lote**: Cola de archivos con seguimiento de estado individual por archivo.
- **Ejecución multihilo**: Traducción simultánea de bloques de subtítulos para acelerar el procesamiento.
- **Tema Dark / Light Glassmorphism**: Alternancia instantánea entre modo oscuro y claro.

---

## Instalación y uso

### Requisitos
- Python 3.10 o superior
- `pip`

### Ejecutar desde código fuente

```bash
# Clonar el repositorio
git clone https://github.com/marodriguezd/SRT4U-Subtitle-Processor.git
cd SRT4U-Subtitle-Processor

# Crear y activar entorno virtual
python -m venv .venv
source .venv/bin/activate  # En Windows: .venv\Scripts\activate

# Instalar dependencias
pip install -r requirements.txt

# Iniciar la aplicación
python main.py
```

### Ejecutables precompilados
GitHub Actions compila automáticamente binarios portables en cada tag de versión:
- **Windows**: `SRT4U-Windows-x64.exe`
- **Linux**: `SRT4U-Linux-x86_64.tar.gz`
- **macOS**: `SRT4U-macOS.dmg`

---

## Pruebas automatizadas

La flota de tests evalúa parseo, limpieza, conversiones entre formatos, traducción gratuita e interfaz headless:

```bash
pytest tests/ -v
```

---

## Formatos soportados

| Formato | Extensión | Lectura | Escritura | Conserva estilos |
|---|---|:---:|:---:|:---:|
| SubRip Subtitle | `.srt` | Sí | Sí | Sí (etiquetas HTML) |
| Web Video Text Tracks | `.vtt` | Sí | Sí | Sí (parámetros de cue y tags) |
| Advanced SubStation Alpha | `.ass` / `.ssa` | Sí | Sí | Sí (estilos y posiciones) |
| Texto plano (diálogo) | `.txt` | Sí | Sí | Solo líneas |

---

## Licencia

Este proyecto está bajo la [Licencia MIT](LICENSE).
