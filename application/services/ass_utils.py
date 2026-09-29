"""Canonical ASS rendering contract for SRT4U (no PyQt6, no domain deps).

Both ASS producers in the project — the ``.ass`` exporter
(``SubtitleService._format_ass``) and the burn-in generator
(``VideoBurnerService.generate_ass_script``) — render the very same
``SubtitleItem`` model. They must therefore agree byte for byte on how
``SubtitleItem.text`` becomes an ASS event body, otherwise the same subtitle
renders differently depending on whether the user exported it or burned it.

The canonical model is deliberately simple: ``SubtitleItem.text`` is *plain
text* that may additionally contain

* literal ``{`` and ``}`` characters, and
* the SRT/SubStation markup subset SRT4U itself understands:
  ``<i>``, ``</i>``, ``<b>``, ``</b>``, ``<u>``, ``</u>``.

Rendering order (this order *is* the contract, do not reorder):

1. Escape every ``{``/``}`` as ``\\{``/``\\}``. In ASS a brace opens an override
   block, so user text must never be able to inject ``\\b1``, ``\\p1`` (drawing
   mode), ``\\pos``, ``\\t`` or any other tag. Escaping first means our own
   tags — added in step 2 — are still emitted as real overrides.
2. Translate the supported ``<i>/<b>/<u>`` markup into real override tags.
   These are the *only* tags SRT4U ever generates.
3. Turn real newlines into ``\\N`` (ASS hard line break).

Styles live in the same module: a document must define every style it
references, otherwise a renderer silently falls back to its own defaults and
the styling is lost (M2). ``parse_style_definitions`` recovers the real
definitions from a source document so a round trip can preserve them.
"""

from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

#: v4+ style format line shared by every SRT4U ASS document.
STYLE_FORMAT = (
    "Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
    "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, "
    "Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, "
    "MarginV, Encoding"
)

#: Fallback definition used when a style is referenced but never declared.
FALLBACK_STYLE_BODY = (
    "Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,"
    "0,0,0,0,100,100,0,0,1,2,2,2,10,10,10,1"
)

DEFAULT_STYLE_NAME = "Default"

#: Markup SRT4U translates into genuine ASS override tags.
_TAG_MAP = (
    ("<i>", r"{\i1}"),
    ("</i>", r"{\i0}"),
    ("<b>", r"{\b1}"),
    ("</b>", r"{\b0}"),
    ("<u>", r"{\u1}"),
    ("</u>", r"{\u0}"),
)


def escape_ass_braces(text: str) -> str:
    """Escape user braces so they can never open an ASS override block."""
    return text.replace("{", r"\{").replace("}", r"\}")


def apply_markup_tags(text: str) -> str:
    """Translate the supported ``<i>/<b>/<u>`` markup into override tags."""
    for source, target in _TAG_MAP:
        text = text.replace(source, target)
    return text


def to_ass_text(text: str) -> str:
    """Render one ``SubtitleItem.text`` value as an ASS event body.

    This is *the* canonical transformation; every ASS producer must use it.
    """
    rendered = escape_ass_braces(text or "")
    rendered = apply_markup_tags(rendered)
    return rendered.replace("\r\n", "\n").replace("\r", "\n").replace("\n", r"\N")


