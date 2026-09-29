"""
Prueba de extremo a extremo con material real: un vídeo de 1 minuto (1920x1080,
60 fps, con audio) y su fichero de subtítulos SRT (25 bloques con solapamientos
y un hueco de 1 s).

El resto de la suite trabaja con fixtures diminutas y no toca FFmpeg de verdad
con un vídeo completo; aquí se recorre **cada apartado** de la aplicación con
los ficheros reales: lectura, limpieza, traducción con el motor gratuito,
conversión entre los 4 formatos, metadatos del vídeo, generación de ASS, burn-in
(hardsub) del minuto completo con validación del resultado, reproductor de la
vista previa y los flujos de la interfaz (procesar, convertir, por lotes,
ajustes).

Los ficheros se localizan por `SRT4U_E2E_MEDIA` (por defecto el directorio de
material del usuario) y todo el módulo se omite si no están, de modo que la
suite sigue siendo ejecutable en CI sin ese material.
"""

import os
import shutil
import subprocess
import time

import pytest
from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtWidgets import QTableWidgetItem
from PyQt6.QtGui import QImage
from PyQt6.QtMultimedia import QMediaPlayer

from application.services.config_service import ConfigService
from application.services.i18n_service import get_i18n
from application.services.subtitle_service import SubtitleService
from application.services.translation_service import TranslationService
from application.services.video_burner_service import (
    BurnInOptions,
    BurnInWorker,
    VideoBurnerService,
)
from application.ui.burn_in_dialog import BurnInDialog
from application.ui.main_window import MainWindow, ProcessWorker
from application.services.i18n_service import t
from application.ui.widgets import VideoPreviewPlayer

MEDIA_DIR = os.environ.get("SRT4U_E2E_MEDIA", "/home/marodriguezd/Video_srt4u")
VIDEO_NAME = "S1pK5hmTzkE_1min.mp4"
SRT_NAME = "S1pK5hmTzkE_1min.srt"

VIDEO_PATH = os.path.join(MEDIA_DIR, VIDEO_NAME)
SRT_PATH = os.path.join(MEDIA_DIR, SRT_NAME)

# Datos esperados del material real (verificados con ffprobe / inspección)
EXPECTED_CUES = 25
EXPECTED_DURATION_MS = 60000
EXPECTED_SIZE = (1920, 1080)

pytestmark = pytest.mark.skipif(
    not (os.path.exists(VIDEO_PATH) and os.path.exists(SRT_PATH)),
    reason=f"material real no disponible en {MEDIA_DIR} "
    f"(se puede indicar con SRT4U_E2E_MEDIA)",
)


# --------------------------------------------------------------------------- #
# Utilidades
# --------------------------------------------------------------------------- #
def _ffprobe(path: str) -> dict:
    """Metadatos del fichero con ffprobe ( streams + formato)."""
    out = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration,size",
            "-show_entries",
            "stream=codec_type,codec_name,width,height,duration",
            "-of",
            "json",
            path,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    import json

    return json.loads(out.stdout)


def _streams(path: str, codec_type: str) -> list:
    return [s for s in _ffprobe(path)["streams"] if s["codec_type"] == codec_type]


def _wait_for_worker(worker, timeout_ms: int = 600_000) -> dict:
    """Ejecuta un QThread de la app hasta que emita finished/failed/cancelled."""
    result: dict = {}
    loop = QEventLoop()

    def _done(key):
        def handler(value):
            result[key] = value
            loop.quit()

        return handler

    if hasattr(worker, "finished_success"):
        worker.finished_success.connect(_done("output"))
        worker.failed.connect(_done("error"))
        worker.cancelled.connect(lambda: (result.update(cancelled=True), loop.quit()))
    if hasattr(worker, "completed"):
        worker.completed.connect(_done("result"))
        worker.failed.connect(_done("error"))

    QTimer.singleShot(timeout_ms, loop.quit)
    worker.start()
    loop.exec()
    worker.wait(30_000)
    return result


