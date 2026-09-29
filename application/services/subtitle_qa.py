"""Deterministic subtitle QA rules over SRT4U's existing cue model."""

import heapq
import json
import math
import re
from abc import ABC, abstractmethod
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    Iterable,
    List,
    Optional,
    Sequence,
    Set,
    Tuple,
)

if TYPE_CHECKING:
    from .subtitle_service import SubtitleItem


@dataclass(frozen=True)
class QARules:
    """Configurable thresholds; values equal to a limit are accepted."""

    max_cps: float = 20.0
    max_characters_per_line: int = 42
    max_lines: int = 2
    min_duration_ms: int = 1000
    max_duration_ms: int = 7000

    def __post_init__(self):
        if (
            isinstance(self.max_cps, bool)
            or not isinstance(self.max_cps, (int, float))
            or not math.isfinite(self.max_cps)
            or self.max_cps <= 0
        ):
            raise ValueError("max_cps debe ser un número finito mayor que cero")
        integer_limits = (
            self.max_characters_per_line,
            self.max_lines,
            self.min_duration_ms,
            self.max_duration_ms,
        )
        if any(
            isinstance(value, bool) or not isinstance(value, int)
            for value in integer_limits
        ):
            raise ValueError(
                "los límites de líneas, caracteres y duración deben ser enteros"
            )
        if self.max_characters_per_line <= 0:
            raise ValueError("max_characters_per_line debe ser mayor que cero")
        if self.max_lines <= 0:
            raise ValueError("max_lines debe ser mayor que cero")
        if self.min_duration_ms < 0:
            raise ValueError("min_duration_ms no puede ser negativo")
        if self.max_duration_ms <= 0:
            raise ValueError("max_duration_ms debe ser mayor que cero")
        if self.min_duration_ms > self.max_duration_ms:
            raise ValueError("min_duration_ms no puede superar max_duration_ms")

    @property
    def min_duration(self) -> float:
        """Minimum cue duration in seconds, for display/configuration clients."""
        return self.min_duration_ms / 1000

    @property
    def max_duration(self) -> float:
        """Maximum cue duration in seconds, for display/configuration clients."""
        return self.max_duration_ms / 1000


@dataclass
class QAFinding:
    severity: str
    rule: str
    subtitle_index: Optional[int]
    message: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.severity not in {"error", "warning", "info"}:
            raise ValueError("severity debe ser error, warning o info")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class QAReport:
    findings: List[QAFinding] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        return sum(finding.severity == "error" for finding in self.findings)

    @property
    def warning_count(self) -> int:
        return sum(finding.severity == "warning" for finding in self.findings)

    @property
    def info_count(self) -> int:
        return sum(finding.severity == "info" for finding in self.findings)

    @property
    def passed(self) -> bool:
        """Default policy: warnings are advisory; errors make a report fail."""
        return self.error_count == 0

    @property
    def strict_passed(self) -> bool:
        """Strict policy: any warning or error makes a report fail."""
        return self.error_count == 0 and self.warning_count == 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "strict_passed": self.strict_passed,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "info_count": self.info_count,
            "findings": [finding.to_dict() for finding in self.findings],
        }


class SubtitleQARule(ABC):
    """Extension point for a deterministic rule; rule instances should be stateless."""

    @abstractmethod
    def validate(
        self,
        items: Sequence["SubtitleItem"],
        rules: QARules,
        findings: List[QAFinding],
    ) -> None:
        """Append findings for the provided cues."""


class _CueIndexRule(SubtitleQARule):
    def validate(self, items, rules, findings):
        first_by_index: Dict[int, int] = {}
        for position, item in enumerate(items):
            index = item.index
            if isinstance(index, bool) or not isinstance(index, int) or index <= 0:
                findings.append(
                    QAFinding(
                        "error",
                        "invalid_index",
                        index
                        if isinstance(index, int) and not isinstance(index, bool)
                        else None,
                        "El índice del cue debe ser un entero positivo.",
                    )
                )
            elif index in first_by_index:
                findings.append(
                    QAFinding(
                        "error",
                        "duplicate_index",
                        index,
                        "El índice del cue está repetido.",
                        {"first_position": first_by_index[index] + 1},
                    )
                )
            else:
                first_by_index[index] = position


