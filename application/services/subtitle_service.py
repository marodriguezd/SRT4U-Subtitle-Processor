import re
import os
import time
import threading
import concurrent.futures
from dataclasses import dataclass, field
from typing import Optional, Callable, List, Tuple

from ..logging_setup import get_logger
from .translation_service import TranslationService
from .subtitle_analytics import SubtitleAnalytics, SubtitleAnalyticsService
from .subtitle_qa import QAReport, QARules, SubtitleQA
from .translation_models import TranslationMetrics
from . import ass_utils

logger = get_logger("subtitles")


def ms_to_srt_time(ms: int) -> str:
    hours = ms // 3600000
    ms %= 3600000
    minutes = ms // 60000
    ms %= 60000
    seconds = ms // 1000
    milliseconds = ms % 1000
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"


def ms_to_vtt_time(ms: int) -> str:
    hours = ms // 3600000
    ms %= 3600000
    minutes = ms // 60000
    ms %= 60000
    seconds = ms // 1000
    milliseconds = ms % 1000
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"


def ms_to_ass_time(ms: int) -> str:
    """Format milliseconds as ``H:MM:SS.cc``.

    Delegates to :func:`ass_utils.ass_time` so the exporter and the burn-in
    path share one rounding policy (ASS stores centiseconds, so the value is
    rounded, never floored).
    """
    return ass_utils.ass_time(ms)


class SubtitleCancelledError(Exception):
    """Cooperative cancellation of a long subtitle operation.

    Raised by :meth:`SubtitleService.translate_subtitles` when the caller's
    ``cancel_event`` fires. Callers (GUI workers, the media pipeline) treat it
    as a normal, expected outcome: the current provider call is allowed to
    finish, no further cues are started, and no partial result is published.
    """


#: One structural problem found while parsing. Parsers never drop a block
#: silently: every skipped or repaired block produces one of these.
@dataclass
class ParseIssue:
    kind: str
    reason: str
    line: Optional[int] = None
    snippet: str = ""

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "reason": self.reason,
            "line": self.line,
            "snippet": self.snippet,
        }