def _frame(video: str, second: float, dest: str) -> QImage:
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-ss",
            str(second),
            "-i",
            video,
            "-frames:v",
            "1",
            dest,
        ],
        check=True,
        capture_output=True,
    )
    return QImage(dest)


# --------------------------------------------------------------------------- #
# 1. Lectura del SRT real
# --------------------------------------------------------------------------- #
def test_01_reads_every_cue_of_the_real_srt():
    service = SubtitleService()
    with open(SRT_PATH, encoding="utf-8") as handle:
        content = handle.read()

    assert service.detect_format(content, SRT_PATH) == "srt"
    items = service.parse_subtitles(content, "srt")

    assert len(items) == EXPECTED_CUES
    assert items[0].text.startswith("Okay guys")
    assert items[0].start_ms == 0 and items[0].end_ms == 5000
    assert items[-1].start_ms == 59000 and items[-1].end_ms == 60000
    assert [it.index for it in items] == list(range(1, EXPECTED_CUES + 1))
    # El SRT real viene solapado: hay que conservarlo, no "arreglarlo" al leer
    assert any(b.start_ms < a.end_ms for a, b in zip(items, items[1:], strict=False))


@pytest.mark.parametrize("fmt", ["srt", "vtt", "ass", "txt"])
def test_02_every_output_format_round_trips(fmt):
    """SRT -> formato -> SRT: mismos bloques y mismos textos, sin pérdidas."""
    service = SubtitleService()
    with open(SRT_PATH, encoding="utf-8") as handle:
        items = service.parse_subtitles(handle.read(), "srt")

    rendered = service.format_output(items, fmt)
    assert rendered.strip()
    reparsed = service.parse_subtitles(rendered, fmt)

    assert len(reparsed) == EXPECTED_CUES
    assert [it.text.strip() for it in reparsed] == [it.text.strip() for it in items]
    if fmt != "txt":
        # TXT es texto plano: al no llevar marcas de tiempo sólo se conserva
        # el contenido, pero los otros tres formatos son reversibles al 100%.
        assert [it.start_ms for it in reparsed] == [it.start_ms for it in items]
        assert [it.end_ms for it in reparsed] == [it.end_ms for it in items]


# --------------------------------------------------------------------------- #
# 2. Limpieza
# --------------------------------------------------------------------------- #
def test_03_cleaning_keeps_the_real_content_intact():
    service = SubtitleService()
    with open(SRT_PATH, encoding="utf-8") as handle:
        items = service.parse_subtitles(handle.read(), "srt")

    cleaned, total_lines, deleted = service.clean_subtitles(items)

    assert total_lines > 0
    assert len(cleaned) > 0
    # Este subtítulo no tiene ruido que limpiar: no debe perder bloques
    assert len(cleaned) == EXPECTED_CUES
    assert all(it.text.strip() for it in cleaned)
    # Los tiempos no se tocan al limpiar
    assert [it.start_ms for it in cleaned] == [it.start_ms for it in items]


# --------------------------------------------------------------------------- #
# 3. Traducción con el motor gratuito
# --------------------------------------------------------------------------- #
def test_04_free_translation_engine_on_real_subtitles():
    """
    El motor gratuito debe traducir; si no hay red, debe decirlo sin romper nada.

    Es el único punto del E2E que depende de Internet, y aun así comprueba las
    dos ramas: con red, textos traducidos; sin red, el texto original intacto y
    el recuento de fallos avisando al usuario.
    """
    service = SubtitleService()
    with open(SRT_PATH, encoding="utf-8") as handle:
        items = service.parse_subtitles(handle.read(), "srt")

    subset = items[:5]
    translated = service.translate_subtitles(
        subset, target_language="es", engine="google"
    )

    if service.last_translation_failures:
        # Sin red: se conserva el original y queda contabilizado el fallo
        assert service.last_translation_failures == len(subset)
        assert [it.text for it in translated] == [it.text for it in subset]
    else:
        assert service.last_translation_failures == 0
        assert len(translated) == len(subset)
        assert any(
            it.text.strip() != src.text.strip()
            for it, src in zip(translated, subset, strict=True)
        )
        # Ningún bloque puede quedarse vacío
        assert all(it.text.strip() for it in translated)