class _TimingRule(SubtitleQARule):
    """Check intervals and find overlapping cues in O(n log n) time."""

    def validate(self, items, rules, findings):
        active_heap: List[Tuple[int, int]] = []
        active_positions: Set[int] = set()
        overlap_partners: Dict[int, int] = {}
        ordered = sorted(
            enumerate(items),
            key=lambda pair: (pair[1].start_ms, pair[1].end_ms, pair[0]),
        )

        for position, item in ordered:
            while active_heap and active_heap[0][0] <= item.start_ms:
                _, expired_position = heapq.heappop(active_heap)
                active_positions.discard(expired_position)
            if item.start_ms < 0 or item.end_ms <= item.start_ms:
                findings.append(
                    QAFinding(
                        "error",
                        "invalid_timecode",
                        item.index,
                        "El cue tiene un intervalo temporal inválido.",
                        {"start_ms": item.start_ms, "end_ms": item.end_ms},
                    )
                )
                continue

            if active_positions:
                # A representative partner bounds the findings for dense overlaps;
                # emitting every overlapping pair can grow quadratically.
                partner_position = active_heap[0][1]
                overlap_partners.setdefault(partner_position, position)
                overlap_partners.setdefault(position, partner_position)
            active_positions.add(position)
            heapq.heappush(active_heap, (item.end_ms, position))

        for position, partner_position in sorted(overlap_partners.items()):
            findings.append(
                QAFinding(
                    "warning",
                    "overlap",
                    items[position].index,
                    "El intervalo del cue se solapa con otro subtítulo.",
                    {"overlaps_with": [items[partner_position].index]},
                )
            )


class _CueOrderRule(SubtitleQARule):
    def validate(self, items, rules, findings):
        previous_valid = None
        for item in items:
            if item.start_ms < 0 or item.end_ms <= item.start_ms:
                continue
            if previous_valid is not None and item.start_ms < previous_valid.start_ms:
                findings.append(
                    QAFinding(
                        "info",
                        "non_monotonic_order",
                        item.index,
                        "El cue aparece fuera del orden temporal.",
                        {
                            "start_ms": item.start_ms,
                            "previous_start_ms": previous_valid.start_ms,
                        },
                    )
                )
            previous_valid = item


