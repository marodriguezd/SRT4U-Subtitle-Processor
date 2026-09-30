"""Shared timestamp grammar for parsing and QA (single source of truth).

Historically ``SubtitleService`` and ``SubtitleQA`` each carried their own
timestamp grammar and they silently diverged: the parser grew support for
>99-hour media and single-digit VTT hours while QA kept rejecting both, so a
file the product itself accepted was reported as structurally broken — and a
strict QA pipeline aborted on it. This module is now the only grammar: the
parsers validate with the same functions QA validates with, so the two layers
cannot disagree again.

Contract (mirrors the original ``parse_timestamp_to_ms``):

* a well-formed timestamp returns an integer number of milliseconds;
* anything else raises :class:`ValueError`;
* minutes and seconds must be ``00-59``;
* hours are unbounded (media longer than 99 hours round trips);
* the fractional part carries at most three digits (SRT/VTT milliseconds).
"""

import re
from typing import Optional, Tuple

_HOURS = r"\d{1,}"
_MINUTES = r"\d{1,2}"
_SECONDS = r"\d{1,2}"
_FRACTION = r"\d{1,3}"

#: Full SRT clock ``H:MM:SS`` with unbounded hours (``HH:MM:SS`` ⊂ grammar),
#: optional 1-3 digit fraction separated by ``,`` or ``.``.
_SRT_CLOCK_RE = re.compile(
    rf"({_HOURS}):({_MINUTES}):({_SECONDS})(?:[.,]({_FRACTION}))?"
)

#: WebVTT clock ``[H:]MM:SS`` with a mandatory ``.`` fraction; the whole
#: hours component is optional (``00:01.000`` is hourless WebVTT) and one- or
#: two-digit hours are both accepted (matching the parser's grammar).
_VTT_CLOCK_RE = re.compile(
    rf"(?:(?:({_HOURS})):)?(?:({_MINUTES})):({_SECONDS})[.]({_FRACTION})"
)

#: ASS/SSA clock ``H:MM:SS`` with centiseconds (ASS stores 1/100 s). One
#: capturing group per component (the pre-existing QA layout).
ASS_TIMESTAMP_PATTERN = r"(\d{1,}):(\d{1,2}):(\d{1,2})\.(\d{1,2})"

#: ASS/SSA Dialogue timing pair: two full ASS clocks separated by a comma.
#: Anchoring the end timestamp to the field boundary (``...cc,``) removes the
#: ambiguity where a start timestamp's tail (``0:00:01.00`` -> trailing
#: ``00``) could be misread as a second clock.
ASS_DIALOGUE_TIMING_RE = re.compile(
    rf"({ASS_TIMESTAMP_PATTERN}),(?:{ASS_TIMESTAMP_PATTERN}),",
    re.IGNORECASE,
)
#: Full-line timestamp patterns for the ``SubtitleService`` parsers: one
#: capturing group per timestamp, built from the very same component grammar
#: above (non-capturing) so the line-level regex used to find cues cannot
#: drift from the validation QA performs on each component. Exactly one
#: capturing group per pattern keeps the parsers' ``match.group(1)/(2)``
#: layout stable.
SRT_TIMESTAMP_PATTERN = (
    rf"(?:{_HOURS}):(?:{_MINUTES}):(?:{_SECONDS})[,.](?:{_FRACTION})"
)
VTT_TIMESTAMP_PATTERN = (
    rf"(?:(?:{_HOURS}):)?(?:{_MINUTES}):(?:{_SECONDS})[.](?:{_FRACTION})"
)


def _clock_to_ms(hours: str, minutes: str, seconds: str) -> int:
    """Validate range bounds and convert validated clock components to ms."""
    if int(minutes) > 59 or int(seconds) > 59:
        raise ValueError(
            f"minutos/segundos fuera de rango (00-59): {hours}:{minutes}:{seconds}"
        )
    return (int(hours) * 3600 + int(minutes) * 60 + int(seconds)) * 1000


def _validate_fraction(raw_fraction: str, original: str) -> int:
    if raw_fraction and not re.fullmatch(_FRACTION, raw_fraction):
        raise ValueError(f"fracción de segundo inválida: {original!r}")
    return int(raw_fraction.ljust(3, "0")) if raw_fraction else 0


