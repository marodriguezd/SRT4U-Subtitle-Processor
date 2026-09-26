# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-09-26

### Added
- **Glassmorphism Desktop UI**: Modern dark theme interface built with PyQt6, featuring responsive split layouts, status indicators, and dedicated workflow sections.
- **Parallel Subtitle Translation**: Multi-threaded translation pipeline using `ThreadPoolExecutor` with automatic CPU-aware thread scaling (`max_workers`).
- **Translation Studio**: Integrated synchronized video preview player with subtitle overlay, timestamp seeking, and dedicated audio/volume controls.
- **Direct Subtitle Editing**: Live inline subtitle block editor with timestamp validation and batch text modifications.
- **Hardsub / Burn-in Video Export**: Subtitle burn-in rendering directly to video via embedded static FFmpeg, supporting customizable fonts, outline, shadow, box backdrops, and proportional font scaling (`PlayResX`/`PlayResY`).
- **Multi-language Support (i18n)**: Native UI localizations for English, Spanish, German, Italian, Portuguese, and Simplified Chinese with automatic system locale detection.
- **Multi-format Conversion**: Seamless conversion and parsing between SRT, VTT, ASS, and plain TXT subtitle transcripts.
- **Automated CI/CD Multiplatform Packaging**: GitHub Actions release pipeline for standalone Windows x64 executable, Linux x86_64 AppImage & tarball, and macOS universal DMG.

### Fixed
- Proportional subtitle sizing during video burn-in across arbitrary video resolutions via ASS header scaling.
- Audio playback and synchronization in video preview.
- Linux X11/Mesa hardware acceleration crashes by setting `QT_XCB_GL_INTEGRATION=none`.
- Linux desktop icon visibility by switching from color bitmap emojis to scalable vector SVG icons.
- Subtitle parsing edge cases for single timestamps, unindexed transcripts, and malformed spacing.

[1.0.0]: https://github.com/marodriguezd/SRT4U-Subtitle-Processor/releases/tag/v1.0.0