def ass_time(ms: int) -> str:
    """Format milliseconds as an ASS timestamp (``H:MM:SS.cc``).

    ASS stores centiseconds, so the value is *rounded* to the nearest
    centisecond rather than truncated: flooring shifts every single cue up to
    9 ms early, and rounding can carry correctly across second/minute/hour
    boundaries (999 ms -> 0:00:01.00, 59999 ms -> 0:01:00.00).
    """
    if ms < 0:
        ms = 0
    total_cs = (ms + 5) // 10
    centiseconds = total_cs % 100
    total_seconds = total_cs // 100
    seconds = total_seconds % 60
    minutes = (total_seconds // 60) % 60
    hours = total_seconds // 3600
    return f"{hours:d}:{minutes:02d}:{seconds:02d}.{centiseconds:02d}"


def is_safe_style_name(name: str) -> bool:
    """A style name must be usable as a bare field inside a Dialogue line."""
    return bool(name) and "," not in name and "\n" not in name and "\r" not in name


def parse_style_definitions(content: str) -> Dict[str, str]:
    """Recover ``{style name: definition body}`` from an ASS/SSA document.

    Only the ``[V4+ Styles]``/``[V4 Styles]`` sections are read, and the
    section's own ``Format:`` line is honoured so files with a different
    field order are still mapped correctly. Malformed or unusable names are
    ignored rather than reproduced in the output.
    """
    definitions: Dict[str, str] = {}
    in_styles = False
    for raw_line in (content or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("["):
            lowered = line.lower()
            in_styles = lowered in ("[v4+ styles]", "[v4 styles]", "[styles]")
            continue
        if not in_styles:
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip().lower()
        value = value.strip()
        if key == "format":
            continue
        if key not in ("style", "styleext"):
            continue
        name, _, body = value.partition(",")
        name = name.strip()
        if not is_safe_style_name(name) or not body.strip():
            continue
        definitions[name] = body.strip()
    return definitions


def build_ass_document(
    events: Sequence[Tuple[str, str, str]],
    style_definitions: Optional[Mapping[str, str]] = None,
    *,
    title: str = "SRT4U Subtitles",
    play_res: Optional[Tuple[int, int]] = None,
) -> str:
    """Assemble a complete ASS document.

    ``events`` is an ordered sequence of ``(start_ms, end_ms, event_body)``
    tuples, where ``event_body`` already went through :func:`to_ass_text`.
    ``style_definitions`` maps style name -> definition body. Every style that
    appears in the events is guaranteed to be declared in the header, so a
    renderer never has to fall back silently (M2).
    """
    definitions: Dict[str, str] = {}
    if style_definitions:
        for name, body in style_definitions.items():
            if is_safe_style_name(name) and body.strip():
                definitions[name] = body.strip()
    definitions.setdefault(DEFAULT_STYLE_NAME, FALLBACK_STYLE_BODY)

    style_lines = "\n".join(
        f"Style: {name},{definitions[name]}" for name in sorted(definitions)
    )
    resolution = ""
    if play_res:
        resolution = f"PlayResX: {int(play_res[0])}\nPlayResY: {int(play_res[1])}\n"

    header = (
        "[Script Info]\n"
        f"Title: {title}\n"
        "ScriptType: v4.00+\n"
        "WrapStyle: 0\n"
        "ScaledBorderAndShadow: yes\n"
        "YCbCr Matrix: TV.601\n"
        f"{resolution}"
        "\n"
        "[V4+ Styles]\n"
        f"Format: {STYLE_FORMAT}\n"
        f"{style_lines}\n"
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, "
        "Effect, Text\n"
    )

    lines: List[str] = []
    for start_ms, end_ms, body in events:
        lines.append(
            f"Dialogue: 0,{ass_time(start_ms)},{ass_time(end_ms)},"
            f"{DEFAULT_STYLE_NAME},,0,0,0,,{body}"
        )
    return header + "\n".join(lines) + "\n"


def collect_style_definitions(
    styles: Iterable[str],
    known: Optional[Mapping[str, str]] = None,
) -> Dict[str, str]:
    """Return definitions for every referenced style, never omitting one."""
    known = known or {}
    resolved: Dict[str, str] = {}
    for raw_name in styles:
        name = raw_name or DEFAULT_STYLE_NAME
        if not is_safe_style_name(name):
            name = DEFAULT_STYLE_NAME
        if name in resolved:
            continue
        resolved[name] = known.get(name) or FALLBACK_STYLE_BODY
    resolved.setdefault(DEFAULT_STYLE_NAME, FALLBACK_STYLE_BODY)
    return resolved