def parse_timestamp_to_ms(time_str: str) -> int:
    """Convert ``HH:MM:SS,mmm`` / ``MM:SS.mmm`` to milliseconds.

    The previous silent ``return 0`` turned garbage into "the cue starts at
    zero"; callers must now decide explicitly how to report the problem (see
    ``ParseIssue``). Same behaviour as the original implementation; it simply
    lives here now so parser and QA share it.
    """
    if not isinstance(time_str, str):
        raise ValueError("el timestamp debe ser una cadena")
    normalized = time_str.strip().replace(",", ".")
    if not normalized:
        raise ValueError("timestamp vacío")
    parts = normalized.split(":")
    if len(parts) == 3:
        raw_hours, raw_minutes, raw_seconds = parts
    elif len(parts) == 2:
        raw_hours, raw_minutes, raw_seconds = "0", parts[0], parts[1]
    else:
        raise ValueError(f"formato de timestamp no soportado: {time_str!r}")

    if not re.fullmatch(_HOURS, raw_hours):
        raise ValueError(f"horas inválidas: {raw_hours!r}")
    if not re.fullmatch(_MINUTES, raw_minutes):
        raise ValueError(f"minutos inválidos: {raw_minutes!r}")
    if "." in raw_seconds:
        raw_whole, _, raw_fraction = raw_seconds.partition(".")
    else:
        raw_whole, raw_fraction = raw_seconds, ""
    if not re.fullmatch(_SECONDS, raw_whole):
        raise ValueError(f"segundos inválidos: {raw_whole!r}")

    milliseconds = _clock_to_ms(raw_hours, raw_minutes, raw_whole)
    return milliseconds + _validate_fraction(raw_fraction, time_str)


def srt_timestamp_to_ms(timestamp: str) -> Optional[int]:
    """Parse one full SRT timestamp (clock + optional fraction); ``None`` if bad.

    Component-wise (no string rewrite), aligned with the parser: unbounded
    hours, minutes/seconds bounded to 00-59, 1-3 fraction digits separated by
    ``,`` or ``.``. This is the function ``SubtitleQA`` uses for its
    structural ``invalid_timecode`` check.
    """
    if not isinstance(timestamp, str):
        return None
    match = _SRT_CLOCK_RE.fullmatch(timestamp.strip())
    if not match:
        return None
    try:
        ms = _clock_to_ms(match.group(1), match.group(2), match.group(3))
    except ValueError:
        return None
    fraction = match.group(4)
    if fraction:
        ms += int(fraction.ljust(3, "0"))
    return ms


def vtt_timestamp_to_ms(timestamp: str) -> Optional[int]:
    """Parse one full WebVTT timestamp (clock + mandatory fraction); ``None`` if bad.

    The hours component is optional (``MM:SS.mmm`` is hourless WebVTT) and
    single-digit hours are valid (matching both the parser and the WebVTT
    practice for long media).
    """
    if not isinstance(timestamp, str):
        return None
    match = _VTT_CLOCK_RE.fullmatch(timestamp.strip())
    if not match:
        return None
    hours = match.group(1) or "0"
    try:
        ms = _clock_to_ms(hours, match.group(2), match.group(3))
    except ValueError:
        return None
    return ms + int(match.group(4).ljust(3, "0"))


def ass_timestamp_to_ms(timestamp: str) -> Optional[int]:
    """Parse one ASS/SSA ``H:MM:SS.cc`` timestamp; ``None`` when invalid.

    Hours are unbounded (media longer than 99 hours), minutes/seconds are
    bounded to 00-59 and the fraction is the ASS centisecond field (1-2
    digits), matching the clock components the parser accepts for ASS via
    :func:`parse_timestamp_to_ms`.
    """
    if not isinstance(timestamp, str):
        return None
    match = re.fullmatch(ASS_TIMESTAMP_PATTERN, timestamp.strip())
    if not match:
        return None
    try:
        ms = _clock_to_ms(match.group(1), match.group(2), match.group(3))
    except ValueError:
        return None
    return ms + int(match.group(4).ljust(2, "0")) * 10


def ass_dialogue_timing_to_ms(line: str) -> Optional[Tuple[int, int]]:
    """Extract ``(start_ms, end_ms)`` from a Dialogue line; ``None`` if bad.

    The two-timestamp layout is matched as one anchored expression (see
    ``ASS_DIALOGUE_TIMING_RE``) so a well-formed Dialogue line can never be
    misread at its field boundaries.
    """
    if not isinstance(line, str):
        return None
    match = ASS_DIALOGUE_TIMING_RE.search(line)
    if not match:
        return None
    # group(1) is the whole start clock; the start components are groups
    # 2-5. The end clock is non-capturing at its outer level, so its
    # components are groups 6-9 (hour, minute, second, centiseconds).
    try:
        start = _clock_to_ms(match.group(2), match.group(3), match.group(4))
        end = _clock_to_ms(match.group(6), match.group(7), match.group(8))
    except ValueError:
        return None
    start += int(match.group(5).ljust(2, "0")) * 10
    end += int(match.group(9).ljust(2, "0")) * 10
    return start, end
