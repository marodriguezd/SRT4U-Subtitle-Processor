# Release Notes — SRT4U 1.4.11

SRT4U Subtitle Processor **1.4.11** is published on GitHub as
[tag/v1.4.11](https://github.com/marodriguezd/SRT4U-Subtitle-Processor/releases/tag/v1.4.11).

## What's in 1.4.11

A stability, security and reliability update. No new product features; the
feature set is unchanged from 1.4.10.

### Fixes and hardening

- **API uploads and jobs**: temporary upload files are closed before deletion
  and cleaned on every error path; uploaded filenames lose directory
  components; the job queue is bounded and returns HTTP 503 with
  `Retry-After` when saturated; cancelled or rejected queued jobs always
  release their temporary files; and a shutdown race that could run a dropped
  job after its cleanup was fixed.
- **Translation**: same-origin redirects now normalize default HTTP/HTTPS
  ports and reject malformed ports from redirect headers instead of raising.
- **History (SQLite)**: WAL mode and a busy timeout reduce lock errors,
  migrations are race-safe under concurrent opens, and storage failures
  surface as `HistoryError` without interrupting processing.
- **Whisper**: with `device=auto`, a failed CUDA initialization now falls
  back to CPU processing; an explicit `cuda` request still fails loudly.
- **GUI**: the application starts even when Qt Multimedia is unavailable,
  disabling playback controls instead of crashing; start, cancel, close,
  batch and language workflows are covered by new GUI tests.
- **Packaging**: cross-platform smoke tests launch the built Windows `.exe`,
  Linux AppImage and macOS `.app` to verify bundled resources, FFmpeg and
  startup before publication.

---

## Current published release

The latest published release is **v1.4.11** (this release).

See [CHANGELOG.md](CHANGELOG.md) for the full, dated change list.

### macOS (Apple Silicon)

The macOS DMG is **Apple Silicon (arm64)** only and will not launch on Intel Macs;
no x86_64 build is available. Download links are in the assets table of
[README.md](README.md).