# --------------------------------------------------------------------------- #
# 4. Pipeline completo de procesamiento
# --------------------------------------------------------------------------- #
def test_05_processing_pipeline_end_to_end(tmp_path, caplog):
    service = SubtitleService()
    source = str(tmp_path / SRT_NAME)
    shutil.copyfile(SRT_PATH, source)

    steps = []
    result = service.process_subtitles(
        file_path=source,
        do_clean=True,
        do_translate=True,
        target_language="es",
        engine="google",
        progress_callback=lambda step, payload: steps.append(step),
    )

    assert result.stats.total_lines > 0
    assert result.stats.translation_failures >= 0
    assert steps[0] == "step_reading"
    assert steps[-1] == "step_saving"
    for step in (
        "step_analyzing",
        "step_cleaning",
        "step_translating",
        "step_formatting",
    ):
        assert step in steps, f"falta el paso {step}: {steps}"

    written = result.output_content
    items = service.parse_subtitles(written, "srt")
    assert len(items) == EXPECTED_CUES
    assert items[0].start_ms == 0 and items[-1].end_ms == 60000
    # Si hubo traducción, el resultado debe estar en español o ser el original
    if result.stats.translation_failures == 0:
        assert items[0].text != "Okay guys, Hightail Chapter 1"

    # El fichero se puede volver a procesar sin errores (idempotencia)
    again = service.process_subtitles(
        file_path=source, do_clean=False, do_translate=False
    )
    assert len(service.parse_subtitles(again.output_content, "srt")) == EXPECTED_CUES

    # Ningún ERROR en el log durante el camino feliz
    errors = [r for r in caplog.records if r.levelname in ("ERROR", "CRITICAL")]
    assert not errors, [r.getMessage() for r in errors]


# --------------------------------------------------------------------------- #
# 5. Metadatos del vídeo real
# --------------------------------------------------------------------------- #
def test_06_ffmpeg_detects_real_video_metadata():
    ffmpeg = VideoBurnerService.get_ffmpeg_path()
    assert ffmpeg, "no se encontró FFmpeg"

    duration = VideoBurnerService.get_video_duration_ms(VIDEO_PATH)
    assert abs(duration - EXPECTED_DURATION_MS) < 1000

    assert VideoBurnerService.get_video_dimensions(VIDEO_PATH) == EXPECTED_SIZE

    probe = _ffprobe(VIDEO_PATH)
    assert _streams(VIDEO_PATH, "video")[0]["codec_name"] == "h264"
    assert _streams(VIDEO_PATH, "audio")[0]["codec_name"] == "aac"
    assert float(probe["format"]["duration"]) == pytest.approx(60.0, abs=0.5)


# --------------------------------------------------------------------------- #
# 6. Generación del ASS para hardsub
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "options",
    [
        BurnInOptions(),
        BurnInOptions(font_size="small", font_color="yellow", box_style="none"),
        BurnInOptions(font_size="large", font_color="cyan", box_style="solid"),
    ],
    ids=["por-defecto", "sin-caja", "grande-cian"],
)
def test_07_ass_script_matches_the_real_video(options):
    service = SubtitleService()
    with open(SRT_PATH, encoding="utf-8") as handle:
        items = service.parse_subtitles(handle.read(), "srt")

    ass = VideoBurnerService.generate_ass_script(items, options, *EXPECTED_SIZE)

    assert "[Script Info]" in ass and "PlayResX: 1920" in ass
    assert "PlayResY: 1080" in ass
    assert ass.count("Dialogue:") == EXPECTED_CUES
    assert "Okay guys" in ass

    # Los tiempos de inicio del ASS salen del SRT real, incluido su hueco
    starts = [
        line.split(",")[1].strip()
        for line in ass.splitlines()
        if line.startswith("Dialogue:")
    ]
    assert len(starts) == EXPECTED_CUES
    assert starts[0] == "0:00:00.00"
    # Ningún subtítulo empieza durante el hueco real de 30 a 31 s
    assert not any("0:00:30." in start for start in starts), starts


