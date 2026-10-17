# Testing — deterministic suite and opt-in integrations

SRT4U separates its tests into a deterministic suite (the one CI runs on every
change) and opt-in integration suites that need Internet access, downloaded
Whisper models or local media fixtures. A skipped test is never a pass: any
path run without its prerequisites stays explicitly unverified.

## Default (deterministic) suite

```bash
pytest tests/ -q -m "not network"                          # same selection as CI
pytest tests/ -q -m "not network" --cov=application --cov-report=term-missing
```

- Never contacts the network and never needs API keys, Whisper models or media.
- Translation providers run against mocked HTTP in
  `tests/test_translation_providers.py` (protocol, error normalization,
  retries, secrets never logged).
- GUI tests use `QT_QPA_PLATFORM=offscreen`; the screenshot gallery smoke test
  (`tests/test_screenshot_tool.py`) regenerates the full 74-shot,
  7-language gallery in a subprocess.
- The coverage floor lives in `[tool.coverage.report]` (pyproject.toml).

## Network-marked tests

```bash
pytest tests/ -q -m network
```

Three tests carry the `network` marker; none of them needs API credentials:

| Test | Needs | Notes |
|---|---|---|
| `tests/test_translation_free.py::test_free_google_translation` | Internet | keyless Google free tier; skips itself when offline |
| `tests/test_translation_free.py::test_parallel_vs_sequential_subtitles_translation` | Internet | same free tier, parallel vs sequential |
| `tests/test_e2e_real_media.py::test_04_free_translation_engine_on_real_subtitles` | Internet + media fixture | also skipped when `SRT4U_E2E_MEDIA` is unset |

DeepL, OpenAI-compatible and Ollama endpoints are covered deterministically
with mocked HTTP; live calls against those configurable providers are not part
of any suite and remain a manual maintenance activity (for example through the
`benchmark` CLI with real credentials).

### Manual workflow

The `Integration Tests (manual)` workflow (`.github/workflows/integration.yml`,
`workflow_dispatch` only) runs the network selection on a GitHub runner. It
never triggers on push, pull request or tags, and it does not publish
anything.

## Real Whisper inference (opt-in)

Prerequisites: the transcription extra, FFmpeg, a local media file and a model
(downloaded once on first use; never bundled).

```bash
python -m pip install '.[transcription]'
SRT4U_TEST_REAL_WHISPER=1 SRT4U_TEST_MEDIA=/path/clip.mp4 \
  python -m pytest tests/test_transcription_real.py -q -s
```

Environment variables:

- `SRT4U_TEST_REAL_WHISPER=1` — required opt-in switch.
- `SRT4U_TEST_MEDIA` — local audio/video file (a few seconds are enough).
- `SRT4U_TEST_MODEL` — model name, default `tiny`; larger models are slower.
- `SRT4U_WHISPER_MODEL_DIR` — optional cache relocation (also honored by the
  application).

A GPU is optional: with `device=auto` a failed CUDA initialization falls back
to CPU. Without the extra or the opt-in switch the test is skipped, never
passed.

## Real-media end-to-end (opt-in)

Prerequisites: FFmpeg/ffprobe on `PATH` and a fixture directory with exactly
these files:

- `S1pK5hmTzkE_1min.mp4` — 1920×1080, 60 fps, with audio, 60 s.
- `S1pK5hmTzkE_1min.srt` — 25 cues with overlaps and a 1 s gap.

```bash
SRT4U_E2E_MEDIA=/path/to/media python -m pytest tests/test_e2e_real_media.py -q
```

The whole module is skipped when either file is missing. It exercises parsing,
cleaning, translation, cross-format conversion, video metadata, ASS
generation, real burn-in and the GUI flows on genuine media; one of its tests
is network-marked (free Google translation).

## Coverage matrix

| Area | Deterministic suite | Opt-in | Live/real path exercised by |
|---|---|---|---|
| Parsing, cleaning, QA, analytics, conversion | yes | — | default suite |
| Translation protocol, errors, retries | yes (mocked HTTP) | — | default suite |
| Google free tier | — | `-m network` | manual run or manual workflow |
| DeepL / OpenAI-compatible / Ollama live calls | — | not covered | manual run with real credentials |
| Whisper provider wiring (fake backend) | yes | — | default suite |
| Real Whisper inference | — | `SRT4U_TEST_REAL_WHISPER=1` | manual run (model download) |
| Real media pipeline + burn-in | — | `SRT4U_E2E_MEDIA` | manual run (media fixture) |
| Windows/Linux/macOS packaging + launch smoke | CI builds | — | `Build & Release Multiplatform` |
