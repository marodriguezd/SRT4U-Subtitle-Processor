"""Regression tests for the deep source-code audit remediation.

Every test here corresponds to a finding that survived the previous, green
test suite. They are written to fail against the pre-fix implementation.
"""

import os
import re
import sqlite3
from pathlib import Path
import threading
import time

import pytest

from application.services import ass_utils
from application.services.config_service import ConfigService
from application.services.history_store import HistoryStore, SCHEMA_VERSION
from application.services.subtitle_service import (
    ParseIssue,
    SubtitleCancelledError,
    SubtitleItem,
    SubtitleService,
    ms_to_ass_time,
    parse_timestamp_to_ms,
)
from application.services.translation_models import (
    TranslationMetrics,
    TranslationResult,
)
from application.services.translation_service import TranslationService


@pytest.fixture
def service():
    return SubtitleService()


# ---------------------------------------------------------------- H1 cleaner


def _line(service, text):
    items = [SubtitleItem(index=1, start_ms=0, end_ms=1000, text=text)]
    cleaned, _total, removed = service.clean_subtitles(items)
    return removed, cleaned


@pytest.mark.parametrize(
    "line",
    [
        "Subtitled by AnimeFansubPro",
        "Subtitulado por FansubZone",
        "Subtítulos sincronizados por FansubZone - https://t.me/fansub",
        "Traducción de SpanishSubs",
        "Ripped by YTS",
        "Encoded by SubTeam",
        "Downloaded from opensubtitles.org",
        "Descargado de YTS.MX",
        "https://t.me/fansub_official",
        "www.subtitlesfree.org",
        "t.me/tech_news",
        "telegram:@subs",
        "YTS.MX",
        "RARBG",
        "We compress knowledge for you!",
        "♪ Suspenseful dramatic music ♪",
        "♪",
        "[Upbeat music]",
    ],
)
def test_real_spam_is_still_removed(service, line):
    """H1: the default cleaner must keep working, not just stop eating things."""
    removed, cleaned = _line(service, line)
    assert removed == 1, f"spam line should be removed: {line!r}"
    assert cleaned == []


@pytest.mark.parametrize(
    "line",
    [
        # The exact false positives the audit demonstrated.
        "I went to www.city.com yesterday.",
        "The rarbg group released it.",
        "yts.mx was in my history.",
        "I visited https://example.org yesterday.",
        "I downloaded it from opensubtitles yesterday.",
        "The sign said t.me/joinchat for info.",
        "She said 100% of the time.",
        "My email is a@b.com",
        "Look at the mountains in the distance!",
        "The opensubtitles community is unreliable.",
        "We downloaded the report from the server.",
        "He rated the film 9/10 on IMDb.",
    ],
)
def test_legitimate_dialogue_is_never_deleted(service, line):
    """H1: a line that merely *mentions* a site or URL is dialogue, not spam."""
    removed, cleaned = _line(service, line)
    assert removed == 0, f"legitimate dialogue was deleted: {line!r}"
    assert [item.text for item in cleaned] == [line]


def test_promotional_line_with_source_is_removed(service):
    """H1: an imperative call to action that names a source *is* an ad."""
    removed, _ = _line(service, "Join our Telegram group: https://t.me/tech_news")
    assert removed == 1
    removed, _ = _line(service, "Visit us at www.subtitlesfree.org for more.")
    assert removed == 1
    removed, _ = _line(service, "Please visit https://example.org now.")
    assert removed == 1


def test_cleaner_keeps_whole_cue_when_one_line_is_spam(service):
    """H1: removing a spam line must not remove the dialogue beside it."""
    items = [
        SubtitleItem(
            index=1,
            start_ms=0,
            end_ms=2000,
            text="Yes, we found fingerprints.\nSubtitled by Someone",
        )
    ]
    cleaned, _total, removed = service.clean_subtitles(items)
    assert removed == 1
    assert [item.text for item in cleaned] == ["Yes, we found fingerprints."]
    assert cleaned[0].start_ms == 0 and cleaned[0].end_ms == 2000