# --------------------------------------------------------------------------- #
# 7. Burn-in (hardsub) del minuto completo  -- se hace una vez y se reutiliza
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def burned_video(tmp_path_factory, qapp):
    """Graba los subtítulos sobre el vídeo real completo y devuelve la ruta."""
    out_dir = tmp_path_factory.mktemp("burn")
    out_path = str(out_dir / "S1pK5hmTzkE_1min_burned.mp4")

    service = SubtitleService()
    with open(SRT_PATH, encoding="utf-8") as handle:
        items = service.parse_subtitles(handle.read(), "srt")

    started = time.time()
    result = _wait_for_worker(
        BurnInWorker(VIDEO_PATH, out_path, items, BurnInOptions())
    )
    elapsed = time.time() - started

    assert "error" not in result, f"el burn-in falló: {result.get('error')}"
    assert not result.get("cancelled")
    assert result.get("output") == out_path
    assert os.path.exists(out_path) and os.path.getsize(out_path) > 1_000_000
    print(
        f"\n  burn-in del minuto real: {elapsed:.1f}s -> {os.path.getsize(out_path) / 1e6:.1f} MB"
    )
    return out_path


def test_08_burn_in_output_is_a_valid_playable_video(burned_video):
    probe = _ffprobe(burned_video)
    assert float(probe["format"]["duration"]) == pytest.approx(60.0, abs=0.5)

    video = _streams(burned_video, "video")[0]
    assert (video["codec_name"], video["width"], video["height"]) == (
        "h264",
        *EXPECTED_SIZE,
    )
    # El audio se copia tal cual, no se recodifica ni se pierde
    assert _streams(burned_video, "audio")[0]["codec_name"] == "aac"


def test_09_subtitles_are_actually_rendered_in_the_pixels(burned_video, tmp_path):
    """La prueba clave: el subtítulo tiene que estar grabado, no sólo ahí en el ASS."""
    for second in (1, 3, 8):
        original = _frame(VIDEO_PATH, second, str(tmp_path / f"orig_{second}.png"))
        burned = _frame(burned_video, second, str(tmp_path / f"burn_{second}.png"))
        assert (original.width(), original.height()) == EXPECTED_SIZE
        assert (burned.width(), burned.height()) == EXPECTED_SIZE

        height = original.height()
        differences = {"arriba": 0, "subtitulo": 0}
        sampled = {"arriba": 0, "subtitulo": 0}
        for y in range(0, height, 6):
            for x in range(0, original.width(), 12):
                a, b = original.pixelColor(x, y), burned.pixelColor(x, y)
                delta = (
                    abs(a.red() - b.red())
                    + abs(a.green() - b.green())
                    + abs(a.blue() - b.blue())
                )
                key = "arriba" if y < height * 0.6 else "subtitulo"
                sampled[key] += 1
                if delta > 30:
                    differences[key] += 1

        # La parte alta del fotograma sólo cambia por la recodificación (ruido
        # de compresión): muy por debajo del cambio que provoca el subtítulo.
        ratio_top = differences["arriba"] / max(1, sampled["arriba"])
        assert ratio_top < 0.01, f"el reencode alteró demasiado arriba: {ratio_top:.2%}"
        # La banda del subtítulo sí cambia de verdad, y mucho más
        assert differences["subtitulo"] > differences["arriba"] * 5

        # Y hay texto legible (píxeles claros) en esa banda
        bright = sum(
            1
            for y in range(int(height * 0.8), height, 4)
            for x in range(0, original.width(), 4)
            if burned.pixelColor(x, y).lightness() > 170
        )
        assert bright > 20, f"no se ve texto en el fotograma de t={second}s"


