# SRT4U - Subtitle Processor

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10+-3776AB.svg?logo=python&logoColor=white)](https://python.org)
[![PyQt6](https://img.shields.io/badge/GUI-PyQt6-41CD52.svg?logo=qt&logoColor=white)](https://pypi.org/project/PyQt6/)
[![Platforms](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey.svg)]()
[![Tests](https://img.shields.io/badge/Tests-19%20passed-success.svg)]()

[**English**](README.md) | [**Español**](README_es.md)

Desktop app to translate, clean, and convert subtitle files (`.srt`, `.vtt`, `.ass`, `.txt`) with a real-time synchronized video player.

![SRT4U Preview](assets/preview.png)

---

## Features

- **Translation Engines**:
  - Google Translate: Built-in free tier with zero setup or API keys required.
  - DeepL: Free and Pro API key support.
  - OpenAI / Local LLMs: Compatible with OpenAI, Ollama, and OpenRouter endpoints.
- **Automated Cleaner**: Strips out Telegram channels (`t.me`), URLs, fansub credits, ads, and musical markers (`♪`) while preserving valid dialogue and formatting tags (`<i>`, `<b>`, ASS styles).
- **Format Converter**: Bi-directional conversion between `.srt`, `.vtt`, `.ass`, and plain text `.txt`.
- **Live Video Preview**: Integrated player to inspect subtitles overlaid onto the video before saving.
- **Batch Processing**: Queue entire folders or multiple files with per-file progress tracking.
- **Parallel Execution**: Multi-threaded block translation to speed up large subtitle files.
- **Dark / Light Glass Theme**: Toggle instantly between dark and light modes.

---

## Installation & Running

### Requirements
- Python 3.10 or higher
- `pip`

### Run from Source

```bash
# Clone the repository
git clone https://github.com/marodriguezd/SRT4U-Subtitle-Processor.git
cd SRT4U-Subtitle-Processor

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the application
python main.py
```

### Pre-built Binaries
Standalone portable binaries are automatically built via GitHub Actions for every release tag:
- **Windows**: `SRT4U-Windows-x64.exe`
- **Linux**: `SRT4U-Linux-x86_64.AppImage` (portable)
- **macOS**: `SRT4U-macOS.dmg`

---

## Running Tests

The test suite covers parsing, cleaning, cross-format conversion, free translation, and UI flows:

```bash
pytest tests/ -v
```

---

## Supported Formats

| Format | Extension | Read | Write | Style Preservation |
|---|---|:---:|:---:|:---:|
| SubRip Subtitle | `.srt` | Yes | Yes | Yes (HTML tags) |
| Web Video Text Tracks | `.vtt` | Yes | Yes | Yes (cue settings & tags) |
| Advanced SubStation Alpha | `.ass` / `.ssa` | Yes | Yes | Yes (styles & positions) |
| Plain Text Dialogue | `.txt` | Yes | Yes | Lines only |

---

## License

This project is licensed under the [MIT License](LICENSE).