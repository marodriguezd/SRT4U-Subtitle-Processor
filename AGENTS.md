# SRT4U — Agent Instructions

Canonical, permanent agent instructions. This is the **only** versioned agent
contract in the repo. Temporal agent work (prompts, reports, audits, scratch)
lives in `.agents/` (git-ignored, never committed).

## 1. Project purpose

SRT4U Subtitle Processor (current version **1.4.9**, working tree) is a
local-first desktop + headless tool to translate, clean, convert, analyze and
burn-in subtitle files (`.srt`, `.vtt`, `.ass`, `.ssa`, `.txt`), with optional
local Whisper transcription of audio/video and an end-to-end media pipeline.
Three front-ends share one core: PyQt6 desktop GUI (`main.py`), headless CLI
(`srt4u`, 8 subcommands), and an optional local REST API (`/api/v1`, OpenAPI).

## 2. Product philosophy

- **Local-first.** Base install works offline except for the translation
  provider the user explicitly chooses.
- Base install is usable with **zero paid services**: free Google Translate
  tier needs no keys; cleaning, conversion, analytics, deterministic QA and
  history are local. Burn-in is local but requires a working FFmpeg binary
  (system-installed or bundled by a distribution).
- Translation providers are **interchangeable** (`google`, `deepl`, `openai`,
  `ollama`, `llm`); do NOT claim external providers are free — only the
  Google free tier is keyless.
- **Local AI is optional and supported**: Ollama/OpenRouter via
  OpenAI-compatible endpoints, and local Whisper via `faster-whisper`.
- Processing is local; never send user content anywhere except the provider
  endpoint the user configured.

## 3. Architecture

```
GUI (PyQt6) / CLI (argparse) / API (FastAPI)
            ↓  (thin layers, no business logic)
      domain / services
            ↓
providers (registry) / SQLite / FFmpeg
```

Key services (`application/services/`):

- `SubtitleService` — parse, clean, convert, process orchestration.
- `TranslationService` — dispatches via `ProviderRegistry` to
  `translation_providers.py` (`Google`, `DeepL`, `OpenAICompatible`);
  normalized `TranslationProviderError`, opt-in retries, explicit fallbacks,
  `TranslationMetrics` (never invent tariffs: `estimated_cost` is `null`).
- `TranscriptionService` + `transcription_whisper.py` — `TranscriptionProvider`
  ABC, `TranscriptionRegistry`, lazy `faster-whisper` import;
  `TranscriptionResult`/`TranscriptionMetrics` (real-time factor only when
  both durations are known); converts segments to `SubtitleItem`, renders
  SRT/VTT via `SubtitleService.format_output()`.
- `MediaPipeline` (`media_pipeline.py`) — `PipelineConfig` validated up front,
  `PipelineResult` with per-stage status/durations, strict QA gates; stages:
  transcription/parse → cleaning → analytics → QA → optional translation →
  final QA → export → optional burn-in. Reuses the services above; no
  duplicated domain logic.
- `HistoryStore` (`history_store.py`, schema v2) — SQLite `runs` + `qa_findings`,
  `user_version` migrations, `record_safely` never breaks execution.
- `SubtitleQA` + `subtitle_analytics.py` — deterministic rules and grouped
  metrics (content/timing/quality); overlap findings are warnings
  (`strict_passed` semantics).
- `TranslationBenchmark` (`translation_benchmark.py`) — versioned dataset,
  per-(provider, run) rows, JSON/CSV export; no quality judging.
- `VideoBurnerService` — `run_burn_in_sync` with real FFmpeg progress; the
  module imports PyQt6 because it also contains the UI-bound `BurnInWorker`.
  Headless services/CLI/API must not instantiate or import `BurnInWorker`;
  requested headless burn-in is available with the base desktop dependency.
- `JobManager` (`application/api/jobs.py`) — in-memory local jobs
  (`queued/running/completed/failed/cancelled`); lost on restart by design.

**Import rules:** core subtitle parsing, QA, analytics, history, translation
providers and CLI processing do not require creating a Qt application.
`application/services/i18n_service.py` and
`application/services/video_burner_service.py` import PyQt6 (the latter also
contains the UI-bound `BurnInWorker`); GUI modules require Qt. FastAPI/Pydantic
are confined to the optional API layer. Headless burn-in imports the burner
only when requested and therefore also requires the desktop/PyQt6 dependency.
`faster-whisper` is imported lazily inside the provider; base code paths work
without it and transcription reports the optional-extra install hint.

## 4. Repository structure

- `main.py` — desktop entry point.
- `application/cli.py` — `srt4u` (`process analyze qa benchmark history
  transcribe pipeline serve`).