class _ContentRule(SubtitleQARule):
    """Check text shape, duplicates, duration, and reading speed in one pass."""

    def validate(self, items, rules, findings):
        first_by_text: Dict[str, int] = {}
        for item in items:
            visible = SubtitleQA.visible_text(item.text)
            lines = visible.splitlines()
            normalized = " ".join(visible.split()).casefold()
            if not normalized:
                findings.append(
                    QAFinding(
                        "warning",
                        "empty_subtitle",
                        item.index,
                        "El cue no contiene texto visible.",
                    )
                )
            elif normalized in first_by_text:
                findings.append(
                    QAFinding(
                        "warning",
                        "duplicate_subtitle",
                        item.index,
                        "El texto del cue está duplicado.",
                        {"first_subtitle_index": first_by_text[normalized]},
                    )
                )
            else:
                first_by_text[normalized] = item.index

            if len(lines) > rules.max_lines:
                findings.append(
                    QAFinding(
                        "warning",
                        "too_many_lines",
                        item.index,
                        "El cue supera el máximo de líneas configurado.",
                        {"line_count": len(lines), "maximum_lines": rules.max_lines},
                    )
                )
            for line_number, line in enumerate(lines, start=1):
                if not line.strip():
                    findings.append(
                        QAFinding(
                            "warning",
                            "empty_line",
                            item.index,
                            "El cue contiene una línea vacía.",
                            {"line_number": line_number},
                        )
                    )
                if len(line) > rules.max_characters_per_line:
                    findings.append(
                        QAFinding(
                            "warning",
                            "line_too_long",
                            item.index,
                            "La línea supera el máximo de caracteres configurado.",
                            {
                                "line_number": line_number,
                                "characters": len(line),
                                "maximum_characters": rules.max_characters_per_line,
                            },
                        )
                    )

            duration = item.end_ms - item.start_ms
            if item.start_ms < 0 or duration <= 0:
                continue
            if duration < rules.min_duration_ms:
                findings.append(
                    QAFinding(
                        "warning",
                        "duration_too_short",
                        item.index,
                        "La duración del cue es inferior al mínimo configurado.",
                        {"duration_ms": duration, "minimum_ms": rules.min_duration_ms},
                    )
                )
            if duration > rules.max_duration_ms:
                findings.append(
                    QAFinding(
                        "warning",
                        "duration_too_long",
                        item.index,
                        "La duración del cue supera el máximo configurado.",
                        {"duration_ms": duration, "maximum_ms": rules.max_duration_ms},
                    )
                )
            cps = sum(len(line) for line in lines) / (duration / 1000)
            if normalized and cps > rules.max_cps:
                findings.append(
                    QAFinding(
                        "warning",
                        "cps_exceeded",
                        item.index,
                        "La velocidad de lectura supera el máximo CPS configurado.",
                        {"cps": round(cps, 3), "maximum_cps": rules.max_cps},
                    )
                )


class _FormattingRule(SubtitleQARule):
    def validate(self, items, rules, findings):
        for item in items:
            stack = []
            for match in SubtitleQA._HTML_TAG.finditer(item.text):
                closing, tag_name, self_closing = match.groups()
                tag_name = tag_name.casefold()
                if tag_name in {"br", "hr", "img", "meta", "link"} or self_closing:
                    continue
                if closing:
                    if not stack or stack[-1] != tag_name:
                        findings.append(
                            QAFinding(
                                "warning",
                                "malformed_formatting_tag",
                                item.index,
                                "Las etiquetas HTML del cue no están equilibradas.",
                            )
                        )
                        break
                    stack.pop()
                else:
                    stack.append(tag_name)
            else:
                if stack:
                    findings.append(
                        QAFinding(
                            "warning",
                            "malformed_formatting_tag",
                            item.index,
                            "El cue contiene etiquetas HTML sin cerrar.",
                        )
                    )

            # ASS override blocks start with '{\\'; natural braces are ignored.
            residual_text = re.sub(r"\{\\[^}]*\}", "", item.text)
            unmatched_open = len(re.findall(r"\{\\", residual_text))
            unmatched_close = len(re.findall(r"\\[a-zA-Z][^}]*\}", residual_text))
            incomplete_html = re.search(
                r"</?(?:b|i|u|s|strike|em|strong|font|br|ruby|rt|c)(?:\s[^<>]*)?$",
                item.text,
                re.IGNORECASE,
            )
            if unmatched_open or unmatched_close:
                findings.append(
                    QAFinding(
                        "warning",
                        "malformed_formatting_tag",
                        item.index,
                        "Las etiquetas de estilo ASS del cue tienen llaves desequilibradas.",
                    )
                )
            if incomplete_html and not item.text.endswith(">"):
                findings.append(
                    QAFinding(
                        "warning",
                        "malformed_formatting_tag",
                        item.index,
                        "El cue contiene una etiqueta HTML incompleta.",
                    )
                )


