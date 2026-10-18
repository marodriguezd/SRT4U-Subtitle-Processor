# Release Notes — SRT4U 1.0.0

SRT4U Subtitle Processor **1.0.0** is published on GitHub as
[tag/v1.0.0](https://github.com/marodriguezd/SRT4U-Subtitle-Processor/releases/tag/v1.0.0).

## What's in 1.0.0

Initial major release of SRT4U Subtitle Processor: a fast, local-first, robust tool to translate, clean, convert, analyze, and burn-in subtitle files (`.srt`, `.vtt`, `.ass`, `.ssa`, `.txt`) with optional local Whisper transcription and end-to-end media pipeline.

### Highlights

- **Three Front-ends, One Core**: PyQt6 desktop GUI, headless CLI (`srt4u`, 8 subcommands), and local REST API (`/api/v1`, OpenAPI).
- **Local-first & Offline-capable**: Free translation tier, cleaning, conversion, analytics, deterministic QA, and SQLite history work 100% locally.
- **Interchangeable Providers**: Google Translate, DeepL, OpenAI-compatible LLMs (Ollama, OpenRouter, OpenAI) with cycle-safe fallback chains and opt-in retries.
- **Whisper Transcription & Media Pipeline**: Optional local speech-to-text via `faster-whisper` and full end-to-end media processing pipeline.
- **Deterministic Quality Assurance & Analytics**: Strict QA gates, reading speed (CPS/CPL), timing overlap detection, and zero-data-loss subtitle format conversion.
- **Optimized & Hardened**: Consolidated $O(N)$ analytics passes, precompiled regular expressions, vector icon caching, concurrency-safe burn-in, and 100% passing test suite (752 tests passed, ~82% coverage).

The macOS DMG remains **Apple Silicon (arm64)** only and will not launch on Intel Macs;
no x86_64 build is available.
