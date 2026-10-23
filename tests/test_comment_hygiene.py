"""Guard against decorative and redundant comments.

An earlier cleanup removed banners, numbered narration, empty labels and
multi-line prose. This test keeps them from coming back without flagging the
comments that carry real information: ``#:`` documentation, linter directives
and audit tags are always exempt, and a block of three or more explanatory
lines is reported because it should be one or two.
"""

import io
import re
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = ("application", "tests", "tools")
SINGLE_FILES = ("main.py", "conftest.py")

DIRECTIVE = re.compile(
    r"^(noqa\b|type:\s*ignore\b|pragma:\s*no\s*cover\b|fmt:\s*|isort:\s*"
    r"|mypy:\s*|ruff:\s*|deep-audit\b)"
)
AUDIT_TAG = re.compile(r"^[A-Z]\d+(?:/[A-Z]\d+)*:?(\s|$)")
SEPARATOR = re.compile(r"^[-=*_#~+\s]{3,}$")
BANNER = re.compile(r"^[=\-*#~]{2,}\s*\S.*\s*[=\-*#~]{2,}$")
CAPS_BANNER = re.compile(r"^[A-Z0-9 ,&/()'\-:]{12,}$")
NUMERIC_ONLY = re.compile(r"^\d+[.)]?$")
STEP_NARRATION = re.compile(r"^(\d+[.)]|(?:step|paso)\s+\d+[:.)]?)\s", re.I)
BARE_TODO = re.compile(r"^(TODO|FIXME|XXX|HACK)\s*:?\s*$", re.I)
EMOJI = re.compile("[\U0001f300-\U0001faff\u2705\u274c\u26a0\u2b50\u2714\u2716]")

EMPTY_LABELS = {
    "main logic",
    "core logic",
    "business logic",
    "helper function",
    "entry point",
    "error handling",
    "initialization",
    "setup",
    "imports",
    "implementation",
    "workflow",
    "routes",
    "note",
    "important",
    "note: important",
    "note: this is important",
}

MAX_PROSE_LINES = 2


def _target_files():
    files = [ROOT / name for name in SINGLE_FILES]
    for directory in TARGETS:
        files.extend(sorted((ROOT / directory).rglob("*.py")))
    return [path for path in files if path.is_file()]


def _exempt(body):
    """Directives, audit tags, shebangs and ``#:`` docs set the contract."""
    return body.startswith((":", "!")) or bool(
        DIRECTIVE.match(body) or AUDIT_TAG.match(body)
    )


def _classify(path):
    source = path.read_text(encoding="utf-8")
    lines = source.splitlines()
    tokens = tokenize.generate_tokens(io.StringIO(source).readline)

    offenders = []
    full_line = []
    for token in tokens:
        if token.type != tokenize.COMMENT:
            continue
        body = token.string.lstrip("#").strip()
        line_no = token.start[0]
        if lines[line_no - 1].strip().startswith("#"):
            full_line.append((line_no, body))
        if _exempt(body):
            continue

        label = body.lower().rstrip(".")
        reason = None
        if SEPARATOR.match(body) or BANNER.match(body):
            reason = "decorative separator/banner"
        elif CAPS_BANNER.match(body) and body.upper() == body:
            reason = "ALL CAPS banner"
        elif NUMERIC_ONLY.match(body):
            reason = "comment that is only a number"
        elif STEP_NARRATION.match(body):
            reason = "numbered step narration"
        elif label in EMPTY_LABELS:
            reason = "empty label"
        elif BARE_TODO.match(body):
            reason = "bare TODO"
        elif EMOJI.search(body):
            reason = "decorative emoji"
        if reason:
            offenders.append((line_no, reason, token.string.strip()))

    run = []
    for line_no, body in [*full_line, (10**9, "")]:
        if run and line_no == run[-1][0] + 1 and not _exempt(body):
            run.append((line_no, body))
            continue
        if len(run) > MAX_PROSE_LINES:
            offenders.append((run[0][0], f"{len(run)}-line comment block", run[0][1]))
        run = [(line_no, body)] if not _exempt(body) else []

    return sorted(offenders)


def test_comments_have_no_decorative_or_redundant_patterns():
    """No banners, numbered narration, empty labels or 3+ line prose blocks."""
    findings = []
    for path in _target_files():
        for line_no, reason, text in _classify(path):
            findings.append(f"{path.relative_to(ROOT)}:{line_no}: {reason}: {text}")

    assert not findings, "Comment hygiene regressions:\n" + "\n".join(findings)
