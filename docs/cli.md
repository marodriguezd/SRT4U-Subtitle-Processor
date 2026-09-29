# SRT4U CLI (headless)

The CLI runs subtitle processing without creating a Qt application. It reuses
`SubtitleService.process_subtitles`, the same business operation used by the
desktop application, and supports SRT, VTT, ASS/SSA, and TXT files.

## Run

From a source checkout:

```bash
python -m application.cli process input.srt --output output.srt --clean
```

Install the CLI entry point and base desktop stack with
`python -m pip install .` (the `desktop` extra remains a compatibility alias).
The equivalent console command is `srt4u`:

```bash
srt4u process input.srt --output output.srt --clean
srt4u process input.srt --output translated.srt --translate --source auto --target es --engine ollama
srt4u process ./input --output ./output --config pipeline.json
```

`ollama` selects the existing OpenAI-compatible endpoint integration; set its
base URL and model in SRT4U's existing settings before using it. The CLI does
not print or expose configured credentials. Translation providers may fall back
according to the existing `TranslationService` behavior.

For a directory, supported subtitle files are discovered recursively and their
relative paths are preserved under the output directory. With multiple files
and no `--output`, results go to `./srt4u-output`. A single file without an
output path produces `<name>_processed.<format>` next to the input; inputs are
never overwritten by default. `--format` chooses a common output format, or the
output file extension selects the format for a single-file job.

Use `--no-clean` / `--no-translate` to override preset booleans and
`--sequential` to disable parallel translation. Translation requires `--target`
(or a `target_language` in the preset). `--stats` prints human-readable
translation metrics; `--stats-json` prints the same `TranslationMetrics` as a
single JSON object per processed file without changing the subtitle output.

## History

`process`, `analyze` and `qa` record each execution in the local SQLite
history (auxiliary: a database failure only logs a warning). `benchmark`
stores results with `--store`. Query it without SQL:

```bash
srt4u history --limit 20
srt4u history --provider ollama --fallback-only
srt4u history --errors-only --json
srt4u history --stats
```

`--db` overrides the database path per command; `process` also accepts
`--no-history`. See [docs/database.md](database.md).

## JSON pipeline preset

Presets are deliberately small JSON documents rather than a general workflow
language. CLI flags override values in the preset.

```json
{
  "pipeline": {
    "clean": true,
    "translate": false,
    "source_language": "auto",
    "engine": "google",
    "convert_to": "vtt",
    "parallel": true
  }
}
```

Supported keys are `clean`, `translate`, `source_language`, `target_language`,
`engine`, `target_format` (or its alias `convert_to`), and `parallel`. Analysis and
QA are available as standalone CLI commands; they are not steps in this processing
preset. Burn-in and arbitrary workflow steps remain out of scope.

## Technical decision

The CLI is an orchestration/argument-validation layer, not another processor:
it calls the existing service and writes its returned content. This avoids
separate implementations of parsing, cleaning, translation, or formatting.
JSON uses Python's standard library, so presets add no runtime dependency.
CLI subtitle processing does not create a Qt application. Some other service
modules, including the i18n service and the FFmpeg burner, import PyQt6, so a
full wheel-level Qt-free import guarantee is not claimed. YAML, a generic
pipeline engine, and an additional business-logic facade are outside the
current CLI scope.
