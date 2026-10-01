# Release Notes — SRT4U 1.4.9

SRT4U Subtitle Processor **1.4.9**. See [CHANGELOG.md](CHANGELOG.md) for the
full, dated change list.

## What's New in 1.4.9

A feature release. Unlike 1.1.0 (a quality-focused hardening pass), this one adds
three optional capabilities — a local REST API, local Whisper transcription and an
end-to-end media pipeline — on top of the existing desktop and CLI core, plus a
hardening pass over translation, history and the build pipeline.

### Highlights

- **Local REST API (optional)**: a thin FastAPI layer over the *existing* services at
  `/api/v1` — `health`, `analyze`, `qa`, job-based `translate`/`process`/`transcribe`/
  `pipeline`, `history` and stored `benchmarks`, with OpenAPI docs at `/docs` and a
  `srt4u serve` command that binds `127.0.0.1` by default. Slow work runs as local
  jobs with best-effort cancellation: a queued job is dropped, while a running job
  finishes in the background and only its result is discarded. **No authentication
  by design; keep it on loopback.**
- **Local Whisper transcription (optional)**: audio/video to SRT/VTT with
  `faster-whisper` behind the `[transcription]` extra, via the `srt4u transcribe`
  command, a Transcribe page and `POST /api/v1/transcribe`. Models are never
  bundled; the one-time download is announced with its size. Nothing is sent to a
  third party.
- **Media pipeline**: `srt4u pipeline`, a Pipeline page and `POST /api/v1/pipeline`
  chain transcription/parse → cleaning → analytics → QA → optional translation →
  final QA → export → optional burn-in, with per-stage status, cooperative
  (between-stage) cancellation and one history record per run.
- **Translation providers and metrics**: an interchangeable provider registry
  (`google`, `deepl`, `openai`, `ollama`, `llm`), normalized error categories,
  opt-in bounded retries and explicit cycle-safe fallbacks, plus JSON-serializable
  per-run metrics. Cost estimates stay `null` — no invented tariffs. API keys never
  reach logs, errors, history or API responses.
- **Benchmarking and analysis**: a `benchmark` command over a versioned dataset with
  JSON/CSV export, and `analysis/benchmark_analysis.py` +
  `notebooks/benchmark_analysis.ipynb` for descriptive statistics and plots.
  No quality judging, no new runtime dependencies.
- **Local SQLite history**: aggregate-only run records with versioned `user_version`
  migrations, a `history` command, a History page and read-only API endpoints.
  Subtitle texts, transcripts, media and secrets are never persisted.
- **Install contract made explicit**: `pip install .` yields a working desktop GUI +
  CLI (PyQt6 + deep-translator). `api`, `transcription` and `dev` are optional
  extras; `desktop` remains an alias of the base stack.
- **Reproducible packaging**: FFmpeg is pinned to `eugeneware/ffmpeg-static`
  `b6.1.1` and `appimagetool` to `1.9.1` instead of moving tags, so the published
  binaries are reproducible. `contents: write` is now confined to the `release` job.
- **Burn-in rendering hardened**: braces in subtitle text are escaped before the
  renderer generates its own ASS tags, so arbitrary subtitle content can no longer
  inject ASS override or drawing blocks into the burned-in video.
- **Deep-audit remediation**: failed or cancelled burn-in encodes can no longer
  destroy a previously valid output (atomic sibling-temp promotion); WebVTT
  `NOTE`/`STYLE`/`REGION` metadata no longer produces phantom cues; parser and QA
  share one timestamp grammar so the two layers cannot contradict each other;
  per-cue ASS styles survive export; the API shows actionable local validation
  errors while internal failures stay sanitized; GUI start actions guard against
  double launches; parse issues are reported as advisories across pipeline, API,
  GUI and history.
- **i18n coherence**: the six catalogs (English, Spanish, German, Italian,
  Portuguese, Simplified Chinese) carry identical keys and compatible
  placeholders, including the Transcribe and Pipeline pages.

See [CHANGELOG.md](CHANGELOG.md) for the complete list of changes.

---

## Overview

SRT4U is a standalone, cross-platform desktop application for processing,
translating, editing, and burning subtitles into video files. It bundles all core
dependencies — including a static build of FFmpeg — into self-contained packages
requiring no external runtime installation.

## Key Features

- **Parallel Translation Engine**: High-throughput subtitle translation via Google
  Translate with automatic CPU-aware worker thread scaling; DeepL and
  OpenAI-compatible endpoints (including local Ollama) are interchangeable.
- **Translation Studio & Preview**: Synchronized video player with live subtitle
  preview, timestamp seeking, and dedicated audio/volume controls.
- **Hardsubbing / Burn-In**: Permanent subtitle rendering to video files with full
  visual styling (fonts, borders, backdrops, margins) and automatic proportional
  resolution scaling.
- **Multi-Format Processing**: Parse, clean, and convert between SubRip (`.srt`),
  WebVTT (`.vtt`), Advanced SubStation Alpha (`.ass`), SSA and plain text (`.txt`).
- **Analytics & Deterministic QA**: Grouped content/timing/quality metrics and a
  fixed rule set, both with JSON output and CSV export.
- **Internationalization (i18n)**: Native UI localizations for English, Spanish,
  German, Italian, Portuguese, and Simplified Chinese.
- **Local-First**: Subtitle processing, QA, analytics, history and burn-in run
  entirely offline. Only the translation provider you choose is contacted.

---

## Downloads & Platform Packages

| Package | Platform | Architecture | Details |
| :--- | :--- | :--- | :--- |
| **`SRT4U-Windows-x64.exe`** | Windows 10 / 11 | x86_64 | Portable standalone executable (PyInstaller), bundled FFmpeg |
| **`SRT4U-Linux-x86_64.AppImage`** | Linux | x86_64 | Standalone AppImage with bundled Qt & static FFmpeg |
| **`SRT4U-Linux-x86_64.tar.gz`** | Linux | x86_64 | Portable archive with the standalone executable (run it directly) |
| **`SRT4U-macOS.dmg`** | macOS 12+ | Apple Silicon (arm64) | Bundled DMG; **not** Intel/universal — no x86_64 build is produced |

> **macOS:** the current macOS build is produced on an `arm64` runner and ships
> **arm64 only**. It runs on Apple Silicon Macs and will not launch on Intel Macs.
> A universal (arm64 + x86_64) build requires a dedicated x86_64 build job and is
> not part of this release.

---

## Installation & Running

### Windows
Download `SRT4U-Windows-x64.exe` and double-click to launch. No installer or
administrator rights required.

### Linux (AppImage)
```bash
chmod +x SRT4U-Linux-x86_64.AppImage
./SRT4U-Linux-x86_64.AppImage
```

### macOS (Apple Silicon)
1. Open `SRT4U-macOS.dmg` and drag `SRT4U.app` to your `Applications` folder.
2. If blocked by Gatekeeper on first launch: Right-click `SRT4U.app` → click **Open**
   → click **Open** again (or allow in **System Settings → Privacy & Security**).

---

## Verification & Checksums

SHA-256 checksums are provided in `checksums.txt` attached to the release. Verify
your download with:

```bash
# Linux
sha256sum -c checksums.txt

# macOS
shasum -a 256 -c checksums.txt

# Windows (PowerShell)
Get-FileHash .\SRT4U-Windows-x64.exe -Algorithm SHA256
```
