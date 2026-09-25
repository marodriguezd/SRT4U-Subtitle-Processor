# application/services/subtitle_service.py
import re
import os
import time
import concurrent.futures
from dataclasses import dataclass, field
from typing import Optional, Callable, List, Tuple
from .translation_service import TranslationService


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
    hours = ms // 3600000
    ms %= 3600000
    minutes = ms // 60000
    ms %= 60000
    seconds = ms // 1000
    centiseconds = (ms % 1000) // 10
    return f"{hours:01d}:{minutes:02d}:{seconds:02d}.{centiseconds:02d}"


def parse_timestamp_to_ms(time_str: str) -> int:
    time_str = time_str.strip().replace(",", ".")
    parts = time_str.split(":")
    if len(parts) == 3:
        h = int(parts[0])
        m = int(parts[1])
        s_parts = parts[2].split(".")
        s = int(s_parts[0])
        ms = int(s_parts[1].ljust(3, "0")[:3]) if len(s_parts) > 1 else 0
        return (h * 3600 + m * 60 + s) * 1000 + ms
    elif len(parts) == 2:
        m = int(parts[0])
        s_parts = parts[1].split(".")
        s = int(s_parts[0])
        ms = int(s_parts[1].ljust(3, "0")[:3]) if len(s_parts) > 1 else 0
        return (m * 60 + s) * 1000 + ms
    return 0


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


@dataclass
class ProcessingResult:
    stats: ProcessingStats
    original_items: List[SubtitleItem] = field(default_factory=list)
    processed_items: List[SubtitleItem] = field(default_factory=list)
    output_content: str = ""