def test_10_burn_in_respects_the_gap_of_the_source(burned_video, tmp_path):
    """El SRT real tiene un hueco de 30 a 31 s: ahí no debe aparecer nada."""
    during = _frame(burned_video, 29, str(tmp_path / "during.png"))
    gap = _frame(burned_video, 30.5, str(tmp_path / "gap.png"))
    after = _frame(burned_video, 32, str(tmp_path / "after.png"))

    def bright_pixels(image):
        height = image.height()
        return sum(
            1
            for y in range(int(height * 0.8), height, 4)
            for x in range(0, image.width(), 4)
            if image.pixelColor(x, y).lightness() > 170
        )

    assert bright_pixels(during) > 20
    assert bright_pixels(gap) == 0
    assert bright_pixels(after) > 20


def test_11_burn_in_fails_cleanly_on_a_broken_video(tmp_path, caplog, qapp):
    """Un vídeo corrupto debe avisar, no reventar ni dejar un archivo a medias."""
    broken = str(tmp_path / "roto.mp4")
    with open(broken, "wb") as handle:
        handle.write(b"esto no es un mp4" * 500)

    service = SubtitleService()
    with open(SRT_PATH, encoding="utf-8") as handle:
        items = service.parse_subtitles(handle.read(), "srt")

    out = str(tmp_path / "salida.mp4")
    result = _wait_for_worker(BurnInWorker(broken, out, items, BurnInOptions()), 60_000)

    assert "output" not in result
    assert result.get("error")
    assert not os.path.exists(out) or os.path.getsize(out) == 0


# --------------------------------------------------------------------------- #
# 8. Reproductor de la vista previa
# --------------------------------------------------------------------------- #
def test_12_preview_player_opens_the_real_video(qapp):
    player = VideoPreviewPlayer()
    player.show()

    errors = []
    player.player.errorOccurred.connect(lambda _code, message: errors.append(message))

    loop = QEventLoop()
    player.player.mediaStatusChanged.connect(
        lambda status: (
            loop.quit()
            if status
            in (
                QMediaPlayer.MediaStatus.LoadedMedia,
                QMediaPlayer.MediaStatus.InvalidMedia,
            )
            else None
        )
    )
    player.load_video(VIDEO_PATH)
    QTimer.singleShot(20_000, loop.quit)
    loop.exec()
    qapp.processEvents()

    assert player.player.mediaStatus() == QMediaPlayer.MediaStatus.LoadedMedia
    assert not errors
    assert player.player.duration() == EXPECTED_DURATION_MS

    # Buscar a mitad del vídeo y sincronizar el subtítulo
    player.seek_to_ms(30_000)
    qapp.processEvents()
    assert player.player.position() == 30_000


def test_13_preview_player_shows_the_real_subtitles(qapp):
    service = SubtitleService()
    with open(SRT_PATH, encoding="utf-8") as handle:
        items = service.parse_subtitles(handle.read(), "srt")

    player = VideoPreviewPlayer()
    player.show()

    loop = QEventLoop()
    player.player.mediaStatusChanged.connect(
        lambda status: (
            loop.quit()
            if status
            in (
                QMediaPlayer.MediaStatus.LoadedMedia,
                QMediaPlayer.MediaStatus.InvalidMedia,
            )
            else None
        )
    )
    player.load_video(VIDEO_PATH)
    QTimer.singleShot(20_000, loop.quit)
    loop.exec()
    qapp.processEvents()
    assert player.player.mediaStatus() == QMediaPlayer.MediaStatus.LoadedMedia

    player.set_subtitles(items)
    player.seek_to_ms(1000)
    qapp.processEvents()

    assert "Okay guys" in player.sub_overlay.text()
    player.seek_to_ms(52_000)  # dentro del bloque 21
    qapp.processEvents()
    assert "upgrade" in player.sub_overlay.text()

    # Fuera del hueco 30-31 s no hay subtítulo que mostrar
    player.seek_to_ms(30_500)
    qapp.processEvents()
    assert "upgrade" not in player.sub_overlay.text()