def parse_timestamp_to_ms(time_str: str) -> int:
    """Convert ``HH:MM:SS,mmm`` / ``MM:SS.mmm`` to milliseconds.

    Contract: a well-formed timestamp returns an ``int``; anything else raises
    :class:`ValueError`. The previous silent ``return 0`` turned garbage into
    "the cue starts at zero", which quietly moved subtitles; callers must now
    decide explicitly how to report the problem (see ``ParseIssue``).

    Hours are not capped at two digits, so media longer than 99 hours round
    trips through SRT. Minutes and seconds must be ``00-59`` per the format.
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

    if not re.fullmatch(r"\d{1,}", raw_hours):
        raise ValueError(f"horas inválidas: {raw_hours!r}")
    if not re.fullmatch(r"\d{1,2}", raw_minutes):
        raise ValueError(f"minutos inválidos: {raw_minutes!r}")
    if "." in raw_seconds:
        raw_whole, _, raw_fraction = raw_seconds.partition(".")
    else:
        raw_whole, raw_fraction = raw_seconds, ""
    if not re.fullmatch(r"\d{1,2}", raw_whole):
        raise ValueError(f"segundos inválidos: {raw_whole!r}")
    # At most three fraction digits: "00:00:01,1234" is malformed, not 1.123 s.
    if raw_fraction and not re.fullmatch(r"\d{1,3}", raw_fraction):
        raise ValueError(f"fracción de segundo inválida: {raw_fraction!r}")

    hours = int(raw_hours)
    minutes = int(raw_minutes)
    seconds = int(raw_whole)
    if minutes > 59 or seconds > 59:
        raise ValueError(f"minutos/segundos fuera de rango (00-59): {normalized!r}")
    milliseconds = int(raw_fraction.ljust(3, "0")) if raw_fraction else 0
    return (hours * 3600 + minutes * 60 + seconds) * 1000 + milliseconds


@dataclass
class SubtitleItem:
    index: int
    start_ms: int
    end_ms: int
    text: str
    style: str = "Default"
    extra: str = ""

    def get_srt_time(self) -> str:
        return f"{ms_to_srt_time(self.start_ms)} --> {ms_to_srt_time(self.end_ms)}"

    def get_vtt_time(self) -> str:
        return f"{ms_to_vtt_time(self.start_ms)} --> {ms_to_vtt_time(self.end_ms)}"

    def get_ass_start(self) -> str:
        return ms_to_ass_time(self.start_ms)

    def get_ass_end(self) -> str:
        return ms_to_ass_time(self.end_ms)


@dataclass
class ProcessingStats:
    total_lines: int = 0
    deleted_lines: int = 0
    processed_items_count: int = 0
    elapsed_time: float = 0.0
    # Bloques que el motor de traducción no pudo traducir (mantienen el texto original)
    translation_failures: int = 0
    # Bloques que el parser no pudo usar (timestamp inválido, evento mal formado).
    # Antes se descartaban en silencio; ahora son visibles para el usuario.
    parse_issues: int = 0


@dataclass
class ProcessingResult:
    stats: ProcessingStats
    original_items: List[SubtitleItem] = field(default_factory=list)
    processed_items: List[SubtitleItem] = field(default_factory=list)
    output_content: str = ""
    analytics: Optional[SubtitleAnalytics] = None
    qa_report: Optional[QAReport] = None
    translation_metrics: Optional[TranslationMetrics] = None
    #: ``True`` only when a complete, usable output was produced. The same
    #: meaning is used by ``record_pipeline_result`` (L2), so history never
    #: records a failed run as successful just because it had no metrics.
    success: bool = True
    #: Structural problems found while parsing (skipped/repaired blocks).
    parse_issues: List[ParseIssue] = field(default_factory=list)


@dataclass
class _CueTranslation:
    """Complete, self-contained outcome of translating one cue.

    Workers return this instead of mutating shared lists, which is what makes
    metric attribution independent of thread scheduling (deep-audit H2).
    """

    position: int
    item: SubtitleItem
    metrics: Optional[TranslationMetrics]
    failed: bool
    error_type: Optional[str]
    fallback_error_type: Optional[str]
    providers_used: List[str]
    cancelled: bool = False


class SubtitleService:
    """
    Motor de procesamiento de subtítulos para SRT, VTT, ASS y TXT.
    """

    # Spam is detected in two tiers, because "contains a token" and "is spam"
    # are not the same statement (deep-audit H1).
    #
    # TIER 1 - the WHOLE line is spam. These patterns are matched with
    # ``fullmatch`` against the stripped line, so any additional words make the
    # line survive. This is what keeps real dialogue intact:
    #     "I went to www.city.com yesterday."      -> kept
    #     "The rarbg group released it."           -> kept
    #     "I downloaded it from opensubtitles."    -> kept
    #     "www.city.com"                           -> removed
    #     "Subtitled by AnimeFansubPro"            -> removed
    #: Lines that are spam on their own: bare URLs, bare site tags, credits
    #: and music placeholders.
    #:
    #: Attribution phrases ("Subtitled by ...", "Subtitulos sincronizados
    #: por ...") are unambiguous credit markers, so they may appear after a
    #: short lead-in. The release-site tokens deliberately do NOT allow a
    #: lead-in: that is exactly what separates a bare "YTS.MX" credit line from
    #: the dialogue "The rarbg group released it.".
    WHOLE_LINE_SPAM_PATTERNS = [
        # Attribution / credit lines.
        r"(?i).*\bsubtitled?\s+by\b.*",
        r"(?i).*\bsubtitulad[oa]s?\s+(?:por|de)\b.*",
        r"(?i).*\bsubt[ií]tulos\s+(?:por|de|sincronizad[oa]s?\s+por)\b.*",
        r"(?i).*\btraducci[oó]n\s+(?:de|por)\b.*",
        r"(?i).*\bripped\s+by\b.*",
        r"(?i).*\bencoded\s+by\b.*",
        r"(?i).*\bsync(?:ed|hronized|hronizado|hronizad[oa]s?)\s+by\b.*",
        r"(?i).*\b(?:downloaded|descargad[oa]o?)\s+from\b.*",
        r"(?i).*\bdescargad[oa]s?\s+de\b.*",
        r"(?i).*\brelease\s*:\s*\S+.*",
        r"(?i).*\buploads?\s+(?:by|from)\b.*",
        r"(?i).*\bsubtitled?\s+by\s*:.*",
        # Bare links: the line is nothing but the link.
        r"(?i)https?://\S+",
        r"(?i)www\.[a-z0-9\-]+(?:\.[a-z0-9\-]+)*\.[a-z]{2,}",
        r"(?i)t\.me/[a-zA-Z0-9_\-]+",
        r"(?i)joinchat/[a-zA-Z0-9_\-]+",
        r"(?i)telegram:?\s*@\w+",
        # Bare release-site tags, e.g. a cue that is only "YTS.MX".
        r"(?i)(?:yts|rarbg|yify|opensubtitles|addic7ed|subscene)"
        r"[\w.\-]*(?:\.(?:com|org|net|mx|to|ru|me|io|ly))?",
        # Music / sound placeholders.
        r"[-~]?♪.*?♪[-~]?",
        r"♪+",
        r"♫+",
        r"(?i)\[[^\]]*music[^\]]*\]",
        r"(?i)\([^\)]*music[^\)]*\)",
        # Site taglines.
        r"(?i)we\s*compress\s*knowledge\s*for\s*you!?",
    ]

    #: Lines that are spam only when they *advertise* something. The call to
    #: action must open the line, which is what separates an ad from a
    #: first-person statement that happens to mention the same place:
    #     "Visit us at www.site.org for more."  -> removed
    #:     "I visited https://example.org."     -> kept
    PROMOTIONAL_VERBS = (
        r"visit|download|watch|stream|get|grab|click|support|rate|join|"
        r"order|follow|subscribe|suscrib"
    )
    #: Something that identifies *where* the content comes from.
    SOURCE_REFERENCE = (
        r"https?://\S+|www\.[a-z0-9\-]+(?:\.[a-z0-9\-]+)*\.[a-z]{2,}|"
        r"t\.me/\S+|telegram|\b(?:yts|rarbg|yify|opensubtitles|addic7ed|"
        r"subscene)\b"
    )
    PROMOTIONAL_PATTERNS = [
        rf"(?i)^(?:please\s+|por\s+favor\s+)?(?:{PROMOTIONAL_VERBS})\b.*"
        rf"(?:{SOURCE_REFERENCE}).*",
        rf"(?i)^(?:please\s+)?(?:available|descarga(?:r|lo)?|disponible)\b"
        rf".*(?:{SOURCE_REFERENCE}).*",
        r"(?i)^(?:watch|stream)\b.*\bfree\b.*",
        r"(?i)^full\s+(?:movie|episode|season)\b.*",
    ]

    #: Explicit advertising with no link at all.
    ADVERTISEMENT_PATTERNS = [
        r"(?i)^(?:your|our)\s+(?:free\s+)?(?:subtitles?|subs)\s+"
        r"(?:are\s+)?(?:available|provided|offered)\b.*",
        r"(?i)^donate\s+(?:to\s+)?(?:our|this)\s+project\b.*",
        r"(?i)^support\s+(?:our|this)\s+(?:channel|project|subs)\b.*",
        r"(?i)^rate\s+(?:this|our)\s+(?:movie|film|episode|video)\b.*",
    ]

    #: Kept for backwards compatibility with the historical attribute name.
    DEFAULT_SPAM_PATTERNS = WHOLE_LINE_SPAM_PATTERNS

    def __init__(
        self,
        translation_service: Optional[TranslationService] = None,
        batch_size: int = 50,
        qa_rules: Optional[QARules] = None,
    ):
        self.translation_service = translation_service or TranslationService()
        self.batch_size = batch_size
        self.qa_service = SubtitleQA(qa_rules)
        self.analytics_service = SubtitleAnalyticsService(qa_rules)
        self.last_translation_metrics: Optional[TranslationMetrics] = None
        self._last_translation_started_at: Optional[float] = None
        self.last_translation_failures = 0
        self.spam_patterns = [re.compile(p) for p in self.WHOLE_LINE_SPAM_PATTERNS]
        self.promotional_patterns = [re.compile(p) for p in self.PROMOTIONAL_PATTERNS]
        self.advertisement_patterns = [
            re.compile(p) for p in self.ADVERTISEMENT_PATTERNS
        ]
        #: Structural problems found by the last parse. Never silently empty.
        self.last_parse_issues: List[ParseIssue] = []
        #: Style definitions recovered by the last ASS parse, so a round trip
        #: can preserve them instead of emitting undefined style references.
        self._last_ass_styles: dict = {}
        cpu_threads = os.cpu_count() or 4
        self.max_workers = max(1, round(cpu_threads * 0.8))

    def detect_format(self, content: str, file_path: Optional[str] = None) -> str:
        if file_path:
            ext = os.path.splitext(file_path)[1].lower()
            if ext in [".srt", ".vtt", ".ass", ".ssa", ".txt"]:
                return "ass" if ext in [".ass", ".ssa"] else ext.lstrip(".")

        stripped = content.strip()
        if stripped.startswith("WEBVTT"):
            return "vtt"
        if "[Script Info]" in content or "[Events]" in content:
            return "ass"
        if "\n00:" in content or "\n1\n00:" in content or " --> " in content:
            return "srt"
        return "txt"

    def parse_subtitles(
        self, content: str, file_format: str = "srt"
    ) -> List[SubtitleItem]:
        format_lower = file_format.lower()
        self.last_parse_issues = []
        self._last_ass_styles = {}
        if format_lower == "vtt":
            return self._parse_vtt(content)
        elif format_lower in ["ass", "ssa"]:
            return self._parse_ass(content)
        elif format_lower == "txt":
            return self._parse_txt(content)
        return self._parse_srt(content)

    def _add_issue(
        self, kind: str, reason: str, line: Optional[int] = None, snippet: str = ""
    ) -> None:
        """Record a block that could not be used, so nothing is lost silently."""
        self.last_parse_issues.append(
            ParseIssue(
                kind=kind,
                reason=reason,
                line=line,
                snippet=snippet[:120],
            )
        )

    def _safe_timestamps(
        self,
        start_raw: str,
        end_raw: str,
        line: Optional[int] = None,
        snippet: str = "",
    ) -> Optional[Tuple[int, int]]:
        """Parse a cue's timestamps, reporting instead of guessing."""
        try:
            start_ms = parse_timestamp_to_ms(start_raw)
            end_ms = parse_timestamp_to_ms(end_raw)
        except ValueError as exc:
            self._add_issue(
                "invalid_timestamp", str(exc), line, f"{start_raw} --> {end_raw}"
            )
            return None
        if end_ms < start_ms:
            self._add_issue(
                "reversed_timing",
                f"el final ({end_ms} ms) precede al inicio ({start_ms} ms)",
                line,
                f"{start_raw} --> {end_raw}",
            )
            return None
        return start_ms, end_ms

    def _parse_srt(self, content: str) -> List[SubtitleItem]:
        """Parse SRT by walking lines, not by splitting on blank lines.

        Splitting on blank lines silently truncated any cue that contained an
        internal blank line and then discarded the remainder as an orphan
        block. Here a cue starts at its timestamp line and runs until the next
        timestamp line, so multi-paragraph cues survive intact.
        """
        items: List[SubtitleItem] = []
        lines = (content or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
        # Hours are unbounded so that >99h media round trips through SRT (L5).
        ts_regex = re.compile(
            r"(\d{1,}:\d{2}:\d{2}[,.]\d{1,3})\s*-->\s*(\d{1,}:\d{2}:\d{2}[,.]\d{1,3})"
        )

        def find_timing(value: str):
            match = ts_regex.search(value)
            return match if match else None

        index = 0
        position = 0
        total = len(lines)
        first_timing_line = None
        while position < total:
            match = find_timing(lines[position])
            if match is None:
                position += 1
                continue
            if first_timing_line is None:
                first_timing_line = position
            start_line = position
            timings = self._safe_timestamps(
                match.group(1), match.group(2), start_line + 1, lines[start_line]
            )
            position += 1
            text_lines: List[str] = []
            while position < total and find_timing(lines[position]) is None:
                candidate = lines[position]
                # A bare number immediately followed by the next cue's timecode
                # is that cue's index, not dialogue. Stop before it.
                if candidate.strip().isdigit():
                    lookahead = position + 1
                    while lookahead < total and not lines[lookahead].strip():
                        lookahead += 1
                    if lookahead < total and find_timing(lines[lookahead]):
                        break
                text_lines.append(candidate)
                position += 1
            if timings is None:
                # ``_safe_timestamps`` already recorded the specific reason;
                # adding a generic one here would double-count every block.
                continue
            start_ms, end_ms = timings
            text = "\n".join(text_lines).strip("\n")
            if not text.strip():
                self._add_issue(
                    "empty_cue",
                    "el cue no contiene texto",
                    start_line + 1,
                    lines[start_line],
                )
                continue
            index += 1
            items.append(
                SubtitleItem(index=index, start_ms=start_ms, end_ms=end_ms, text=text)
            )

        # Text that precedes the very first timecode belongs to no cue; report
        # it instead of dropping it without a trace. A bare cue number is the
        # index of the first cue, not lost content.
        if first_timing_line:
            for offset in range(first_timing_line):
                candidate = lines[offset].strip()
                if candidate and not candidate.isdigit():
                    self._add_issue(
                        "unattached_text",
                        "texto anterior al primer timecode",
                        offset + 1,
                        lines[offset],
                    )
        return items

    def _parse_vtt(self, content: str) -> List[SubtitleItem]:
        lines = (content or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
        items: List[SubtitleItem] = []
        ts_regex = re.compile(
            r"((?:\d{1,}:)?\d{2}:\d{2}[.]\d{1,3})\s*-->\s*((?:\d{1,}:)?\d{2}:\d{2}[.]\d{1,3})"
        )

        curr_idx = 1
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if not line or line.startswith("WEBVTT") or line.startswith("NOTE"):
                i += 1
                continue

            match = ts_regex.search(line)
            extra = ""
            if not match and i + 1 < len(lines):
                match = ts_regex.search(lines[i + 1].strip())
                if match:
                    line = lines[i + 1].strip()
                    i += 1

            if match:
                time_line_full = line
                timing_line = i
                after_match = time_line_full[match.end() :].strip()
                if after_match:
                    extra = after_match

                text_lines = []
                i += 1
                while i < len(lines) and lines[i].strip():
                    text_lines.append(lines[i].strip())
                    i += 1

                timings = self._safe_timestamps(
                    match.group(1), match.group(2), timing_line + 1, time_line_full
                )
                text = "\n".join(text_lines)
                if timings is None:
                    self._add_issue(
                        "cue_dropped",
                        "la cue tiene un timestamp no utilizable",
                        timing_line + 1,
                        time_line_full,
                    )
                    continue
                start_ms, end_ms = timings
                if not text.strip():
                    self._add_issue(
                        "empty_cue",
                        "la cue no contiene texto",
                        timing_line + 1,
                        time_line_full,
                    )
                    continue
                items.append(
                    SubtitleItem(
                        index=curr_idx,
                        start_ms=start_ms,
                        end_ms=end_ms,
                        text=text,
                        extra=extra,
                    )
                )
                curr_idx += 1
            else:
                i += 1
        return items

    def _parse_ass(self, content: str) -> List[SubtitleItem]:
        items: List[SubtitleItem] = []
        # One regex decides both "is this a dialogue line" and "what are its
        # fields". The previous code guarded on a case-sensitive
        # startswith("Dialogue:") and then matched case-insensitively, so the
        # IGNORECASE flag was dead and lowercase "dialogue:" was dropped.
        dialogue_regex = re.compile(
            r"^Dialogue:[ \t]*[^,]*,"  # layer
            r"([^,]*),([^,]*),([^,]*),"  # start, end, style
            r"([^,]*),([^,]*),([^,]*),([^,]*),([^,]*),"  # name, margins, effect
            r"(.*)$",
            re.IGNORECASE,
        )
        self._last_ass_styles = ass_utils.parse_style_definitions(content)
        curr_idx = 1
        for number, line in enumerate((content or "").splitlines(), start=1):
            line_str = line.strip()
            if not line_str:
                continue
            lowered = line_str.lower()
            if lowered.startswith("comment:") or lowered.startswith("picture:"):
                continue
            if not lowered.startswith("dialogue:"):
                continue

            match = dialogue_regex.match(line_str)
            if not match:
                self._add_issue(
                    "malformed_dialogue",
                    "línea Dialogue con número de campos incorrecto",
                    number,
                    line_str,
                )
                continue
            start_str, end_str, style = (
                match.group(1).strip(),
                match.group(2).strip(),
                match.group(3).strip(),
            )
            raw_text = match.group(9)
            timings = self._safe_timestamps(start_str, end_str, number, line_str)
            if timings is None:
                continue
            start_ms, end_ms = timings
            if style and not ass_utils.is_safe_style_name(style):
                self._add_issue(
                    "unsafe_style_name",
                    f"el nombre de estilo {style!r} no es utilizable",
                    number,
                    line_str,
                )
                style = ass_utils.DEFAULT_STYLE_NAME
            text = raw_text.replace(r"\N", "\n").replace(r"\n", "\n")
            if not text.strip():
                self._add_issue(
                    "empty_cue", "el evento no contiene texto", number, line_str
                )
                continue
            items.append(
                SubtitleItem(
                    index=curr_idx,
                    start_ms=start_ms,
                    end_ms=end_ms,
                    text=text,
                    style=style or ass_utils.DEFAULT_STYLE_NAME,
                )
            )
            curr_idx += 1
        return items

    def _parse_txt(self, content: str) -> List[SubtitleItem]:
        items: List[SubtitleItem] = []
        curr_ms = 0
        curr_idx = 1
        for line in content.splitlines():
            text = line.strip()
            if not text:
                continue
            duration = max(2000, len(text) * 60)
            items.append(
                SubtitleItem(
                    index=curr_idx,
                    start_ms=curr_ms,
                    end_ms=curr_ms + duration,
                    text=text,
                )
            )
            curr_ms += duration + 500
            curr_idx += 1
        return items

    def analyze_subtitles(
        self,
        items: List[SubtitleItem],
        *,
        file_format: Optional[str] = None,
        source_content: Optional[str] = None,
        processing_time_seconds: float = 0.0,
        lines_removed: int = 0,
        translation_failures: int = 0,
        reference_items: Optional[List[SubtitleItem]] = None,
    ) -> Tuple[SubtitleAnalytics, QAReport]:
        """Return reusable analytics and deterministic QA for already-parsed cues."""
        report = self.qa_service.validate(
            items, file_format, source_content, reference_items
        )
        analytics = self.analytics_service.analyze(
            items,
            file_format=file_format,
            source_content=source_content,
            processing_time_seconds=processing_time_seconds,
            lines_removed=lines_removed,
            translation_failures=translation_failures,
            qa_report=report,
        )
        return analytics, report

    def qa_subtitles(
        self,
        items: List[SubtitleItem],
        *,
        file_format: Optional[str] = None,
        source_content: Optional[str] = None,
        reference_items: Optional[List[SubtitleItem]] = None,
    ) -> QAReport:
        """Run only QA on parsed cues, independently of analytics and presentation."""
        return self.qa_service.validate(
            items, file_format, source_content, reference_items
        )

    def qa_file(self, file_path: str) -> QAReport:
        """Read and parse one subtitle file, returning its standalone QA report."""
        with open(file_path, "r", encoding="utf-8", errors="replace") as source_file:
            content = source_file.read()
        file_format = self.detect_format(content, file_path)
        items = self.parse_subtitles(content, file_format)
        return self.qa_subtitles(items, file_format=file_format, source_content=content)

    def analyze_file(self, file_path: str) -> Tuple[SubtitleAnalytics, QAReport]:
        """Read, detect, and parse a subtitle file once before returning analytics and QA."""
        with open(file_path, "r", encoding="utf-8", errors="replace") as source_file:
            content = source_file.read()
        file_format = self.detect_format(content, file_path)
        items = self.parse_subtitles(content, file_format)
        return self.analyze_subtitles(
            items, file_format=file_format, source_content=content
        )

    def is_spam_line(self, line: str) -> bool:
        """Classify one subtitle line as spam.

        A line is only removed when the *whole line* is spam, or when it opens
        with a call to action and names a source. Merely mentioning a site, a
        URL or a release tag inside a sentence is dialogue, not spam.
        """
        stripped = (line or "").strip()
        if not stripped:
            return False
        if any(pattern.fullmatch(stripped) for pattern in self.spam_patterns):
            return True
        if any(pattern.search(stripped) for pattern in self.promotional_patterns):
            return True
        if any(pattern.search(stripped) for pattern in self.advertisement_patterns):
            return True
        return False

    def clean_subtitles(
        self, items: List[SubtitleItem]
    ) -> Tuple[List[SubtitleItem], int, int]:
        cleaned_items: List[SubtitleItem] = []
        total_lines = 0
        deleted_lines = 0

        for item in items:
            lines = item.text.split("\n")
            kept_lines = []
            for line in lines:
                total_lines += 1
                if not line.strip():
                    # Blank padding is not a line of dialogue; drop it without
                    # counting it as deleted content.
                    continue
                if self.is_spam_line(line):
                    deleted_lines += 1
                    logger.debug("Línea de spam eliminada: %s", line.strip()[:80])
                    continue
                kept_lines.append(line.strip())

            if kept_lines:
                item_cleaned = SubtitleItem(
                    index=len(cleaned_items) + 1,
                    start_ms=item.start_ms,
                    end_ms=item.end_ms,
                    text="\n".join(kept_lines),
                    style=item.style,
                    extra=item.extra,
                )
                cleaned_items.append(item_cleaned)
            elif item.text.strip():
                logger.debug(
                    "Cue %s eliminado por completo (todas sus líneas eran spam)",
                    item.index,
                )

        return cleaned_items, total_lines, deleted_lines

    def translate_subtitles(
        self,
        items: List[SubtitleItem],
        target_language: str,
        source_language: str = "auto",
        engine: str = "google",
        parallel: bool = True,
        progress_callback: Optional[Callable[[str, object], None]] = None,
        cancel_event: Optional["threading.Event"] = None,
    ) -> List[SubtitleItem]:
        """Translate cues, preserving order and per-cue metric attribution.

        Concurrency contract (deep-audit H2): a worker never touches a shared
        collection. It receives its own cue, does its work against the
        thread-local translation state, and *returns* a complete
        :class:`_CueTranslation` record. The coordinator then rebuilds the
        output in the original order, so neither the metrics nor the reported
        error type can depend on which thread happened to finish first.

        ``cancel_event`` implements cooperative cancellation (H3): no new cue
        is started once it is set, the in-flight provider call is allowed to
        finish, the thread pool is always shut down cleanly, and
        :class:`SubtitleCancelledError` is raised instead of returning a
        partial result.
        """
        total_items = len(items)
        self._last_translation_started_at = time.perf_counter()
        self.last_translation_failures = 0
        self.last_translation_metrics = None
        if total_items == 0:
            self.last_translation_metrics = TranslationMetrics.aggregate(
                [],
                source_language=source_language,
                target_language=target_language,
                number_of_cues=0,
                characters_input=0,
                characters_output=0,
                words_input=0,
                words_output=0,
                duration_ms=0,
                success=True,
                requested_provider=engine,
            )
            return []

        def cancelled() -> bool:
            return cancel_event is not None and cancel_event.is_set()

        if cancelled():
            raise SubtitleCancelledError("traducción cancelada")

        def translate_single_item(idx: int, item: SubtitleItem) -> "_CueTranslation":
            original_text = item.text.strip()
            if not original_text:
                return _CueTranslation(
                    position=idx,
                    item=item,
                    metrics=None,
                    failed=False,
                    error_type=None,
                    fallback_error_type=None,
                    providers_used=[],
                )
            if cancelled():
                return _CueTranslation(
                    position=idx,
                    item=item,
                    metrics=None,
                    failed=False,
                    error_type=None,
                    fallback_error_type=None,
                    providers_used=[],
                    cancelled=True,
                )

            try:
                if hasattr(self.translation_service, "clear_last_result"):
                    self.translation_service.clear_last_result()
                translated_text = self.translation_service.translate_text(
                    text=original_text,
                    target_language=target_language,
                    source_language=source_language,
                    engine=engine,
                )
                last_result = getattr(self.translation_service, "last_result", None)
                engine_error = getattr(self.translation_service, "last_error", None)
                if last_result is not None:
                    metric = last_result.metrics
                else:
                    metric = TranslationMetrics.for_text(
                        provider=engine,
                        model=None,
                        source_language=source_language,
                        target_language=target_language,
                        source_text=original_text,
                        translated_text=translated_text,
                        duration_ms=0,
                        success=engine_error is None,
                        error_type="unknown" if engine_error else None,
                        requested_provider=engine,
                        providers_used=[engine],
                        error_message="unknown" if engine_error else None,
                    )
                if engine_error:
                    # Mutate only this thread's own object; no shared lookup.
                    metric.success = False
                    if not metric.error_type:
                        metric.error_type = "unknown"
                    logger.warning(
                        "El provider '%s' no pudo traducir el cue %s: error_type=%s",
                        engine,
                        item.index,
                        metric.error_type,
                    )
                new_item = SubtitleItem(
                    index=item.index,
                    start_ms=item.start_ms,
                    end_ms=item.end_ms,
                    text=translated_text,
                    style=item.style,
                    extra=item.extra,
                )
                return _CueTranslation(
                    position=idx,
                    item=new_item,
                    metrics=metric,
                    failed=bool(engine_error),
                    error_type=metric.error_type if engine_error else None,
                    fallback_error_type=metric.fallback_error_type,
                    providers_used=list(metric.providers_used or [metric.provider]),
                )
            except SubtitleCancelledError:
                raise
            except Exception as exc:
                logger.error(
                    "Excepción al traducir el cue %s con el provider '%s' (%s)",
                    item.index,
                    engine,
                    type(exc).__name__,
                )
                return _CueTranslation(
                    position=idx,
                    item=item,
                    metrics=TranslationMetrics.for_text(
                        provider=engine,
                        model=None,
                        source_language=source_language,
                        target_language=target_language,
                        source_text=original_text,
                        translated_text=original_text,
                        duration_ms=0,
                        success=False,
                        error_type="unknown",
                        requested_provider=engine,
                        providers_used=[engine],
                        error_message=None,
                    ),
                    failed=True,
                    error_type="unknown",
                    fallback_error_type=None,
                    providers_used=[engine],
                )

        records: List[Optional[_CueTranslation]] = [None] * total_items
        completed = 0
        cancelled_early = False

        if parallel:
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=self.max_workers
            ) as executor:
                future_to_idx = {}
                for i, item in enumerate(items):
                    if cancelled():
                        cancelled_early = True
                        break
                    future_to_idx[executor.submit(translate_single_item, i, item)] = i
                for future in concurrent.futures.as_completed(future_to_idx):
                    record = future.result()
                    records[record.position] = record
                    completed += 1
                    if progress_callback:
                        progress_callback("step_translating", (completed, total_items))
        else:
            for i, item in enumerate(items):
                if cancelled():
                    cancelled_early = True
                    break
                record = translate_single_item(i, item)
                records[record.position] = record
                completed += 1
                if progress_callback:
                    progress_callback("step_translating", (completed, total_items))

        if cancelled_early or any(
            record is not None and record.cancelled for record in records
        ):
            # Leave no partial state behind: the next job must not read a
            # half-finished translation.
            self.last_translation_failures = 0
            self.last_translation_metrics = None
            raise SubtitleCancelledError("traducción cancelada")

        # Deterministic reconstruction: input order, never completion order.
        ordered: List[_CueTranslation] = [r for r in records if r is not None]
        translation_metrics = [r.metrics for r in ordered if r.metrics is not None]
        failed_records = [r for r in ordered if r.failed]

        self.last_translation_failures = len(failed_records)
        providers_used = list(
            dict.fromkeys(
                provider for record in ordered for provider in record.providers_used
            )
        )
        input_texts = [item.text.strip() for item in items if item.text.strip()]
        output_texts = [r.item.text.strip() for r in ordered if r.item.text.strip()]
        failed = bool(failed_records)
        self.last_translation_metrics = TranslationMetrics.aggregate(
            translation_metrics,
            source_language=source_language,
            target_language=target_language,
            number_of_cues=len(input_texts),
            characters_input=sum(len(text) for text in input_texts),
            characters_output=sum(len(text) for text in output_texts),
            words_input=sum(len(text.split()) for text in input_texts),
            words_output=sum(len(text.split()) for text in output_texts),
            duration_ms=(
                int((time.perf_counter() - self._last_translation_started_at) * 1000)
                if self._last_translation_started_at is not None
                else None
            ),
            success=not failed,
            requested_provider=engine,
            providers_used=providers_used,
            # Deterministic: the first failure in *cue* order, not in the order
            # the worker threads happened to finish.
            error_type=failed_records[0].error_type if failed_records else None,
            error_message=None,
            fallback_error_type=next(
                (
                    record.fallback_error_type
                    for record in ordered
                    if record.fallback_error_type
                ),
                None,
            ),
        )
        if failed_records:
            logger.warning(
                "Traducción incompleta: %s de %s cues mantienen el texto original (error_type=%s)",
                self.last_translation_failures,
                total_items,
                failed_records[0].error_type or "unknown",
            )

        return [record.item for record in ordered]

    def format_output(
        self,
        items: List[SubtitleItem],
        target_format: str = "srt",
        *,
        ass_styles: Optional[dict] = None,
    ) -> str:
        """Render cues in one of the supported formats.

        ``ass_styles`` optionally supplies style name -> definition body for
        ``ass``/``ssa`` output; it defaults to the definitions recovered by the
        last ASS parse. SRT/VTT/TXT ignore it.
        """
        fmt = target_format.lower().lstrip(".")
        if fmt == "vtt":
            return self._format_vtt(items)
        elif fmt in ["ass", "ssa"]:
            return self._format_ass(items, styles=ass_styles)
        elif fmt == "txt":
            return self._format_txt(items)
        return self._format_srt(items)

    def _format_srt(self, items: List[SubtitleItem]) -> str:
        blocks = []
        for idx, item in enumerate(items, 1):
            blocks.append(f"{idx}\n{item.get_srt_time()}\n{item.text}\n")
        return "\n".join(blocks).strip() + "\n"

    def _format_vtt(self, items: List[SubtitleItem]) -> str:
        """Render WebVTT.

        ``SubtitleItem.extra`` carries the cue settings that followed the
        timestamp (``line:80% align:middle``). WebVTT can express them, so they
        are preserved here; SRT has no field for them and dropping them is an
        expected, documented loss, not a silent corruption.
        """
        lines = ["WEBVTT\n"]
        for idx, item in enumerate(items, 1):
            cue_line = item.get_vtt_time()
            if item.extra:
                cue_line += f" {item.extra}"
            lines.append(f"{idx}\n{cue_line}\n{item.text}\n")
        return "\n".join(lines).strip() + "\n"

    def _format_ass(
        self, items: List[SubtitleItem], styles: Optional[dict] = None
    ) -> str:
        """Render ASS using the shared rendering contract.

        Text goes through :func:`ass_utils.to_ass_text`, the exact same
        transformation the burn-in path uses, so exporting to ``.ass`` and
        burning into a video can never disagree about the same cue. Every style
        referenced by an event is declared in the header, using the real
        definition when the source document provided one.
        """
        known = styles if styles is not None else self._last_ass_styles
        used_styles = [item.style or ass_utils.DEFAULT_STYLE_NAME for item in items]
        definitions = ass_utils.collect_style_definitions(used_styles, known or {})
        events = []
        for item in items:
            style = item.style or ass_utils.DEFAULT_STYLE_NAME
            if style not in definitions:
                style = ass_utils.DEFAULT_STYLE_NAME
            events.append(
                (item.start_ms, item.end_ms, ass_utils.to_ass_text(item.text))
            )
        return ass_utils.build_ass_document(
            events, definitions, title="SRT4U Exported Subtitles"
        )

    def _format_txt(self, items: List[SubtitleItem]) -> str:
        return "\n".join(item.text for item in items).strip() + "\n"

    def process_subtitles(
        self,
        file_path: str,
        do_clean: bool = True,
        do_translate: bool = False,
        target_language: Optional[str] = None,
        source_language: str = "auto",
        engine: str = "google",
        target_format: Optional[str] = None,
        parallel: bool = True,
        progress_callback: Optional[Callable[[str, object], None]] = None,
        cancel_event: Optional[threading.Event] = None,
    ) -> ProcessingResult:
        start_time = time.time()

        # Paso 1: Lectura
        if progress_callback:
            progress_callback("step_reading", True)

        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()

        source_format = self.detect_format(content, file_path)
        out_format = target_format or source_format

        # Paso 2: Análisis
        if progress_callback:
            progress_callback("step_analyzing", True)

        original_items = self.parse_subtitles(content, source_format)
        parse_issues = list(self.last_parse_issues)
        if parse_issues:
            logger.warning(
                "El parser no pudo usar %s bloque(s) del archivo: %s",
                len(parse_issues),
                ", ".join(sorted({issue.kind for issue in parse_issues})),
            )
        current_items = list(original_items)
        total_original_lines = sum(len(it.text.split("\n")) for it in original_items)
        deleted_lines_count = 0

        # Paso 3: Limpieza
        if do_clean:
            if progress_callback:
                progress_callback("step_cleaning", True)
            current_items, total_original_lines, deleted_lines_count = (
                self.clean_subtitles(current_items)
            )

        # Paso 4: Traducción
        translation_failures = 0
        if do_translate and target_language:
            if progress_callback:
                progress_callback("step_translating", (0, len(current_items)))
            current_items = self.translate_subtitles(
                items=current_items,
                target_language=target_language,
                source_language=source_language,
                engine=engine,
                parallel=parallel,
                progress_callback=progress_callback,
                cancel_event=cancel_event,
            )
            translation_failures = self.last_translation_failures

        # Paso 5: Aplicar formato original
        if progress_callback:
            progress_callback("step_formatting", True)

        output_content = self.format_output(current_items, out_format)

        # Paso 6: Guardado
        if progress_callback:
            progress_callback("step_saving", True)

        analytics, qa_report = self.analyze_subtitles(
            current_items,
            file_format=out_format,
            source_content=output_content,
            lines_removed=deleted_lines_count,
            translation_failures=translation_failures,
            reference_items=original_items if do_translate else None,
        )
        elapsed = time.time() - start_time
        stats = ProcessingStats(
            total_lines=total_original_lines,
            deleted_lines=deleted_lines_count,
            processed_items_count=len(current_items),
            elapsed_time=round(elapsed, 2),
            translation_failures=translation_failures,
            parse_issues=len(parse_issues),
        )
        analytics.processing.processing_time_seconds = round(elapsed, 3)

        return ProcessingResult(
            stats=stats,
            original_items=original_items,
            processed_items=current_items,
            output_content=output_content,
            analytics=analytics,
            qa_report=qa_report,
            translation_metrics=self.last_translation_metrics if do_translate else None,
            success=bool(current_items) or not original_items,
            parse_issues=parse_issues,
        )

    def write_output_file(self, path: str, content: str) -> None:
        """Write rendered subtitles to ``path`` without ever truncating it first.

        Deep-audit L9: the previous code opened the destination directly, so an
        interrupted export destroyed the user's previous good file. The content
        now lands in a sibling temporary file and is renamed into place.
        """
        from .atomic_write import atomic_write_text

        atomic_write_text(path, content, encoding="utf-8")