class SubtitleQA:
    """Runs composable deterministic rules over parsed cues and source structure."""

    _SRT_TIMESTAMP = re.compile(
        r"^(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})\s*-->\s*"
        r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})(?:\s+.*)?$"
    )
    _VTT_TIMESTAMP = re.compile(
        r"^((?:\d{2,}:)?\d{2}:\d{2})\.(\d{1,3})\s*-->\s*"
        r"((?:\d{2,}:)?\d{2}:\d{2})\.(\d{1,3})(?:\s+.*)?$"
    )
    _ASS_TIME = re.compile(r"(\d{1,2}):(\d{2}):(\d{2})\.(\d{1,2})")
    _FORMATTING_TAG = re.compile(
        r"</?(?:b|i|u|s|strike|em|strong|font|br|ruby|rt|c)(?:\s[^<>]*)?/?>"
        r"|\{\\[^}]*\}",
        re.IGNORECASE,
    )
    _HTML_TAG = re.compile(
        r"<(/?)(b|i|u|s|strike|em|strong|font|br|ruby|rt|c)(?:\s[^>]*)?(/?)>",
        re.IGNORECASE,
    )
    DEFAULT_RULES: Tuple[SubtitleQARule, ...] = (
        _CueIndexRule(),
        _TimingRule(),
        _CueOrderRule(),
        _ContentRule(),
        _FormattingRule(),
    )

    def __init__(
        self,
        rules: Optional[QARules] = None,
        rule_set: Optional[Iterable[SubtitleQARule]] = None,
    ):
        self.rules = rules or QARules()
        self.rule_set = tuple(rule_set if rule_set is not None else self.DEFAULT_RULES)
        if any(not isinstance(rule, SubtitleQARule) for rule in self.rule_set):
            raise TypeError("rule_set solo puede contener instancias de SubtitleQARule")

    def validate(
        self,
        items: Sequence["SubtitleItem"],
        file_format: Optional[str] = None,
        source_content: Optional[str] = None,
        reference_items: Optional[Sequence["SubtitleItem"]] = None,
    ) -> QAReport:
        findings: List[QAFinding] = []
        for rule in self.rule_set:
            rule.validate(items, self.rules, findings)
        if source_content is not None and not source_content.strip():
            findings.append(
                QAFinding(
                    "warning", "empty_file", None, "El archivo no contiene subtítulos."
                )
            )
        if source_content is not None and file_format:
            self._validate_source(source_content, file_format.lower(), findings, items)
        if reference_items is not None:
            self._validate_formatting_tags(reference_items, items, findings)
        return self.deduplicate_findings(findings)

    @staticmethod
    def deduplicate_findings(findings: List[QAFinding]) -> QAReport:
        unique_findings = []
        seen_findings = set()
        for finding in findings:
            identity = (
                finding.severity,
                finding.rule,
                finding.subtitle_index,
                json.dumps(finding.metadata, sort_keys=True, ensure_ascii=False),
            )
            if identity not in seen_findings:
                seen_findings.add(identity)
                unique_findings.append(finding)
        return QAReport(unique_findings)

    @classmethod
    def visible_text(cls, text: str) -> str:
        """Remove common HTML/ASS formatting tags from readability calculations."""
        return cls._FORMATTING_TAG.sub("", text)

    def _validate_formatting_tags(self, reference_items, translated_items, findings):
        translated_by_index = {item.index: item for item in translated_items}
        for original in reference_items:
            expected = self._formatting_tags(original.text)
            if not expected:
                continue
            translated = translated_by_index.get(original.index)
            actual = self._formatting_tags(translated.text) if translated else []
            if sorted(expected) != sorted(actual):
                findings.append(
                    QAFinding(
                        "warning",
                        "formatting_tag_mismatch",
                        original.index,
                        "Las etiquetas de formato no coinciden con el cue de referencia.",
                        {"expected_tags": expected, "actual_tags": actual},
                    )
                )

    @staticmethod
    def _formatting_tags(text: str) -> List[str]:
        return SubtitleQA._FORMATTING_TAG.findall(text)

    def _validate_source(self, content, file_format, findings, parsed_items):
        if file_format in {"srt", "vtt"}:
            self._validate_timed_blocks(content, file_format, findings, parsed_items)
        elif file_format in {"ass", "ssa"}:
            self._validate_ass_source(content, findings)

    def _validate_timed_blocks(self, content, file_format, findings, parsed_items):
        if file_format == "vtt" and not re.match(
            r"^WEBVTT(?:\s|$)",
            content.lstrip("\ufeff \t\r\n"),
            re.IGNORECASE,
        ):
            findings.append(
                QAFinding("error", "invalid_format", None, "Falta la cabecera WEBVTT.")
            )
        if not content.strip():
            return

        blocks = re.split(r"\r?\n\s*\r?\n", content.strip())
        cue_number = 0
        declared_indices: Dict[int, int] = {}
        invalid_parsed_intervals = Counter(
            (item.start_ms, item.end_ms)
            for item in parsed_items
            if item.end_ms <= item.start_ms
        )
        pattern = self._SRT_TIMESTAMP if file_format == "srt" else self._VTT_TIMESTAMP
        for block in blocks:
            lines = [line.strip() for line in block.splitlines() if line.strip()]
            if not lines:
                continue
            if file_format == "vtt":
                if lines[0].upper() == "WEBVTT" or lines[0].upper().startswith(
                    "WEBVTT "
                ):
                    continue
                if lines[0].upper().startswith(("NOTE", "STYLE", "REGION")):
                    continue
                if "-->" not in lines[0] and len(lines) > 1 and "-->" in lines[1]:
                    lines = lines[1:]

            cue_number += 1
            time_line_index = next(
                (index for index, line in enumerate(lines) if "-->" in line), None
            )
            if file_format == "srt":
                if not lines[0].isdigit():
                    findings.append(
                        QAFinding(
                            "error",
                            "invalid_index",
                            cue_number,
                            "El cue SRT no tiene un índice numérico.",
                        )
                    )
                else:
                    declared = int(lines[0])
                    if declared <= 0:
                        findings.append(
                            QAFinding(
                                "error",
                                "invalid_index",
                                cue_number,
                                "El índice del cue SRT debe ser positivo.",
                                {"declared_index": declared},
                            )
                        )
                    elif declared in declared_indices:
                        findings.append(
                            QAFinding(
                                "error",
                                "duplicate_index",
                                cue_number,
                                "El índice del cue SRT está repetido.",
                                {
                                    "declared_index": declared,
                                    "first_position": declared_indices[declared],
                                },
                            )
                        )
                    else:
                        declared_indices[declared] = cue_number
                        if declared != cue_number:
                            findings.append(
                                QAFinding(
                                    "warning",
                                    "invalid_format",
                                    cue_number,
                                    "La numeración SRT no es consecutiva desde uno.",
                                    {
                                        "declared_index": declared,
                                        "expected_index": cue_number,
                                    },
                                )
                            )

            if time_line_index is None:
                findings.append(
                    QAFinding(
                        "error" if file_format == "srt" else "warning",
                        "invalid_timecode"
                        if file_format == "srt"
                        else "invalid_format",
                        cue_number,
                        "El bloque no contiene una línea de timecode válida.",
                    )
                )
                continue
            time_line = lines[time_line_index]
            match = pattern.fullmatch(time_line)
            if not match or not self._timestamp_components_valid(match, file_format):
                duplicate_parsed_interval = False
                if match and file_format == "srt":
                    groups = match.groups()
                    start_parts = tuple(int(value) for value in groups[:3])
                    end_parts = tuple(int(value) for value in groups[4:7])
                    start_ms = (
                        (start_parts[0] * 60 + start_parts[1]) * 60 + start_parts[2]
                    ) * 1000 + int(groups[3].ljust(3, "0"))
                    end_ms = (
                        (end_parts[0] * 60 + end_parts[1]) * 60 + end_parts[2]
                    ) * 1000 + int(groups[7].ljust(3, "0"))
                    interval = (start_ms, end_ms)
                    duplicate_parsed_interval = invalid_parsed_intervals[interval] > 0
                    if duplicate_parsed_interval:
                        invalid_parsed_intervals[interval] -= 1
                if not duplicate_parsed_interval:
                    findings.append(
                        QAFinding(
                            "error",
                            "invalid_timecode",
                            cue_number,
                            "No se pudo interpretar la línea de timecode del archivo.",
                        )
                    )
                continue

            if not lines[time_line_index + 1 :]:
                findings.append(
                    QAFinding(
                        "warning",
                        "empty_subtitle",
                        cue_number,
                        "El bloque con timecode no contiene texto.",
                    )
                )

    @classmethod
    def _timestamp_components_valid(cls, match, file_format):
        if file_format == "srt":
            groups = match.groups()
            start = tuple(int(value) for value in groups[:3])
            end = tuple(int(value) for value in groups[4:7])
            if start[1] > 59 or start[2] > 59 or end[1] > 59 or end[2] > 59:
                return False
            start_ms = ((start[0] * 60 + start[1]) * 60 + start[2]) * 1000 + int(
                groups[3].ljust(3, "0")
            )
            end_ms = ((end[0] * 60 + end[1]) * 60 + end[2]) * 1000 + int(
                groups[7].ljust(3, "0")
            )
            return end_ms > start_ms
        start_ms = cls._clock_to_ms(match.group(1), match.group(2))
        end_ms = cls._clock_to_ms(match.group(3), match.group(4))
        return start_ms is not None and end_ms is not None and end_ms > start_ms

    @staticmethod
    def _clock_to_ms(clock, fraction):
        parts = [int(part) for part in clock.split(":")]
        if len(parts) == 2:
            minutes, seconds = parts
            hours = 0
        elif len(parts) == 3:
            hours, minutes, seconds = parts
        else:
            return None
        if minutes > 59 or seconds > 59:
            return None
        return ((hours * 60 + minutes) * 60 + seconds) * 1000 + int(
            fraction.ljust(3, "0")
        )

    @classmethod
    def _ass_time_to_ms(cls, value):
        match = cls._ASS_TIME.fullmatch(value)
        if not match:
            return None
        hours, minutes, seconds = (int(part) for part in match.groups()[:3])
        if minutes > 59 or seconds > 59:
            return None
        return ((hours * 60 + minutes) * 60 + seconds) * 1000 + int(
            match.group(4).ljust(2, "0")
        ) * 10

    @classmethod
    def _validate_ass_source(cls, content, findings):
        lowered = content.casefold()
        if "[events]" not in lowered or "[script info]" not in lowered:
            findings.append(
                QAFinding(
                    "error",
                    "invalid_format",
                    None,
                    "El archivo ASS/SSA no contiene las secciones básicas requeridas.",
                )
            )
        dialogue_number = 0
        for line in content.splitlines():
            dialogue_line = line.strip()
            if not dialogue_line.casefold().startswith("dialogue:"):
                continue
            dialogue_number += 1
            if len(dialogue_line.split(",", 9)) != 10:
                findings.append(
                    QAFinding(
                        "error",
                        "invalid_format",
                        dialogue_number,
                        "La línea Dialogue de ASS/SSA no tiene los campos esperados.",
                    )
                )
                continue
            match = re.match(
                r"Dialogue:\s*[^,]+,([^,]+),([^,]+),",
                dialogue_line,
                re.IGNORECASE,
            )
            start = cls._ass_time_to_ms(match.group(1)) if match else None
            end = cls._ass_time_to_ms(match.group(2)) if match else None
            if start is None or end is None or end <= start:
                findings.append(
                    QAFinding(
                        "error",
                        "invalid_timecode",
                        dialogue_number,
                        "La línea Dialogue de ASS/SSA contiene timecodes inválidos.",
                    )
                )
