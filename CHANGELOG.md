# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2026-09-27

### Added
- **Layout Regression Suite**: 54 offscreen UI tests (`tests/test_ui_layout.py`) covering clipped-text detection across all 8 pages, burn-in dialog fit, ×1.5 scaled-font variants for the settings/about pages and all progress dialogs, and a `minimumSize >= minimumSizeHint` invariant for every app dialog in all 6 UI languages and both themes.
- **Dynamic Dialog Minimum Sizing**: New `Styles.sync_minimum_size()` helper keeps every dialog's declared minimum size in sync with its real content (`ensurePolished` + layout activation + `minimumSizeHint`), with design floors as lower bounds; applied to `BurnInDialog`, `BurnInProgressModal`, and `ProgressModal` (replacing fixed sizing).
- **Centralized Multiplatform Helpers**: New `application/platform_utils.py` (`open_path`, `reveal_path`) replacing five duplicated platform-dispatch blocks.
- **Screenshot Utility**: `tools/regenerate_screenshots.py` regenerates the offscreen visual-verification gallery (main window pages × languages × themes plus per-language dialogs) with a smoke test (`tests/test_screenshot_tool.py`) wired into CI.
- **Shared Lint Configuration**: `ruff.toml` (pyflakes, pycodestyle statement/parse errors, flake8-bugbear) now drives both local and CI linting, complemented by a `ruff format --check` gate; CI test job runs lint → format → screenshot smoke test → full suite before any build.
- **Diagnostic Logging**: new `application/logging_setup.py` configures a rotating log file (512 KB × 3) in the user config directory; the app no longer fails silently (see below) and records startup, theme/language, FFmpeg detection, translation-engine errors and the final exit code.
- **Qt Message Routing**: a `qInstallMessageHandler` hook (`install_qt_message_handler()`) forwards `qDebug`/`qInfo`/`qWarning`/`qCritical`/`qFatal` messages to the same log via the `srt4u.qt` logger, so Qt Multimedia warnings (codecs, FFmpeg backend, audio), platform-plugin and QSS diagnostics are captured with their severity and log category instead of being scattered on stderr; `QtInfoMsg` is kept at DEBUG level to avoid flooding the log with the noisy Qt Multimedia version banner.
- **Effective-Language Label**: the settings page now states which language is actually in force (new `settings.lang_effective_auto` / `settings.lang_effective` strings in 6 languages), and the top-bar language selector's tooltip repeats it while “Automatic (System)” is selected, so it is unambiguous whether the app follows the system locale or a previously saved choice.
- **User-Visible Failure Notices**: incomplete translations, settings that could not be saved, an unreadable settings file and unhandled exceptions now raise a themed dialog explaining what happened and pointing to the log file.
- **Compatibility Gate for the Declared Minimum**: `compat-min-pyqt6` CI job (see below).
- **Themed System Dialogs**: `QFileDialog` and `QMessageBox` are now rendered non-natively with a deterministic Fusion style, an explicit palette, a scoped stylesheet, a themed SVG icon provider (file/folder/drive/monitor icons) and SVG toolbar icons, replacing the desktop-theme icons that clashed with the app (one of them invisible). Both follow the active dark/light theme via `Styles.set_dark()`.
- **Themed Tooltips**: the application-level tooltip stylesheet is now theme-aware and re-applied whenever the theme changes.
- **License Bundled in Binaries**: `LICENSE` is packaged into the Windows, Linux and macOS builds, so the About page "View license" button opens the local file instead of always falling back to the web page.
- **System Dialog Regression Tests**: 18 new tests (`tests/test_system_dialogs.py`) assert dialog palette contrast, themed toolbar icons with a minimum contrast, the themed icon provider, and message-box theming in all 6 languages × 2 themes.
- **Expanded i18n Catalog**: ~65 new translation keys across the burn-in dialog, progress modals, preview counters, and alerts; 212 consistent keys per language verified by invariant scripts.