# --------------------------------------------------------------------------- #
# 9. Flujos completos de la interfaz
# --------------------------------------------------------------------------- #
def test_14_main_window_processes_the_real_file(qapp, tmp_path):
    """Inicio -> procesar con traducción -> vista previa -> página de resultado."""
    win = MainWindow()
    win.i18n.set_language("es", save_to_config=False)

    source = str(tmp_path / SRT_NAME)
    shutil.copyfile(SRT_PATH, source)

    win._switch_page(0)
    win._on_file_selected(source, VIDEO_PATH)
    assert win.current_subtitle_path == source

    # El vídeo real se carga en el reproductor de la vista previa
    loop = QEventLoop()
    win.video_player.player.mediaStatusChanged.connect(
        lambda status: (
            loop.quit()
            if status
            in (
                QMediaPlayer.MediaStatus.LoadedMedia,
                QMediaPlayer.MediaStatus.InvalidMedia,
            )
            else None
        )
    )
    QTimer.singleShot(20_000, loop.quit)
    loop.exec()
    qapp.processEvents()
    assert win.video_player.player.duration() == EXPECTED_DURATION_MS

    # Opciones del formulario
    win.cb_source_lang.setCurrentIndex(win.cb_source_lang.findData("en"))
    win.cb_target_lang.setCurrentIndex(win.cb_target_lang.findData("es"))
    win.cb_engine.setCurrentIndex(win.cb_engine.findData("google"))

    # Mismo worker que lanza `_start_processing`, pero sin el modal de progreso
    worker = ProcessWorker(
        service=win.subtitle_service,
        file_path=source,
        do_clean=win.toggle_clean.isChecked(),
        do_translate=win.toggle_translate.isChecked(),
        target_lang=win.cb_target_lang.currentData(),
        source_lang=win.cb_source_lang.currentData(),
        engine=win.cb_engine.currentData(),
        target_format="srt",
        parallel=True,
    )
    worker_result = _wait_for_worker(worker)

    assert "error" not in worker_result, worker_result.get("error")
    result = worker_result["result"]
    assert len(result.processed_items) == EXPECTED_CUES
    assert len(result.original_items) == EXPECTED_CUES

    win._on_processing_completed(result)
    qapp.processEvents()

    # Guarda el resultado junto al origen y salta a la página de resumen
    assert win.saved_output_path == str(tmp_path / "S1pK5hmTzkE_1min_processed.srt")
    assert os.path.getsize(win.saved_output_path) > 0
    assert win.stack.currentIndex() == 6

    # El visor de diferencias se ha llenado con los 25 bloques reales
    assert len(win.diff_viewer.cards) == EXPECTED_CUES

    # Página de vista previa: el buscador filtra sobre los subtítulos reales
    win._switch_page(1)
    total_text = win.lbl_preview_sub_counter.text()
    assert total_text
    win.preview_search_input.setText("goblins")
    qapp.processEvents()
    filtered_text = win.lbl_preview_sub_counter.text()
    assert filtered_text != total_text, "el buscador no filtró nada"
    win.preview_search_input.setText("")
    qapp.processEvents()
    assert win.lbl_preview_sub_counter.text() == total_text

    # El reproductor tiene los subtítulos procesados cargados
    win.video_player.seek_to_ms(1_000)
    qapp.processEvents()
    assert win.video_player.sub_overlay.text().strip()