- `application/api/` — `app.py:create_app()`, `API_PREFIX="/api/v1"`,
  `routes/` (13 paths), `schemas.py`, `jobs.py`, `deps.py`.
- `application/services/` — domain core (see §3).
- `application/ui/` — `main_window.py` (11 pages), widgets, styles, i18n
  consumers, burn-in dialog; no business logic.
- `tests/` — full suite + fixtures (never write into `tests/fixtures/`).
- `docs/` — product docs (`cli/api/analytics/qa/transcription/pipeline/
  database/providers/benchmarking/benchmark_analysis/tech-debt`). Product
  documentation: do NOT move.
- `analysis/`, `notebooks/` — benchmark analysis (stdlib core; pandas/
  matplotlib only as optional analysis-env bridges).
- `tools/regenerate_screenshots.py` — offscreen screenshot gallery + CI smoke.
- `assets/` — icons, previews (product resources).
- `.agents/` — agent-only workspace (git-ignored).

## 5. Core development rules

- Inspect before editing; reuse existing services; never duplicate domain
  logic across GUI/CLI/API.
- No unnecessary abstractions, no new layers without a proven need.
- Keep GUI/CLI/API on the same core; fix bugs in services, not in each front-end.
- No PyQt/FastAPI in the domain; providers decoupled behind registries.
- Optional dependencies must stay truly optional (lazy imports + clear
  install hints, e.g. `python -m pip install '.[transcription]'`).
- UI strings go through `i18n_service.py`; the six catalogs must have identical
  keys and compatible placeholders (en es pt de it zh-CN). Never leave a
  hardcoded fallback in another language. Spanish reference is
  es-ES (archivo, vídeo, configuración).
- No emojis in UI (Qt/X11 FreeType limitation); use SVG via
  `application/ui/icons.py`. `♪/♫` in cleaning patterns are functional, not UI.
- Generated output names are canonical: `*_processed`, `*_transcribed`,
  `*_pipeline`. Temp files (`srt4u-api-*`, sibling export temps) must always
  be cleaned up, including on queued-cancel (`on_drop`).

## 6. Agent workflow

1. inspect (read code, never assume) → 2. understand → 3. plan (todo list for
   3+ step work) → 4. implement (minimal diff) → 5. test → 6. lint →
   7. format → 8. review diff (`git status/diff`, no secrets) → 9. report
   (facts + evidence, no marketing).

## 7. Git rules

- Work only on the branch assigned for the task; this final hardening was
  explicitly assigned to the current `main` branch. Never switch branches.
- Never commit or push unless explicitly requested. Never `reset --hard`,
  rebase destructively, or rewrite history.
- Never delete other agents' work. Review `git diff` before finishing.

## 8. Testing

```bash
.venv/bin/python -m pytest tests/ -q -m "not network"  # no network/keys/models
.venv/bin/python -m ruff check application main.py conftest.py tests tools
.venv/bin/python -m ruff format --check application main.py conftest.py tests tools
```

Relevant smokes: `srt4u --version`, `srt4u <cmd> --help`, API
`GET /api/v1/health` + OpenAPI path count, GUI offscreen
(`QT_QPA_PLATFORM=offscreen`, 11 pages × 6 languages). Opt-in extras:
real-Whisper test (`SRT4U_TEST_REAL_WHISPER=1`), real-media e2e
(`SRT4U_E2E_MEDIA`). Suite redirects `ConfigService` to a temp dir; keep it so.

## 9. Installation dependencies (from `pyproject.toml`, Python `>=3.10`)

- **base**: `PyQt6` + `deep-translator`; GUI + headless CLI + analytics + QA +
  translation + history + pipeline over subtitle inputs. `requirements.txt` is
  a documented exact mirror of the base dependency list; a coherence test
  prevents silent drift. The CLI does not create a Qt application.
- **`.[api]`**: FastAPI + uvicorn (`srt4u serve`, default `127.0.0.1:8000`).
- **`.[transcription]`**: `faster-whisper` (`srt4u transcribe`, media pipeline
  input). Models (`tiny/base/small/medium/large-v3/turbo`, default `small`)
  are NEVER bundled; first use downloads once with prior notice
  (`SRT4U_WHISPER_MODEL_DIR` relocates the cache).
- **`.[dev]`**: pytest + ruff.
- **`.[desktop]`** = compatibility alias for the base stack.
- **full** = base + API + transcription (see `build_exe.bat` BASE vs FULL).

## 10. Translation providers

