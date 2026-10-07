# Release Notes — SRT4U 1.4.10

SRT4U Subtitle Processor **1.4.10** is prepared on the `main` branch and is
ready to be released, but it has **not yet been published** as a GitHub
Release. See [CHANGELOG.md](CHANGELOG.md) for the change list that will ship
with it.

## What's in 1.4.10

A maintenance release with no new product functionality.

### Fixes

- **GPL license fallback**: when the bundled/local `LICENSE` file cannot be found,
  the About page now opens the official GNU GPL v3 page instead of the obsolete
  Creative Commons BY-NC-SA 4.0 URL.

The application behavior and feature set are otherwise unchanged from 1.4.9.

---

## Current published release

The latest published release is v1.4.9
([tag/v1.4.9](https://github.com/marodriguezd/SRT4U-Subtitle-Processor/releases/tag/v1.4.9)).
The next release will be v1.4.10 once the `v1.4.10` tag is pushed and the
`release` job publishes it.

### macOS (Apple Silicon)

When v1.4.10 is published, its macOS DMG will be **Apple Silicon (arm64)** only
and will not launch on Intel Macs; no x86_64 build will be produced.