# ------------------------------------------------------------------ H2 race


class _SelectivelyFailingService(TranslationService):
    """Fails for even cue indices; every call is tagged with its own text."""

    def __init__(self, delay=lambda text: 0.0):
        self._tls = threading.local()
        self._delay = delay
        self.attributed = {}
        self._lock = threading.Lock()

    def translate_text(
        self,
        text,
        target_language,
        source_language="auto",
        engine="google",
        progress_callback=None,
    ):
        if self._delay(text):
            time.sleep(self._delay(text))
        fail = int(text) % 2 == 0
        metrics = TranslationMetrics.for_text(
            provider=engine,
            model=None,
            source_language=source_language,
            target_language=target_language,
            source_text=text,
            translated_text=text,
            duration_ms=0,
            success=not fail,
            error_type="rate_limit" if fail else None,
            requested_provider=engine,
            providers_used=[engine],
        )
        with self._lock:
            self.attributed[text] = metrics
        self._set_result(TranslationResult(text, metrics))
        return text


def _numbered(count):
    return [
        SubtitleItem(index=i + 1, start_ms=i * 1000, end_ms=i * 1000 + 900, text=str(i))
        for i in range(count)
    ]


@pytest.mark.parametrize("parallel", [True, False])
def test_parallel_metrics_are_attributed_to_the_right_cue(parallel):
    """H2: every metric must belong to the cue that produced it."""
    fake = _SelectivelyFailingService()
    svc = SubtitleService(fake)
    svc.max_workers = 8
    out = svc.translate_subtitles(_numbered(60), "es", parallel=parallel)

    assert [item.index for item in out] == list(range(1, 61))
    assert svc.last_translation_failures == 30
    for text, metric in fake.attributed.items():
        expected = int(text) % 2 == 0
        assert metric.success is not expected, (
            f"cue {text}: success flag was mutated by another thread"
        )


def test_parallel_aggregate_is_deterministic_across_runs():
    """H2: the aggregate error type must not depend on thread scheduling."""
    results = set()
    for _ in range(5):
        svc = SubtitleService(_SelectivelyFailingService())
        svc.max_workers = 8
        svc.translate_subtitles(_numbered(40), "es", parallel=True)
        results.add(svc.last_translation_metrics.error_type)
    assert results == {"rate_limit"}


def test_no_shared_list_minus_one_pattern_remains():
    """H2: the structural fix must not reintroduce the racy read."""
    source = open(
        os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "application",
            "services",
            "subtitle_service.py",
        ),
        encoding="utf-8",
    ).read()
    body = source.split("def translate_single_item", 1)[1].split(
        "def format_output", 1
    )[0]
    assert "[-1]" not in body, "translate_single_item must not index a shared list"


def test_translation_preserves_input_order_regardless_of_completion_order():
    """H2: results are rebuilt in cue order, not completion order."""
    # The last cue is by far the slowest, so completion order != input order.
    fake = _SelectivelyFailingService(delay=lambda text: 0.02 if text == "39" else 0.0)
    svc = SubtitleService(fake)
    svc.max_workers = 8
    out = svc.translate_subtitles(_numbered(40), "es", parallel=True)
    assert [item.index for item in out] == list(range(1, 41))
    assert out[-1].start_ms == 39000


# ------------------------------------------------------- H3 cancel contract


def test_cancel_before_translation_starts():
    svc = SubtitleService(_SelectivelyFailingService())
    event = threading.Event()
    event.set()
    with pytest.raises(SubtitleCancelledError):
        svc.translate_subtitles(_numbered(10), "es", cancel_event=event)


