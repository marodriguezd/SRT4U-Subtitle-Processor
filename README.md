# SRT4U - Subtitle Processor 💎

[![License](https://img.shields.io/badge/License-Apache%202.0-blue)](https://opensource.org/licenses/Apache-2.0)
[![Python](https://img.shields.io/badge/Python-3.13%2B-yellow?logo=python&logoColor=white)](https://www.python.org/)
[![PyQt](https://img.shields.io/badge/PyQt-6.4%2B-3D9D5B)](https://pypi.org/project/PyQt6/)

[**Español 🇪🇸**](README_es.md) | [**English 🇺🇸**](README.md)

---

## Translate, Clean, and Convert SRT/VTT Subtitles with Elegance

![Application Screenshot](https://raw.githubusercontent.com/marodriguezd/SRT4U_Subtitle-Processor/main/assets/demo-screenshot.png)

**SRT4U** is a premium desktop application built with Python 3.13 and PyQt6, designed to process subtitle files with a focus on speed, reliability, and a stunning **Glassmorphism** user interface.

### ✨ What's New? (Glassmorphism Refactor)
The latest version features a complete architectural overhaul:
- **Premium UI**: Ultra-modern dark theme with translucent "Glass" cards and smooth gradients.
- **Architectural Purity**: Strict separation between core processing logic and the user interface.
- **Parallel Translation Engine**: New multi-threaded core for significantly faster translations.
- **Enhanced Performance**: Optimized for Python 3.13 with native PyQt6 threading.
- **Bundled Executable**: Easy distribution using PyInstaller.

---

## 🚀 Key Features

- **💎 Stunning Glassmorphism UI**: A modern, translucent design that feels at home on Windows 11 and modern OSs.
- **🛠️ Robust Subtitle Parsing**: Automatically detects and fixes common errors like missing indices or non-standard timestamp separators (`-` instead of `-->`).
- **🌍 Smart Translation**: Powered by `deep-translator`. Translate into 100+ languages while maintaining pixel-perfect timing integrity.
- **🚀 Parallel Engine**: New multi-threaded architecture that processes multiple subtitle blocks simultaneously, cutting translation time by up to 80%.
- **🧹 Expert Cleaning**: Strips out promotional spam, Telegram IDs, URLs, and musical symbols automatically.
- **🔄 Dual Format Support**: Seemlessly convert between `.srt` and `.vtt`.
- **⚡ Native Performance**: Fully asynchronous processing; the UI never freezes, even during heavy translation tasks.

---

## 📦 Installation & Setup

### Prerequisites
- Python 3.13 (recommended)
- Internet connection (for translations)

### 1. Clone & Install
```bash
git clone https://github.com/marodriguezd/SRT4U_Subtitle-Processor.git
cd SRT4U_Subtitle-Processor
pip install -r requirements.txt
```

### 2. Run
```bash
python main.py
```

### 3. Generate Portable Executable (.exe)
If you want to create a standalone version for Windows:
```bash
.\build_exe.bat
```
The resulting file will be in the `/dist` folder.

---

## 🛠️ Internal Architecture

The project follows a modular service-oriented architecture:
- `application/ui/`: Contains the Glassmorphism styling and PyQt6 window definitions.
- `application/services/`: Pure logic services for file handling, subtitle parsing, and translation.
- `main.py`: The entry point that orchestrates the application launch.

---

## 📄 License
This project is licensed under the Apache License 2.0.

---
*Created with ❤️ for subtitle enthusiasts.*