## What's New in 1.1.0

> ⚠️ **Pre-release**: this is a quality-focused pre-release. It contains no new end-user features; it hardens the 1.0.0 codebase ahead of the next feature release.

### Highlights

- **Audited & Remediated Codebase**: a full read-only audit (~58 findings) was remediated end to end — dead code removed, ~65 hardcoded UI strings migrated to the i18n catalog, palette and file-dialog filters centralized, and ineffective tests repaired.
- **UI Robustness Across Languages & Themes**: a new 54-case layout regression suite verifies that no label or button clips its text in any of the 6 UI languages, in both dark and light themes, including ×1.5 scaled-font checks for the settings/about pages and all progress dialogs.
- **Light Theme Fixed**: text colors are now theme-aware, eliminating white-on-white labels in light mode (WCAG contrast ≥ 3.0 verified offscreen). The active sidebar tab — which kept a hardcoded light-lavender color meant for the dark background and was effectively invisible in light mode — is now readable in both themes (5.69:1 light, 9.39:1 dark, measured on the rendered pixels).
- **Dialogs That Always Fit**: burn-in and progress dialogs now derive their minimum size from their real content, so they can always be resized large enough in every language (620–684 px wide depending on locale).
- **Emoji-Free Interface**: all emoji and bitmap glyph usage in the UI was replaced with crisp recolorable SVG icons, per the project's design rules.
- **No Guessing About the Language**: the interface starts in “Automatic (System)” and follows the OS locale, but a language you pick is remembered. The settings page and the top-bar tooltip now say explicitly which one is in force (e.g. “Detected system language: Español”), so “Automatic (System)” is never ambiguous.
- **No More Silent Failures**: failures that used to be swallowed (`except: pass`, `print()`) are now written to a rotating `srt4u.log` in the config folder, and the ones you can act on — incomplete translation, settings not saved, unreadable settings file, unexpected error — raise a dialog telling you what happened and where the log is. Qt's own diagnostics join the same file: `qWarning`/`qCritical`/`qFatal` messages (multimedia codecs and the FFmpeg backend, platform plugins) are captured with their severity and log category instead of disappearing into the console.
- **Coherent System Dialogs**: file open/save dialogs and message boxes now use the app's palette, fonts and SVG icons in both themes — previously they picked up desktop-theme icons (some invisible) and Qt's default blue selection color.
- **Quality Gates in CI**: the test job now runs a pinned ruff lint (shared `ruff.toml`), a `ruff format --check`, a screenshot-tool smoke test, and the full test suite before any platform build is produced. A separate compatibility job installs the minimum PyQt6 declared in `requirements.txt` (`6.6.1`) and runs the suite against it, and it must pass before a release is published.

See [CHANGELOG.md](CHANGELOG.md) for the complete list of changes.

---

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