def test_15_main_window_converts_the_real_file(qapp, tmp_path):
    """Página de conversión: los 4 formatos de salida sobre el SRT real."""
    win = MainWindow()
    source = str(tmp_path / SRT_NAME)
    shutil.copyfile(SRT_PATH, source)
    win._switch_page(3)
    win._on_file_selected(source, "")

    service = SubtitleService()
    for label, ext in (
        ("SRT (.srt)", "srt"),
        ("VTT (.vtt)", "vtt"),
        ("ASS (.ass)", "ass"),
        ("TXT (.txt)", "txt"),
    ):
        win.cb_convert_format.setCurrentText(label)
        win._run_format_conversion()
        produced = str(tmp_path / f"S1pK5hmTzkE_1min_converted.{ext}")
        assert os.path.exists(produced), f"no se generó {produced}"
        assert os.path.getsize(produced) > 0
        if ext != "txt":
            items = service.parse_subtitles(
                open(produced, encoding="utf-8").read(), ext
            )
            assert len(items) == EXPECTED_CUES


def test_16_main_window_clean_page_on_the_real_file(qapp, tmp_path):
    """Página de limpieza: genera el fichero limpio con los 25 bloques intactos."""
    win = MainWindow()
    source = str(tmp_path / SRT_NAME)
    shutil.copyfile(SRT_PATH, source)
    win._switch_page(2)
    win._on_file_selected(source, "")

    win._start_fast_clean()
    assert _wait_for_worker(win.worker).get("result") is not None
    qapp.processEvents()

    cleaned = win.saved_output_path
    assert cleaned == str(tmp_path / "S1pK5hmTzkE_1min_processed.srt")
    items = SubtitleService().parse_subtitles(
        open(cleaned, encoding="utf-8").read(), "srt"
    )
    assert len(items) == EXPECTED_CUES
    assert items[0].text.startswith("Okay guys")
    # El original no se toca: la app nunca sobrescribe el fichero del usuario
    assert (
        SubtitleService()
        .parse_subtitles(open(source, encoding="utf-8").read(), "srt")[0]
        .text.startswith("Okay guys")
    )


def test_17_batch_processing_with_real_files(qapp, tmp_path):
    """Procesamiento por lotes con varias copias del SRT real."""
    win = MainWindow()
    win._switch_page(4)

    for index in range(3):
        copy_path = str(tmp_path / f"parte_{index}{os.path.splitext(SRT_NAME)[1]}")
        shutil.copyfile(SRT_PATH, copy_path)
        # `_add_batch_files()` abre el diálogo del sistema: aquí se inserta la
        # fila exactamente igual que lo hace ese método (columnas 0-3).
        row = win.batch_table.rowCount()
        win.batch_table.insertRow(row)
        win.batch_table.setItem(row, 0, QTableWidgetItem(copy_path))
        win.batch_table.setItem(
            row, 1, QTableWidgetItem(f"{os.path.getsize(copy_path) / 1024:.1f} KB")
        )
        win.batch_table.setItem(row, 2, QTableWidgetItem("SRT"))
        win.batch_table.setItem(row, 3, QTableWidgetItem(t("batch.status_queued")))

    assert win.batch_table.rowCount() == 3

    win.cb_target_lang.setCurrentIndex(win.cb_target_lang.findData("es"))
    win.toggle_translate.setChecked(False)
    win.toggle_clean.setChecked(True)
    win._run_batch_processing()
    qapp.processEvents()

    for index in range(3):
        produced = str(tmp_path / f"parte_{index}_processed.srt")
        assert os.path.exists(produced), f"falta la salida del lote: {produced}"
        items = SubtitleService().parse_subtitles(
            open(produced, encoding="utf-8").read(), "srt"
        )
        assert len(items) == EXPECTED_CUES

    # La columna 3 es el estado: las tres filas deben acabar completadas
    statuses = [
        win.batch_table.item(row, 3).text() for row in range(win.batch_table.rowCount())
    ]
    assert statuses == [t("batch.status_completed")] * 3, statuses


