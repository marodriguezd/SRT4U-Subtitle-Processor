## Overview

SRT4U is a standalone, cross-platform desktop application for processing, translating, editing, and burning subtitles into video files. It bundles all core dependencies—including a static build of FFmpeg—into self-contained packages requiring no external runtime installation.

## Key Features

- **Parallel Translation Engine**: High-throughput subtitle translation via Google Translate API with automatic CPU-aware worker thread scaling.
- **Translation Studio & Preview**: Synchronized video player with live subtitle preview, timestamp seeking, and dedicated audio/volume controls.
- **Hardsubbing / Burn-In**: Permanent subtitle rendering to video files with full visual styling (fonts, borders, backdrops, margins) and automatic proportional resolution scaling.
- **Multi-Format Processing**: Parse, clean, and convert between SubRip (`.srt`), WebVTT (`.vtt`), Advanced SubStation Alpha (`.ass`), and plain text (`.txt`).
- **Internationalization (i18n)**: Native UI localizations for English, Spanish, German, Italian, Portuguese, and Simplified Chinese.
- **Zero-Dependency Binaries**: Fully self-contained portable packages for Windows, Linux, and macOS.

---

## Downloads & Platform Packages

| Package | Platform | Architecture | Details |
| :--- | :--- | :--- | :--- |
| **`SRT4U-Windows-x64.exe`** | Windows 10 / 11 | x86_64 | Portable standalone executable (PyInstaller) |
| **`SRT4U-Linux-x86_64.AppImage`** | Linux | x86_64 | Standalone AppImage with bundled Qt & static FFmpeg |
| **`SRT4U-Linux-x86_64.tar.gz`** | Linux | x86_64 | Portable archive with run script |
| **`SRT4U-macOS.dmg`** | macOS 12+ | Universal (ARM64 / x86_64) | Bundled DMG with embedded universal FFmpeg |

---

## Installation & Running

### Windows
Download `SRT4U-Windows-x64.exe` and double-click to launch. No installer or administrator rights required.

### Linux (AppImage)
```bash
chmod +x SRT4U-Linux-x86_64.AppImage
./SRT4U-Linux-x86_64.AppImage
```

### macOS
1. Open `SRT4U-macOS.dmg` and drag `SRT4U.app` to your `Applications` folder.
2. If blocked by Gatekeeper on first launch: Right-click `SRT4U.app` → click **Open** → click **Open** again (or allow in **System Settings → Privacy & Security**).

---

## Verification & Checksums

SHA-256 checksums are provided in `checksums.txt` attached to this release. Verify your download with:

```bash
# Linux
sha256sum -c checksums.txt

# macOS
shasum -a 256 -c checksums.txt

# Windows (PowerShell)
Get-FileHash .\SRT4U-Windows-x64.exe -Algorithm SHA256
```
