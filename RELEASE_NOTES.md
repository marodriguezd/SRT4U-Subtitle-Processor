# Release Notes — SRT4U 1.4.12

SRT4U Subtitle Processor **1.4.12** is published on GitHub as
[tag/v1.4.12](https://github.com/marodriguezd/SRT4U-Subtitle-Processor/releases/tag/v1.4.12).

## What's in 1.4.12

A maintenance and bug-fix release. No new product functionality; the feature
set is unchanged from 1.4.11.

### Fixed

- **History (SQLite)**: opening the history store no longer rewrites the
  permissions of the parent directory of a caller-supplied database path
  (`--db`, `SRT4U_HISTORY_DB` or an explicit path). Only the application-managed
  SRT4U directory is hardened to `0700`; a custom location keeps the
  permissions its owner chose.
- **Testing and documentation**: an always-true FFmpeg assertion was removed
  from the opt-in real-Whisper test, and the documentation now distinguishes
  the external `ffmpeg` executable from the FFmpeg decoding libraries that
  faster-whisper bundles via PyAV.

### Added

- **Python 3.10 compatibility**: the pyproject-reading test guards fall back to
  `tomli`, and a dedicated CI job runs them on the declared minimum Python
  version.

### Changed

- Screenshot tooling and the new integration-testing documentation now cover
  all seven interface languages consistently.

The macOS DMG remains **Apple Silicon (arm64)** only and will not launch on Intel Macs;
no x86_64 build is available.