class SubtitleService:
    """
    Motor de procesamiento de subtítulos para SRT, VTT, ASS y TXT.
    """

    DEFAULT_SPAM_PATTERNS = [
        r"(?i)subtitled?\s*by\b.*",
        r"(?i)subt[ií]tulos\s*por\b.*",
        r"(?i)traducci[oó]n\s*(?:de|por)\b.*",
        r"(?i)ripped\s*by\b.*",
        r"(?i)sincronizad[oa]\s*por\b.*",
        r"(?i)downloaded\s*from\b.*",
        r"(?i)descargad[oa]\s*de\b.*",
        r"(?i)https?://[^\s]+",
        r"(?i)www\.[a-z0-9\-\.]+\.[a-z]{2,}",
        r"(?i)t\.me/[a-zA-Z0-9_\-]+",
        r"(?i)joinchat/[a-zA-Z0-9_\-]+",
        r"(?i)telegram:?\s*@[a-zA-Z0-9_]+",
        r"[-~]?♪.*?♪[-~]?",
        r"♪+",
        r"♫+",
        r"(?i)we\s*compress\s*knowledge\s*for\s*you!?",
        r"(?i)\b(?:yts|rarbg|yify|opensubtitles|addic7ed|subscene)\b.*",
        r"(?i)<font[^>]*>.*?</font>",
    ]

    def __init__(self, translation_service: Optional[TranslationService] = None, batch_size: int = 50):
        self.translation_service = translation_service or TranslationService()
        self.batch_size = batch_size
        self.spam_patterns = [re.compile(p) for p in self.DEFAULT_SPAM_PATTERNS]
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

    def parse_subtitles(self, content: str, file_format: str = "srt") -> List[SubtitleItem]:
        format_lower = file_format.lower()
        if format_lower == "vtt":
            return self._parse_vtt(content)
        elif format_lower in ["ass", "ssa"]:
            return self._parse_ass(content)
        elif format_lower == "txt":
            return self._parse_txt(content)
        return self._parse_srt(content)

    def _parse_srt(self, content: str) -> List[SubtitleItem]:
        items: List[SubtitleItem] = []
        raw_blocks = re.split(r"\r?\n\s*\r?\n", content.strip())
        ts_regex = re.compile(
            r"(\d{1,2}:\d{2}:\d{2}[,\.]\d{1,3})\s*-->\s*(\d{1,2}:\d{2}:\d{2}[,\.]\d{1,3})"
        )

        curr_idx = 1
        for block in raw_blocks:
            lines = [l.strip() for l in block.splitlines() if l.strip()]
            if not lines:
                continue

            time_line_idx = -1
            match = None
            for idx, line in enumerate(lines[:3]):
                match = ts_regex.search(line)
                if match:
                    time_line_idx = idx
                    break

            if match and time_line_idx >= 0:
                start_ms = parse_timestamp_to_ms(match.group(1))
                end_ms = parse_timestamp_to_ms(match.group(2))
                text = "\n".join(lines[time_line_idx + 1:])
                if text.strip():
                    items.append(SubtitleItem(
                        index=curr_idx,
                        start_ms=start_ms,
                        end_ms=end_ms,
                        text=text
                    ))
                    curr_idx += 1
        return items

    def _parse_vtt(self, content: str) -> List[SubtitleItem]:
        lines = content.splitlines()
        items: List[SubtitleItem] = []
        ts_regex = re.compile(
            r"((?:\d{1,2}:)?\d{2}:\d{2}[\.]\d{1,3})\s*-->\s*((?:\d{1,2}:)?\d{2}:\d{2}[\.]\d{1,3})"
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
                start_ms = parse_timestamp_to_ms(match.group(1))
                end_ms = parse_timestamp_to_ms(match.group(2))
                time_line_full = line
                after_match = time_line_full[match.end():].strip()
                if after_match:
                    extra = after_match

                text_lines = []
                i += 1
                while i < len(lines) and lines[i].strip():
                    text_lines.append(lines[i].strip())
                    i += 1

                text = "\n".join(text_lines)
                if text.strip():
                    items.append(SubtitleItem(
                        index=curr_idx,
                        start_ms=start_ms,
                        end_ms=end_ms,
                        text=text,
                        extra=extra
                    ))
                    curr_idx += 1
            else:
                i += 1
        return items

    def _parse_ass(self, content: str) -> List[SubtitleItem]:
        items: List[SubtitleItem] = []
        dialogue_regex = re.compile(
            r"^Dialogue:\s*[^,]+,([^,]+),([^,]+),([^,]*),([^,]*),([^,]*),([^,]*),([^,]*),([^,]*),(.*)$",
            re.IGNORECASE
        )
        curr_idx = 1
        for line in content.splitlines():
            line_str = line.strip()
            if not line_str.startswith("Dialogue:"):
                continue

            match = dialogue_regex.match(line_str)
            if match:
                start_str, end_str, style = match.group(1), match.group(2), match.group(3)
                raw_text = match.group(9)
                start_ms = parse_timestamp_to_ms(start_str)
                end_ms = parse_timestamp_to_ms(end_str)
                text = raw_text.replace(r"\N", "\n").replace(r"\n", "\n")
                items.append(SubtitleItem(
                    index=curr_idx,
                    start_ms=start_ms,
                    end_ms=end_ms,
                    text=text,
                    style=style
                ))
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
            items.append(SubtitleItem(
                index=curr_idx,
                start_ms=curr_ms,
                end_ms=curr_ms + duration,
                text=text
            ))
            curr_ms += duration + 500
            curr_idx += 1
        return items

    def clean_subtitles(self, items: List[SubtitleItem]) -> Tuple[List[SubtitleItem], int, int]:
        cleaned_items: List[SubtitleItem] = []
        total_lines = 0
        deleted_lines = 0

        for item in items:
            lines = item.text.split("\n")
            kept_lines = []
            for line in lines:
                total_lines += 1
                is_spam = False
                for pattern in self.spam_patterns:
                    if pattern.search(line):
                        is_spam = True
                        deleted_lines += 1
                        break
                if not is_spam and line.strip():
                    kept_lines.append(line.strip())

            if kept_lines:
                item_cleaned = SubtitleItem(
                    index=len(cleaned_items) + 1,
                    start_ms=item.start_ms,
                    end_ms=item.end_ms,
                    text="\n".join(kept_lines),
                    style=item.style,
                    extra=item.extra
                )
                cleaned_items.append(item_cleaned)

        return cleaned_items, total_lines, deleted_lines

    def translate_subtitles(
        self,
        items: List[SubtitleItem],
        target_language: str,
        source_language: str = "auto",
        engine: str = "google",
        parallel: bool = True,
        progress_callback: Optional[Callable[[str, object], None]] = None,
    ) -> List[SubtitleItem]:
        total_items = len(items)
        if total_items == 0:
            return []

        results: List[Optional[SubtitleItem]] = [None] * total_items

        def translate_single_item(idx: int, item: SubtitleItem) -> Tuple[int, SubtitleItem]:
            original_text = item.text.strip()
            if not original_text:
                return idx, item

            try:
                translated_text = self.translation_service.translate_text(
                    text=original_text,
                    target_language=target_language,
                    source_language=source_language,
                    engine=engine
                )
                new_item = SubtitleItem(
                    index=item.index,
                    start_ms=item.start_ms,
                    end_ms=item.end_ms,
                    text=translated_text,
                    style=item.style,
                    extra=item.extra
                )
                return idx, new_item
            except Exception:
                return idx, item

        completed = 0
        if parallel:
            with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                future_to_idx = {
                    executor.submit(translate_single_item, i, item): i
                    for i, item in enumerate(items)
                }

                for future in concurrent.futures.as_completed(future_to_idx):
                    idx, res_item = future.result()
                    results[idx] = res_item
                    completed += 1
                    if progress_callback:
                        progress_callback("step_translating", (completed, total_items))
        else:
            for i, item in enumerate(items):
                idx, res_item = translate_single_item(i, item)
                results[idx] = res_item
                completed += 1
                if progress_callback:
                    progress_callback("step_translating", (completed, total_items))

        return [it for it in results if it is not None]

    def format_output(self, items: List[SubtitleItem], target_format: str = "srt") -> str:
        fmt = target_format.lower().lstrip(".")
        if fmt == "vtt":
            return self._format_vtt(items)
        elif fmt in ["ass", "ssa"]:
            return self._format_ass(items)
        elif fmt == "txt":
            return self._format_txt(items)
        return self._format_srt(items)

    def _format_srt(self, items: List[SubtitleItem]) -> str:
        blocks = []
        for idx, item in enumerate(items, 1):
            blocks.append(f"{idx}\n{item.get_srt_time()}\n{item.text}\n")
        return "\n".join(blocks).strip() + "\n"

    def _format_vtt(self, items: List[SubtitleItem]) -> str:
        lines = ["WEBVTT\n"]
        for idx, item in enumerate(items, 1):
            cue_line = item.get_vtt_time()
            if item.extra:
                cue_line += f" {item.extra}"
            lines.append(f"{idx}\n{cue_line}\n{item.text}\n")
        return "\n".join(lines).strip() + "\n"

    def _format_ass(self, items: List[SubtitleItem]) -> str:
        header = """[Script Info]
Title: SRT4U Exported Subtitles
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.601

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,2,2,10,10,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        events = []
        for item in items:
            ass_text = item.text.replace("\n", r"\N")
            start = item.get_ass_start()
            end = item.get_ass_end()
            style = item.style or "Default"
            events.append(f"Dialogue: 0,{start},{end},{style},,0,0,0,,{ass_text}")
        return header + "\n".join(events) + "\n"

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
        total_original_lines = sum(len(it.text.split("\n")) for it in original_items)
        current_items = list(original_items)
        deleted_lines_count = 0

        # Paso 3: Limpieza
        if do_clean:
            if progress_callback:
                progress_callback("step_cleaning", True)
            current_items, tot_lines, deleted_lines_count = self.clean_subtitles(current_items)
            total_original_lines = tot_lines

        # Paso 4: Traducción
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
            )

        # Paso 5: Aplicar formato original
        if progress_callback:
            progress_callback("step_formatting", True)

        output_content = self.format_output(current_items, out_format)

        # Paso 6: Guardado
        if progress_callback:
            progress_callback("step_saving", True)

        elapsed = time.time() - start_time
        stats = ProcessingStats(
            total_lines=total_original_lines,
            deleted_lines=deleted_lines_count,
            processed_items_count=len(current_items),
            elapsed_time=round(elapsed, 2)
        )

        return ProcessingResult(
            stats=stats,
            original_items=original_items,
            processed_items=current_items,
            output_content=output_content
        )
