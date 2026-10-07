# Release Notes — SRT4U 1.4.10

SRT4U Subtitle Processor **1.4.10**. See [CHANGELOG.md](CHANGELOG.md) for the
full, dated change list.

## What's New in 1.4.10

A maintenance release with no new product functionality.

### Fixes

- **GPL license fallback**: when the bundled/local `LICENSE` file cannot be found,
  the About page now opens the official GNU GPL v3 page instead of the obsolete
  Creative Commons BY-NC-SA 4.0 URL.

The application behavior and feature set are otherwise unchanged from 1.4.9.

---

## Verification

The release artifacts are built by the same pinned multiplatform CI pipeline and
include the bundled `LICENSE` file.

### macOS (Apple Silicon)

The macOS DMG is **Apple Silicon (arm64)** only and will not launch on Intel Macs. x86_64 build is NOT produced.