def test_cancel_during_sequential_translation():
    fake = _SelectivelyFailingService(delay=lambda text: 0.005)
    svc = SubtitleService(fake)
    event = threading.Event()

    def progress(_step, payload):
        completed, _total = payload
        if completed == 2:
            event.set()

    with pytest.raises(SubtitleCancelledError):
        svc.translate_subtitles(
            _numbered(40),
            "es",
            parallel=False,
            progress_callback=progress,
            cancel_event=event,
        )
    # No partial state is published for the next job to pick up.
    assert svc.last_translation_metrics is None
    assert svc.last_translation_failures == 0


def test_cancel_with_parallel_true_exits_pool_and_leaves_no_state():
    fake = _SelectivelyFailingService(delay=lambda text: 0.002)
    svc = SubtitleService(fake)
    svc.max_workers = 4
    event = threading.Event()

    def progress(_step, payload):
        completed, _total = payload
        if completed == 3:
            event.set()

    with pytest.raises(SubtitleCancelledError):
        svc.translate_subtitles(
            _numbered(60),
            "es",
            parallel=True,
            progress_callback=progress,
            cancel_event=event,
        )
    assert svc.last_translation_metrics is None
    # The pool shut down cleanly: no worker thread survives the call.
    before = threading.active_count()
    svc.translate_subtitles(_numbered(2), "es", parallel=True)
    assert threading.active_count() <= before


def test_process_subtitles_forwards_cancellation(tmp_path):
    source = tmp_path / "in.srt"
    source.write_text("1\n00:00:01,000 --> 00:00:02,000\nHello\n", encoding="utf-8")
    svc = SubtitleService(_SelectivelyFailingService())
    event = threading.Event()
    event.set()
    with pytest.raises(SubtitleCancelledError):
        svc.process_subtitles(
            str(source),
            do_translate=True,
            target_language="es",
            engine="google",
            parallel=False,
            cancel_event=event,
        )


# ------------------------------------------------------------------- H4 save


