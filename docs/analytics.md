# Subtitle analytics and QA

SRT4U exposes deterministic, reusable analytics over the existing parsed
`SubtitleItem` cue model. The implementation is independent of PyQt6 and is
available to the desktop flow and the headless CLI through `SubtitleService`.

## Metrics and definitions

Analytics are grouped to distinguish content, timing, quality, and processing:

- **Content**: cue count, words and visible characters (HTML/ASS formatting
  markup excluded), averages and maxima per cue, line count, empty cues, and
  repeated non-empty text. A duplicate is each repeated cue after the first;
  text comparison ignores case and repeated whitespace.
- **Timing**: duration span from the earliest valid cue start to latest valid
  cue end in milliseconds; average/min/max CPS over valid positive-duration
  cues with visible text; overlap, duration, and CPS violation counts. Overlap
  counts cues that overlap at least one other cue, not overlapping pairs. A
  touching end/start boundary is not an overlap.
- **Quality**: error/warning/info counts and counts by rule, including long
  lines.
- **Processing**: elapsed processing seconds, cleaned lines, and translation
  failures. A standalone analysis reports zero processing values because no
  processing pipeline was run.

Characters and words measure visible subtitle dialogue (format tags excluded).
Line lengths are measured individually. Values are rounded to three decimal
places where they are ratios/times. TXT files receive synthetic cue times from
the existing parser; timing metrics for TXT describe those generated values,
not original media synchronization. Empty/unparseable files have zero parsed
cues; QA reports a file-structure warning/error where possible.

## QA rules and defaults

`QARules` is immutable and passed to `SubtitleQA` or `SubtitleService`:

| Rule setting | Default | Interpretation |
|---|---:|---|
| `max_cps` | 20 | Warn above 20 visible characters per second |
| `max_characters_per_line` | 42 | Warn above 42 visible characters on any line |
| `min_duration_ms` | 1000 | Warn below one second |
| `max_duration_ms` | 7000 | Warn above seven seconds |

Invalid or non-positive cue intervals and malformed source timecodes are
errors. Empty cues, overlaps, duplicate text, unbalanced/changed formatting
tags, and threshold violations are warnings. Non-monotonic input ordering is
informational. SRT timecodes and basic SRT numbering, VTT headers/timecodes,
and ASS/SSA event sections/Dialogue timecodes are checked deterministically.
Malformed raw blocks omitted by the existing parser are still reported by
source-structure validation. Threshold boundaries are accepted (`duration ==
min/max`, `CPS == max`, and line length equal to the maximum do not violate the
rule).

## CLI

```bash
python -m application.cli analyze input.srt
python -m application.cli analyze input.srt --json
python -m application.cli qa input.srt
python -m application.cli qa input.srt --json --output report.json
python -m application.cli analyze input.srt --format csv --output metrics.csv
```

JSON on stdout contains grouped analytics and an attached QA report for
`analyze`, or the QA report for `qa`. Use `--output` with `.json` or `.csv` to
export. QA exits with code `1` when it finds errors, `0` when no errors occur,
and `2` for input/output failures; warnings alone do not fail the QA command.
A missing/unsupported `--format` is reported by argparse. `--json` and CSV are
mutually exclusive so stdout remains machine-readable.

## Architecture decision

`SubtitleService` owns parsing and offers `analyze_file` (read/detect/parse once)
and `analyze_subtitles` (analyze already parsed cues). `SubtitleQA` owns
rule-based findings; `SubtitleAnalyticsService` aggregates the report and cue
metrics into grouped dataclasses. `ProcessingStats` remains a compatibility
view for current GUI consumers; `ProcessingResult` additionally carries
analytics and a QA report. This avoids creating another cue representation or
putting business logic in widgets. The models expose `to_dict()` for stable,
JSON-compatible output; CSV export is a CLI presentation layer.

Metrics unavailable from subtitle files (such as video-derived effective
screen duration or provider/model cost) are intentionally not guessed.

## Packaging check

The `.venv` used during development does not contain `setuptools`; therefore
`pip install --no-deps --no-build-isolation .` fails when pip tries to import
`setuptools.build_meta`. This is an environment limitation, not invalid project
metadata: the same wheel build with the system Python succeeds. A normal
isolated PEP 517 install/build will resolve the declared build requirement
(`setuptools>=68`) in its temporary build environment.