Registry in `translation_providers.py`; `TranslationService` coordinates.
Seven normalized error categories with `error_type`/`retryable`; retries are
opt-in (`max_retries`, API bounded 0–10); fallbacks explicit and cycle-safe
(chain capped). `openai`/`llm`/`ollama` share the OpenAI-compatible HTTP
implementation; `requested_provider` is preserved in metrics. Secrets (keys,
headers, raw backend errors) never reach logs, errors, history or API
responses — `error_message` stays `None` on provider failure.

## 11. Transcription

`faster-whisper` behind `[transcription]`, lazy import, `WHISPER_MODELS` with
sizes shown to the user. Media validation (`MEDIA_EXTENSIONS`: mp4/mkv/webm/
mov/mp3/wav/m4a/…); `device` in `auto/cpu/cuda`; `--language auto` detects.
`TranscriptionService.to_subtitle_items()` + `render()` produce SRT/VTT that
flow into analytics, QA, cleaning, translation, burn-in. API caps media
uploads at 500 MB (subtitle uploads 5 MB).

## 12. API

Thin routes over services via `create_app()`; slow work
(translate/process/transcribe/pipeline) runs as `JobManager` jobs (202 +
`Location`-style id polling, 404/409 semantics). Summaries/descriptions are
in Spanish (same convention as the CLI). Errors sanitized (`safe_detail`);
temps removed via `remove_temp` + `on_drop` on queued-cancel; stderr-free
client messages (ffmpeg details go to server logs). Burn-in never runs
server-side; pipeline exports to a sibling temp and returns
`output_subtitle: null` plus the original filename.

## 13. GUI

Long work runs in `QThread` workers (`TranscribeWorker`, `PipelineWorker`,
`BurnInWorker`) with cooperative cancel and `ProgressModal` (real stages,
never invented percentages). 11 pages incl. Transcribe (p.9), Pipeline
(p.10), History; nav order `[home, studio, clean, convert, batch, transcribe,
pipeline, history, settings, about]`. All user strings via `t()`; dialogs
themed non-native (`message_boxes.py`); `Styles.sync_minimum_size()` keeps
dialog minimums content-derived; layouts must survive German-length strings
— fix layouts, never truncate strings. Icons must match actions
(play=preview/transcribe, zap=pipeline, folder=choose).

## 14. History / SQLite

`HistoryStore` records `process/analyze/qa/benchmark/transcription/pipeline`
with aggregate metrics only. Migrations v1→v2 (`media_duration_ms`);
`SRT4U_HISTORY_DB` override. NEVER persist: subtitle texts, transcripts,
audio/video, API keys, headers, secrets (test-enforced). GUI/CLI/API isolate
storage failures via `HistoryError` — history never breaks execution.

## 15. Security

No auth by design (localhost-only default). Sanitize every error path
(CLI stderr, API responses, GUI dialogs): no tracebacks, no internal paths,
no secrets. Upload caps enforced; `settings.json` written `0600`.

## 16. Documentation

Product docs (`README*.md`, `CHANGELOG.md`, `docs/`, `RELEASE_NOTES.md`) stay
versioned in place — never move them to `.agents/`. Describe exactly the
current state; no marketing, no invented releases. Known-accepted debt lives
in `docs/tech-debt.md`.

## 17. Current version

**1.4.9** (working tree consolidation; not a published release — no tag/push
claims). Single source chain: `pyproject.toml` → CLI `--version` → API
metadata/`schemas.APP_VERSION`/OpenAPI → GUI `about.version_pill`.
`AppUserModelID …1.1` is a Windows taskbar identity, not a version display —
do not "fix" it. Historical `1.1.0` references (CHANGELOG entry, release
notes, old audits) are legitimate history.

## 18. Agent-only workspace

`.agents/` is private and git-ignored (`prompts/ reports/ audits/ context/
scratch/`). Put phase prompts, audit reports, session notes and scratchpads
there. Never store anything SRT4U needs at runtime there.

## 19. What NOT to do

No microservices, Kubernetes, Docker-by-default, cloud, SaaS, brokers
(Redis/Celery), auth systems, streaming, diarization/speakers, LLM-as-judge,
embeddings/RAG, or new abstraction layers — unless the user explicitly
requests them. No automatic commits/pushes. No dependency additions without
proving stdlib can't do it. No behavior changes disguised as cleanup.

## 20. Definition of done

- Full suite green (`-m "not network"`), `ruff check` + `format --check`
  green on the CI scope (§8).
- Relevant smokes green (CLI/API/GUI as applicable).
- `git status/diff` reviewed: only intended files, no secrets, no stray
  artifacts; `main` untouched; no commit/push unless requested.
- Report: what changed, evidence (commands + results), conscious decisions,
  pending items — nothing more.