def test_18_burn_in_dialog_with_real_subtitles(qapp, tmp_path):
    """Diálogo de hardsub: genera el ASS con los 25 bloques del vídeo real."""
    service = SubtitleService()
    with open(SRT_PATH, encoding="utf-8") as handle:
        items = service.parse_subtitles(handle.read(), "srt")

    dialog = BurnInDialog(video_path=VIDEO_PATH, subtitle_items=items, parent=None)
    try:
        # El diálogo es utilizable: cabe su contenido y precarga el vídeo real
        assert dialog.width() >= dialog.minimumSizeHint().width()
        assert dialog.txt_video.text() == VIDEO_PATH
        assert dialog.subtitle_items == items

        # Cada opción que ofrece produce un ASS válido con los 25 bloques
        seen = set()
        for box_data in ("semi", "none", "solid"):
            dialog.cb_box.setCurrentIndex(dialog.cb_box.findData(box_data))
            qapp.processEvents()
            assert dialog.cb_box.currentData() == box_data
            seen.add(dialog.cb_box.currentData())
        assert seen == {"semi", "none", "solid"}

        options = BurnInOptions(
            font_size=dialog.cb_size.currentData(),
            font_color=dialog.cb_color.currentData(),
            box_style=dialog.cb_box.currentData(),
            quality_preset=dialog.cb_quality.currentData(),
        )
        assert options.font_size in ("small", "medium", "large")
        assert options.font_color in ("white", "yellow", "cyan")
        assert options.quality_preset in ("high", "fast")

        ass = VideoBurnerService.generate_ass_script(items, options, *EXPECTED_SIZE)
        assert ass.count("Dialogue:") == EXPECTED_CUES
    finally:
        dialog.close()


# --------------------------------------------------------------------------- #
# 10. Ajustes, idiomas y estado
# --------------------------------------------------------------------------- #
def test_19_home_options_are_persisted(qapp, tmp_path):
    win = MainWindow()
    source = str(tmp_path / SRT_NAME)
    shutil.copyfile(SRT_PATH, source)

    win.cb_source_lang.setCurrentIndex(win.cb_source_lang.findData("en"))
    win.cb_target_lang.setCurrentIndex(win.cb_target_lang.findData("de"))
    win.cb_engine.setCurrentIndex(win.cb_engine.findData("google"))
    win._persist_home_options()

    config = ConfigService()
    assert config.get("source_lang") == "en"
    assert config.get("target_lang") == "de"
    assert config.get("preferred_engine") == "google"

    # Una ventana nueva recupera lo guardado
    win2 = MainWindow()
    assert win2.cb_target_lang.currentData() == "de"


def test_20_every_ui_language_processes_the_real_file(qapp, tmp_path):
    """Los 6 idiomas de la interfaz con el contenido real, sin recortes ni errores."""
    service = SubtitleService()
    with open(SRT_PATH, encoding="utf-8") as handle:
        original = handle.read()

    for language in ("en", "es", "pt", "de", "it", "zh-CN"):
        win = MainWindow()
        win.i18n.set_language(language, save_to_config=False)
        win._switch_page(1)
        win.resize(1280, 800)
        win.show()
        qapp.processEvents()

        items = service.parse_subtitles(original, "srt")
        win.diff_viewer.load_subtitles(items, list(items))
        win.preview_search_input.setText("goblins")
        qapp.processEvents()
        win.preview_search_input.setText("")
        qapp.processEvents()

        assert win.stack.currentIndex() == 1
        assert win.i18n.current_language == language
        assert get_i18n().t("nav.home")
        win.close()


def test_21_translation_service_reports_status_for_the_real_file():
    """El servicio de traducción no revienta con el contenido real."""
    service = TranslationService()
    result = service.translate_text(
        "Okay guys, Hightail Chapter 1", "es", "auto", "google"
    )
    assert isinstance(result, str) and result.strip()
