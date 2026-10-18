# Release Notes — SRT4U 1.0.0

SRT4U Subtitle Processor 1.0.0 is the initial production release of the local-first desktop, CLI, and REST API platform for subtitle translation, cleaning, format conversion, deterministic quality assurance, and video burn-in.

## Key Capabilities

- **Unified Core Architecture**: A shared domain core powers the PyQt6 desktop interface, headless CLI (`srt4u`), and OpenAPI REST service (`/api/v1`).
- **Local-First Processing**: Cleaning, format conversion (`.srt`, `.vtt`, `.ass`, `.ssa`, `.txt`), deterministic QA analysis, and SQLite audit logging operate entirely offline.
- **Translation Provider Registry**: Pluggable integration for Google Translate, DeepL, and OpenAI-compatible endpoints (Ollama, OpenRouter, OpenAI) with cycle-safe fallback chains.
- **Local Transcription & Pipeline**: Optional local Whisper integration via `faster-whisper` and an end-to-end media processing pipeline.
- **High-Performance UI Virtualization**: The subtitle preview viewer uses row virtualization and debounced search, providing instant loading and low-latency navigation across documents with thousands of cues.
- **Encoding & Contract Integrity**: Unified encoding auto-detection across CP1252, UTF-8, and UTF-16, with synchronized API schemas and cooperative worker cancellation.

## Platform Binaries

Automated GitHub Actions builds produce signed standalone binaries:
- Windows: x64 standalone executable.
- Linux: x86_64 AppImage and portable tarball.
- macOS: Apple Silicon (arm64) DMG. Intel x86_64 Macs are not supported.