### Changed
- **Full Codebase Remediation** (audit §16, 13/13 items): removed all dead code (`FileService`, unused constants, 24 unused imports), migrated ~65 hardcoded UI strings to the i18n service, centralized the color palette in `Styles`, centralized file-dialog filters as i18n keys, repaired ineffective tests (J1–J5), and de-duplicated test fixtures into `conftest.py`.
- **Emoji-Free UI**: removed all emoji/graphic-symbol prefixes (`🔥`, `⌛`, `✓`, `⏱`, `▶`, `⏸`, `🔊`/`🔉`/`🔇`, flag emojis) from widgets and translation strings per project style rules; replaced with recolorable SVG icons (`pause`, `volume`, `volume_low`, `volume_mute`).
- **Neutral Combo Values**: burn-in dialog options (size, color, box style, quality) now use language-neutral IDs resolved via `currentData()`, keeping `BurnInOptions` stable across translations.
- **Config Persistence**: Home-page choices (source/target language, engine, cleaning and format options) are now loaded from and saved to user configuration; the default engine respects `preferred_engine`.
- **Light Theme Correctness**: inline text colors are now theme-aware via `Styles.retint_inline_text()`, fixing white-on-white labels in light mode while preserving permanent-dark surfaces.
- **CI Quality Gates**: test job gained a ruff lint step (shared config, pinned version), a `ruff format --check` step, and an explicit screenshot-tool smoke test ahead of the full suite; builds run only after all gates pass.
- **Minimum-Version Compatibility Gate**: the new `compat-min-pyqt6` CI job derives the PyQt6 lower bound from `requirements.txt`, installs exactly that version with the matching `PyQt6-Qt6` runtime, asserts the pinned version is really the one installed, and runs the suite against it; it is a `needs` prerequisite of the release job, so the declared minimum can no longer silently rot.
- **Pinned PyQt6 Support Range**: `requirements.txt` now declares the verified minimum and an upper bound (`>=6.6.1,<6.12`) instead of an open-ended `>=6.4.0` — 6.4/6.5 lack `QMessageBox.Option`/`setOption`, which the themed message boxes rely on.
- **Lint/Format Scope**: `tools/` is now covered by the ruff lint and format gates, and the screenshot utility was reformatted accordingly.
- **Hermetic Test Configuration**: the suite redirects `ConfigService` to a temporary directory, so tests no longer read or overwrite the real user `settings.json` (previously the UI language persisted by a test could change later results).
- **Network-Dependent Tests Marked**: the free Google Translate tests are tagged `network` and skip gracefully when the engine returns untranslated text (no connectivity), instead of failing the run.
- **Dependency Cleanup**: removed the unused `requests` dependency from `requirements.txt`.
- **Silent Failures Removed**: the 26 `except Exception` blocks that hid problems behind `pass`/`print()` now log with context — configuration read/write (`ConfigService.save()` returns a success flag), translation engine failures (`TranslationService.last_error`, per thread so parallel workers do not race), per-block translation failures (counted in `ProcessingStats.translation_failures`), FFmpeg binary/duration/dimension detection and cleanup failures, i18n formatting errors and PyInstaller path fallbacks.

### Fixed
- **Light theme contrast**: labels rendered white-on-white (~1.0 contrast) in light mode; all inline text now retints to the active theme (WCAG ≥ 3.0 verified offscreen in 6 languages × 2 themes).
- **Unreadable active sidebar tab in light mode**: the active navigation item used a hardcoded light-lavender text (`#C7D2FE`, ~1.1:1) over the primary tint, and its icon and the idle icons used dark-theme defaults below 3:1. Text and icons are now theme-aware (`Styles.NAV_ACTIVE_TEXT_*`, `NAV_ACTIVE_ICON_*`, `NAV_IDLE_ICON_*`): measured on the rendered pixels, the active tab goes from ~1.1:1 to 5.69:1 (light) and 9.39:1 (dark), and idle items reach 4.72–7.20:1.
- **Clipped text across languages**: missing `setWordWrap` on `OptionCard`, `DropZone`, page subtitles, and burn-in captions clipped long German/Portuguese/Italian/English strings; all now wrap and the burn-in dialog auto-sizes per language (620–684 px wide).
- **Burn-in dialog minimum size**: its declared minimum (620 px) could fall below the content-driven `minimumSizeHint` (654 px in English); minimums are now content-derived, so the dialog can always be resized to fit.
- **German license text truncation** on the About page (word wrap + flexible layout).
- **Batch wording** in `README.md` (files, not folders) and `.desktop` alignment in CI packaging (added `GenericName`, `Categories`, `StartupWMClass`, `Keywords`).
- **Test suite reliability**: generated FFmpeg fixture replaces a hardcoded personal path; offline-resilience and conversion tests now assert real outcomes; QMessageBox monkeypatching centralized; the conversion test works on a temporary copy instead of writing into `tests/fixtures/`.
- **Invisible system-dialog controls**: the file dialog's "up one level" and "new folder" buttons rendered with the same color as the dialog background (contrast 1.00–1.02) and the sidebar used amber desktop-theme icons; all system dialog controls now use themed SVG icons (contrast ≥ 10.5).

[1.1.0]: https://github.com/marodriguezd/SRT4U-Subtitle-Processor/releases/tag/v1.1.0

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
