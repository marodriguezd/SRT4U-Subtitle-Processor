# SRT4U - Subtitle Processor 💎

[![License](https://img.shields.io/badge/License-Apache%202.0-blue)](https://opensource.org/licenses/Apache-2.0)
[![Python](https://img.shields.io/badge/Python-3.13%2B-yellow?logo=python&logoColor=white)](https://www.python.org/)
[![PyQt](https://img.shields.io/badge/PyQt-6.4%2B-3D9D5B)](https://pypi.org/project/PyQt6/)

[**English 🇺🇸**](README.md) | [**Español 🇪🇸**](README_es.md)

---

## Traduce, Limpia y Convierte Archivos de Subtítulos con Elegancia

![Captura de pantalla de la aplicación](https://raw.githubusercontent.com/marodriguezd/SRT4U_Subtitle-Processor/main/assets/demo-screenshot.png)

**SRT4U** es una aplicación de escritorio premium desarrollada con Python 3.13 y PyQt6, diseñada para procesar archivos de subtítulos con un enfoque en la velocidad, la fiabilidad y una impresionante interfaz de usuario estilo **Glassmorphism**.

### ✨ ¿Qué hay de nuevo? (Refactorización Glassmorphism)
La última versión presenta una renovación arquitectónica completa:
- **UI Premium**: Tema oscuro ultra moderno con tarjetas "Glass" translúcidas y degradados suaves.
- **Pureza Arquitectónica**: Separación estricta entre la lógica de procesamiento central y la interfaz de usuario.
- **Motor de Traducción en Paralelo**: Nuevo núcleo multihilo para traducciones significativamente más rápidas.
- **Rendimiento Mejorado**: Optimizado para Python 3.13 con hilos nativos de PyQt6.
- **Ejecutable Compilado**: Distribución sencilla para Windows mediante PyInstaller.

---

## 🚀 Características Principales

- **💎 Interfaz Glassmorphism**: Un diseño moderno y translúcido que se integra perfectamente en Windows 11.
- **🛠️ Procesamiento Robusto**: Detecta y corrige automáticamente errores comunes como índices faltantes o separadores de tiempo no estándar (`-` en lugar de `-->`).
- **🌍 Traducción Inteligente**: Impulsado por `deep-translator`. Traduce a más de 100 idiomas manteniendo la integridad del cronometraje original.
- **🚀 Motor en Paralelo**: Nueva arquitectura multihilo que procesa múltiples bloques de subtítulos simultáneamente, reduciendo el tiempo de traducción hasta en un 80%.
- **🧹 Limpieza Experta**: Elimina automáticamente spam promocional, IDs de Telegram, URLs y símbolos musicales.
- **🔄 Soporte Multi-Formato**: Convierte sin problemas entre `.srt` y `.vtt`. También soporta archivos `.txt` que contienen marcas de tiempo de subtítulos.
- **⚡ Rendimiento Nativo**: Procesamiento totalmente asíncrono; la interfaz nunca se congela, incluso durante tareas de traducción pesadas.

---

## 📦 Instalación y Configuración

### Requisitos Previos
- Python 3.13 (recomendado)
- Conexión a Internet (para las traducciones)

### 1. Clonar e Instalar
```bash
git clone https://github.com/marodriguezd/SRT4U_Subtitle-Processor.git
cd SRT4U_Subtitle-Processor
pip install -r requirements.txt
```

### 2. Ejecutar
```bash
python main.py
```

### 3. Generar Ejecutable Portable (.exe)
Si deseas crear una versión independiente para Windows:
```bash
.\build_exe.bat
```
El archivo resultante se encontrará en la carpeta `/dist`.

---

## 🛠️ Arquitectura Interna

El proyecto sigue una arquitectura modular orientada a servicios:
- `application/ui/`: Contiene los estilos Glassmorphism y las definiciones de ventanas PyQt6.
- `application/services/`: Servicios de lógica pura para manejo de archivos, análisis de subtítulos y traducción.
- `main.py`: El punto de entrada que orquesta el lanzamiento de la aplicación.

---

## 📄 Licencia
Este proyecto está bajo la Licencia Apache 2.0.

---
*Creado con ❤️ para los entusiastas de los subtítulos.*