def test_config_save_is_valid_json_and_0600(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    cfg = ConfigService()
    cfg.config["openai_api_key"] = "sk-" + "A" * 300
    assert cfg.save() is True
    assert cfg.save_error is None

    import json

    with open(cfg.config_file, encoding="utf-8") as handle:
        assert json.load(handle)["openai_api_key"] == "sk-" + "A" * 300

    if os.name != "nt":
        assert os.stat(cfg.config_file).st_mode & 0o777 == 0o600
        assert os.stat(cfg.config_dir).st_mode & 0o777 == 0o700


def test_config_save_failure_preserves_previous_file(tmp_path, monkeypatch):
    """H4: a failure before the rename must leave the old config intact."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    cfg = ConfigService()
    cfg.config["openai_api_key"] = "original-key"
    assert cfg.save() is True
    with open(cfg.config_file, encoding="utf-8") as handle:
        before = handle.read()

    import os as _os

    from application.services import atomic_write as atomic_module

    def boom(*args, **kwargs):
        raise OSError("simulated failure before replace")

    monkeypatch.setattr(atomic_module.os, "replace", boom)
    cfg.config["openai_api_key"] = "new-key"
    assert cfg.save() is False
    assert cfg.save_error == "OSError"
    with open(cfg.config_file, encoding="utf-8") as handle:
        assert handle.read() == before, "previous settings must survive a failed save"
    leftovers = [
        name for name in os.listdir(cfg.config_dir) if name.startswith(".srt4u-tmp-")
    ]
    assert leftovers == [], "a failed save must not leave a temp file behind"
    assert _os.path.exists(cfg.config_file)


def test_config_save_leaves_no_orphan_temp_file(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    cfg = ConfigService()
    assert cfg.save() is True
    leftovers = [
        name
        for name in os.listdir(cfg.config_dir)
        if name.startswith(".srt4u-tmp-") or name.endswith(".tmp")
    ]
    assert leftovers == []


def test_corrupt_config_recovers_to_defaults_and_reports(tmp_path, monkeypatch):
    """H4: an unparsable file is reported, not silently accepted."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    cfg = ConfigService()
    with open(cfg.config_file, "w", encoding="utf-8") as handle:
        handle.write('{"deepl_api_key": "secret", "trunc')
    fresh = ConfigService()
    fresh.config_file = cfg.config_file
    fresh.config = dict(ConfigService.DEFAULT_CONFIG)
    fresh.load()
    assert fresh.load_error is not None
    assert fresh.get("deepl_api_key") == ""


# ---------------------------------------------------------- M1/M2 ASS output


def _ass_dialogues(document):
    return [
        line.split(",", 9)[9]
        for line in document.splitlines()
        if line.startswith("Dialogue:")
    ]


def _ass_styles(document):
    return {
        line.split(",", 1)[0].split(":", 1)[1].strip()
        for line in document.splitlines()
        if line.startswith("Style:")
    }


def test_ass_export_and_burnin_render_the_same_text():
    """M1: exporter and burn-in must share one rendering contract."""
    from application.services.video_burner_service import (
        BurnInOptions,
        VideoBurnerService,
    )

    items = [
        SubtitleItem(index=1, start_ms=0, end_ms=2000, text="Hello {\\i1}world 50% {"),
        SubtitleItem(
            index=2, start_ms=2000, end_ms=4000, text="<i>Hi</i> and <b>there</b>"
        ),
        SubtitleItem(index=3, start_ms=4000, end_ms=6000, text="two\nlines"),
    ]
    exported = svc_export(items)
    burned = VideoBurnerService.generate_ass_script(items, BurnInOptions())
    assert _ass_dialogues(exported) == _ass_dialogues(burned)
    # User braces are literal, our own tags are real.
    assert _ass_dialogues(exported)[0] == r"Hello \{\i1\}world 50% \{"
    assert _ass_dialogues(exported)[1] == r"{\i1}Hi{\i0} and {\b1}there{\b0}"
    assert _ass_dialogues(exported)[2] == r"two\Nlines"


def svc_export(items):
    return SubtitleService().format_output(items, "ass")


def test_ass_export_never_emits_an_undefined_style():
    """M2: every referenced style must be declared in the header."""
    service = SubtitleService()
    document = (
        "[Script Info]\nTitle: t\nScriptType: v4.00+\n\n[V4+ Styles]\n"
        "Format: " + ass_utils.STYLE_FORMAT + "\n"
        "Style: Top,Arial,40,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,-1,0,0,0,"
        "100,100,0,0,1,3,3,8,10,10,60,1\n"
        "Style: Bottom,Arial,36,&H0000FFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,"
        "100,100,0,0,3,10,0,2,10,10,40,1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:01.00,0:00:02.00,Top,,0,0,0,,top styled\n"
        "Dialogue: 0,0:00:03.00,0:00:04.00,Bottom,,0,0,0,,bottom styled\n"
        "dialogue: 0,0:00:05.00,0:00:06.00,Default,,0,0,0,,lowercase header\n"
    )
    items = service.parse_subtitles(document, "ass")
    assert [item.style for item in items] == ["Top", "Bottom", "Default"]

    exported = service.format_output(items, "ass")
    declared = _ass_styles(exported)
    referenced = {
        line.split(",")[3]
        for line in exported.splitlines()
        if line.startswith("Dialogue:")
    }
    assert referenced <= declared, (
        f"undefined styles referenced: {referenced - declared}"
    )


def test_ass_round_trip_preserves_real_style_definitions():
    """M2: a re-export keeps the source font/size, not just the name."""
    service = SubtitleService()
    document = (
        "[Script Info]\nTitle: t\nScriptType: v4.00+\n\n[V4+ Styles]\n"
        "Format: " + ass_utils.STYLE_FORMAT + "\n"
        "Style: Top,Arial,42,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,0,-1,0,0,"
        "100,100,0,0,1,2,2,8,20,20,20,1\n\n[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:01.00,0:00:02.00,Top,,0,0,0,,top\n"
    )
    items = service.parse_subtitles(document, "ass")
    exported = service.format_output(items, "ass")
    assert "Style: Top,Arial,42," in exported
    assert ",8,20,20,20,1" in exported  # the real alignment/margins survived


# ------------------------------------------------------- M3/M7 parse issues


def test_invalid_timestamp_raises_instead_of_returning_zero():
    """L4: garbage must never silently become "starts at 0"."""
    for bad in ("abc", "", "00:00:01,1234", "1:2:3:4", "00:75:00", "00:00:75"):
        with pytest.raises(ValueError):
            parse_timestamp_to_ms(bad)


def test_valid_timestamps_still_parse():
    assert parse_timestamp_to_ms("00:00:01,1") == 1100
    assert parse_timestamp_to_ms("00:00:01,12") == 1120
    assert parse_timestamp_to_ms("00:01.5") == 1500


def test_srt_keeps_cues_with_internal_blank_lines():
    """M7: the old blank-line splitter truncated the cue and dropped the rest."""
    service = SubtitleService()
    raw = "1\n00:00:01,000 --> 00:00:02,000\nline one\n\nline two\n"
    items = service.parse_subtitles(raw, "srt")
    assert len(items) == 1
    assert items[0].text == "line one\n\nline two"


def test_srt_supports_more_than_99_hours_and_round_trips():
    """L5: the exporter must not write what its own parser cannot read."""
    service = SubtitleService()
    raw = "1\n99:59:59,000 --> 100:00:01,000\nvery long media\n"
    items = service.parse_subtitles(raw, "srt")
    assert len(items) == 1
    assert items[0].start_ms == 99 * 3600000 + 59 * 60000 + 59000
    again = service.parse_subtitles(service.format_output(items, "srt"), "srt")
    assert [(i.start_ms, i.end_ms) for i in again] == [
        (i.start_ms, i.end_ms) for i in items
    ]


def test_dropped_blocks_are_reported_not_silent():
    """M7: unusable blocks are counted and surfaced to the caller."""
    service = SubtitleService()
    raw = (
        "1\n00:00:01,000 --> 00:00:02,000\ngood\n\n"
        "2\n00:75:00,000 --> 00:75:01,000\nbad minutes\n\n"
        "3\n00:00:05,000 --> 00:00:04,000\nreversed\n"
    )
    items = service.parse_subtitles(raw, "srt")
    assert [item.text for item in items] == ["good"]
    kinds = {issue.kind for issue in service.last_parse_issues}
    assert "invalid_timestamp" in kinds
    assert "reversed_timing" in kinds
    assert len(service.last_parse_issues) == 2
    assert all(isinstance(i, ParseIssue) for i in service.last_parse_issues)


def test_negative_ass_times_never_reach_the_output():
    """M3: a negative time used to serialize as -1:59:55,000."""
    service = SubtitleService()
    raw = (
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, "
        "MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:-5.00,0:00:02.00,Default,,0,0,0,,negative start\n"
        "Dialogue: 0,0:00:01.00,0:00:05.00,Default,,0,0,0,,fine\n"
    )
    items = service.parse_subtitles(raw, "ass")
    assert [item.text for item in items] == ["fine"]
    assert any(i.kind == "invalid_timestamp" for i in service.last_parse_issues)
    for line in service.format_output(items, "srt").splitlines():
        assert "-1:59" not in line


def test_malformed_ass_dialogue_is_reported():
    """M7: a Dialogue line with missing fields used to vanish silently."""
    service = SubtitleService()
    raw = (
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, "
        "MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0\n"
        "Dialogue: 0,0:00:03.00,0:00:04.00,Default,,0,0,0,,ok\n"
    )
    items = service.parse_subtitles(raw, "ass")
    assert [item.text for item in items] == ["ok"]
    assert [i.kind for i in service.last_parse_issues] == ["malformed_dialogue"]


def test_lowercase_ass_dialogue_is_parsed():
    """M7: the guard was case-sensitive while the regex claimed IGNORECASE."""
    service = SubtitleService()
    raw = (
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, "
        "MarginV, Effect, Text\n"
        "dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,lowercase\n"
    )
    assert [item.text for item in service.parse_subtitles(raw, "ass")] == ["lowercase"]


def test_process_subtitles_surfaces_parse_issues(tmp_path):
    source = tmp_path / "in.srt"
    source.write_text(
        "1\n00:00:01,000 --> 00:00:02,000\ngood\n\n"
        "2\n00:75:00,000 --> 00:75:01,000\nbad\n",
        encoding="utf-8",
    )
    result = SubtitleService().process_subtitles(str(source))
    assert result.stats.parse_issues == 1
    assert result.parse_issues


# ------------------------------------------------------------------- M8 time


@pytest.mark.parametrize(
    "ms,expected",
    [
        (0, "0:00:00.00"),
        (4, "0:00:00.00"),
        (5, "0:00:00.01"),  # 0.5 cs rounds up
        (9, "0:00:00.01"),
        (10, "0:00:00.01"),
        (994, "0:00:00.99"),
        (995, "0:00:01.00"),  # carries into the next second
        (999, "0:00:01.00"),
        (1499, "0:00:01.50"),
        (59999, "0:01:00.00"),  # carries into the next minute
        (3599999, "1:00:00.00"),  # 59:59.999 rounds into the next minute
        (3600000, "1:00:00.00"),
    ],
)
def test_ass_time_rounds_and_carries(ms, expected):
    """M8: floor shifted every cue up to 9 ms early; rounding must carry."""
    assert ms_to_ass_time(ms) == expected
    assert ass_utils.ass_time(ms) == expected


def test_ass_time_never_goes_backwards_in_the_wrong_direction():
    for ms in range(0, 5000, 7):
        a = ass_utils.ass_time(ms)
        b = ass_utils.ass_time(ms + 1)
        assert a <= b


# -------------------------------------------------------------- M9 retention


def test_job_manager_prunes_completed_jobs():
    from application.api.jobs import JobManager

    manager = JobManager(max_workers=4, max_jobs=25)
    try:
        for _ in range(500):
            manager.submit("t", lambda: {"payload": "x" * 512})
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and len(manager._jobs) > 25:
            time.sleep(0.05)
        assert len(manager._jobs) <= 25
        assert all(job["status"] == "completed" for job in manager._jobs.values())
    finally:
        manager.shutdown()


def test_job_manager_never_prunes_queued_or_running_jobs():
    from application.api.jobs import JobManager

    release = threading.Event()
    manager = JobManager(max_workers=1, max_jobs=5)
    try:
        running = manager.submit("t", lambda: release.wait(5) or "done")
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if manager.get(running)["status"] == "running":
                break
            time.sleep(0.01)
        queued = [manager.submit("t", lambda: "never") for _ in range(20)]
        assert manager.get(running)["status"] == "running"
        for job_id in queued:
            assert manager.get(job_id) is not None, "queued jobs must never be evicted"
        release.set()
    finally:
        manager.shutdown()


def test_job_manager_ttl_expires_old_finished_jobs():
    from application.api.jobs import JobManager

    manager = JobManager(max_workers=1, max_jobs=1000, ttl_seconds=0.05)
    try:
        job_id = manager.submit("t", lambda: "ok")
        assert manager.wait_for(job_id, timeout=5)["status"] == "completed"
        time.sleep(0.4)
        manager._prune_locked()
        assert manager.get(job_id) is None
    finally:
        manager.shutdown()


# ---------------------------------------------------------------- L1 history


def test_run_and_findings_are_written_in_one_transaction(tmp_path):
    """L1: a failure while storing findings must roll the run row back."""
    path = str(tmp_path / "h.db")
    store = HistoryStore(path)
    try:

        class Boom(Exception):
            pass

        def boom(*args, **kwargs):
            raise Boom("findings storage failed")

        store._insert_qa_findings = boom  # type: ignore[method-assign]
        with pytest.raises(Boom):
            store.record_processing_result(
                _ProcessingDouble(), operation="process", file_path="a.srt"
            )
    finally:
        store.close()
    assert sqlite3.connect(path).execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0

    conn = sqlite3.connect(path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0
    finally:
        conn.close()


class _QAReportDouble:
    findings = [
        type(
            "F",
            (),
            {
                "severity": "error",
                "rule": "r",
                "subtitle_index": 1,
                "message": "m",
                "metadata": None,
            },
        )()
    ]
    error_count = 1
    warning_count = 0


class _ProcessingDouble:
    stats = type("S", (), {"translation_failures": 0})()
    qa_report = _QAReportDouble()
    translation_metrics = None
    success = True


# ----------------------------------------------------------------- L2 success


@pytest.mark.parametrize(
    "kwargs,expected",
    [
        ({"success": True}, 1),
        ({"success": False}, 0),
    ],
)
def test_processing_success_is_explicit(tmp_path, kwargs, expected):
    path = str(tmp_path / f"h{expected}.db")
    with HistoryStore(path) as store:
        run_id = store.record_processing_result(
            _ProcessingDouble(), operation="process", file_path="a.srt", **kwargs
        )
    conn = sqlite3.connect(path)
    try:
        stored = conn.execute(
            "SELECT success FROM runs WHERE id=?", (run_id,)
        ).fetchone()
        assert stored[0] == expected
    finally:
        conn.close()


def test_pipeline_and_process_agree_on_success_semantics(tmp_path):
    """L2: a ProcessingResult without metrics is no longer silently 'ok'."""
    from application.services.media_pipeline import (
        PipelineResult,
        record_pipeline_result,
    )

    db = str(tmp_path / "shared.db")
    failed = _ProcessingDouble()
    failed.success = False
    with HistoryStore(db) as store:
        store.record_processing_result(failed, operation="process", file_path="a.srt")
        record_pipeline_result(
            PipelineResult(
                success=False,
                errors=[{"stage": "qa", "error_type": "x", "message": "m"}],
            ),
            _PipelineConfigDouble(),
            db,
        )
    conn = sqlite3.connect(db)
    try:
        rows = dict(conn.execute("SELECT operation, success FROM runs").fetchall())
    finally:
        conn.close()
    assert rows == {"process": 0, "pipeline": 0}


class _PipelineConfigDouble:
    input_media = "media.mp4"
    output_format = "srt"
    source_language = "auto"
    target_language = None
    provider = "google"
    translation_enabled = False


# ----------------------------------------------------------------- L11 migrate


def test_migration_from_v1_to_v2(tmp_path):
    path = str(tmp_path / "m.db")
    conn = sqlite3.connect(path)
    conn.executescript(
        "CREATE TABLE runs (id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "timestamp TEXT NOT NULL, operation TEXT NOT NULL, success INTEGER "
        "NOT NULL DEFAULT 1); PRAGMA user_version = 1;"
    )
    conn.commit()
    conn.close()
    with HistoryStore(path) as store:
        assert store._version() == SCHEMA_VERSION
    conn = sqlite3.connect(path)
    try:
        columns = [r[1] for r in conn.execute("PRAGMA table_info(runs)")]
    finally:
        conn.close()
    assert "media_duration_ms" in columns
    # P1: v3 carries the parse-issue counter for pipeline/process rows.
    assert "parse_issues" in columns


def test_failed_migration_leaves_version_and_schema_consistent(tmp_path, monkeypatch):
    """L11: a mid-migration failure must not desync DDL from user_version."""
    from application.services import history_store as hs

    path = str(tmp_path / "bad.db")
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA user_version = 0")
    conn.commit()
    conn.close()

    original = hs._MIGRATIONS[1]
    hs._MIGRATIONS[1] = "CREATE TABLE runs (id INTEGER PRIMARY KEY); THIS IS NOT SQL;"
    try:
        with pytest.raises(hs.HistoryError):
            HistoryStore(path)
    finally:
        hs._MIGRATIONS[1] = original

    conn = sqlite3.connect(path)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 0
        tables = {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert "runs" not in tables, "partial DDL must have been rolled back"
    finally:
        conn.close()


# ---------------------------------------------------------------- L6 whisper


def test_whisper_models_have_a_single_source_of_truth(tmp_path):
    """L6: the pipeline must validate against the same catalogue as the API."""
    from application.services.media_pipeline import PipelineConfig, PipelineConfigError
    from application.services.transcription_whisper import WHISPER_MODELS

    media = tmp_path / "clip.mp4"
    media.write_bytes(b"not really a video")
    source = str(media)

    with pytest.raises(PipelineConfigError):
        PipelineConfig(input_media=source, transcription_model="not-a-model").validate()
    for model in WHISPER_MODELS:
        config = PipelineConfig(
            input_media=source, transcription_model=model
        ).validate()
        assert config.transcription_model == model


def test_pipeline_model_catalogue_matches_the_api_catalogue():
    """L6: no second, hard-coded list of Whisper models may exist."""
    from application.services.transcription_whisper import WHISPER_MODELS

    source = open(
        os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "application",
            "services",
            "media_pipeline.py",
        ),
        encoding="utf-8",
    ).read()
    # The catalogue must be referenced, never re-listed as a literal set.
    assert "WHISPER_MODELS" in source
    assert not re.search(r"\{[^{}]*\"tiny\"[^{}]*\}", source), (
        "media_pipeline must not re-declare the Whisper model list"
    )
    for model in WHISPER_MODELS:
        occurrences = len(re.findall(rf'"{model}"', source))
        assert occurrences <= 1, (
            f"{model} appears {occurrences} times in media_pipeline"
        )


def test_strict_qa_requires_qa_enabled(tmp_path):
    """L8: strict QA with QA disabled looked like a gate but was a no-op."""
    from application.services.media_pipeline import PipelineConfig, PipelineConfigError

    source = tmp_path / "in.srt"
    source.write_text("1\n00:00:01,000 --> 00:00:02,000\nHi\n", encoding="utf-8")
    with pytest.raises(PipelineConfigError):
        PipelineConfig(
            input_media=str(source), qa_enabled=False, qa_strict=True
        ).validate()


# -------------------------------------------------------------------- L9 i/o


def test_pipeline_export_does_not_destroy_existing_output(tmp_path, monkeypatch):
    from application.services.media_pipeline import MediaPipeline, PipelineConfig

    source = tmp_path / "in.srt"
    source.write_text("1\n00:00:01,000 --> 00:00:02,000\nHi\n", encoding="utf-8")
    out = tmp_path / "out.srt"
    out.write_text("PREVIOUS GOOD CONTENT", encoding="utf-8")

    import application.services.atomic_write as atomic_module

    def boom(*args, **kwargs):
        raise OSError("simulated write failure")

    monkeypatch.setattr(atomic_module.os, "replace", boom)
    result = MediaPipeline().run(
        PipelineConfig(
            input_media=str(source),
            output_subtitle=str(out),
            clean_enabled=False,
            qa_enabled=False,
        ).validate()
    )
    assert result.success is False
    assert result.failed_stage == "export"
    assert out.read_text(encoding="utf-8") == "PREVIOUS GOOD CONTENT"


def test_write_output_file_is_atomic(tmp_path, monkeypatch):
    from application.services.atomic_write import atomic_write_text

    target = tmp_path / "out.srt"
    atomic_write_text(str(target), "first")
    assert target.read_text(encoding="utf-8") == "first"

    import application.services.atomic_write as module

    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(module.os, "replace", boom)
    with pytest.raises(OSError):
        atomic_write_text(str(target), "second")
    assert target.read_text(encoding="utf-8") == "first"
    assert not [p for p in tmp_path.iterdir() if p.name.startswith(".srt4u-tmp-")]


def _write_srt(path, content):
    Path(path).write_text(content, encoding="utf-8")
    return str(path)
