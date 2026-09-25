# application/services/video_burner_service.py
"""
Servicio de quemado de subtítulos en vídeo (Hardsub / Burn-In) mediante FFmpeg.
Soporta detección multiplataforma de binarios, generación de estilos ASS avanzados
y cálculo de progreso/ETA en tiempo real.
"""
import os
import re
import sys
import shutil
import tempfile
import subprocess
from dataclasses import dataclass
from typing import Optional, List, Tuple
from PyQt6.QtCore import QThread, pyqtSignal

from .subtitle_service import SubtitleItem


@dataclass
class BurnInOptions:
    font_size: str = "Mediano"  # "Pequeño", "Mediano", "Grande"
    font_color: str = "Blanco"  # "Blanco", "Amarillo", "Cian"
    box_style: str = "Caja semitransparente"  # "Sin fondo", "Caja semitransparente", "Caja sólida"
    quality_preset: str = "Alta calidad"  # "Alta calidad", "Rápido"
    fix_overlaps: bool = True  # Ajusta tiempos automáticamente para evitar solapamientos


class VideoBurnerService:
    @staticmethod
    def _is_working_binary(path: str) -> bool:
        if not path or not os.path.isfile(path) or not os.access(path, os.X_OK):
            return False
        try:
            res = subprocess.run([path, "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2)
            return res.returncode == 0
        except Exception:
            return False

    @classmethod
    def get_ffmpeg_path(cls) -> Optional[str]:
        """
        Localiza un binario de FFmpeg funcional en el sistema o dentro del paquete de la app.
        Valida que el binario realmente ejecute sin errores de librerías dinámicas.
        """
        candidates = []

        # 1. PyInstaller bundled path
        if hasattr(sys, "_MEIPASS"):
            exe_name = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
            candidates.append(os.path.join(sys._MEIPASS, exe_name))
            candidates.append(os.path.join(sys._MEIPASS, "bin", exe_name))

        if getattr(sys, "frozen", False):
            exe_dir = os.path.dirname(sys.executable)
            candidates.append(os.path.join(exe_dir, "ffmpeg"))
            candidates.append(os.path.join(exe_dir, "ffmpeg.exe"))
            candidates.append(os.path.join(exe_dir, "..", "Resources", "ffmpeg"))

        # 2. Local app directory bin/
        app_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        local_exe = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
        candidates.append(os.path.join(app_root, "bin", local_exe))

        # 3. System PATH
        system_ffmpeg = shutil.which("ffmpeg")
        if system_ffmpeg:
            candidates.append(system_ffmpeg)

        # 4. Fallbacks comunes en Linux/Unix
        for fallback in ["/usr/bin/ffmpeg", "/usr/local/bin/ffmpeg", "/opt/homebrew/bin/ffmpeg"]:
            if fallback not in candidates:
                candidates.append(fallback)

        for cand in candidates:
            if cls._is_working_binary(cand):
                return cand

        return None

    @staticmethod
    def get_video_duration_ms(video_path: str, ffmpeg_path: Optional[str] = None) -> Optional[int]:
        """
        Obtiene la duración total del archivo de vídeo en milisegundos usando ffmpeg -i.
        """
        ffmpeg = ffmpeg_path or VideoBurnerService.get_ffmpeg_path()
        if not ffmpeg or not os.path.exists(video_path):
            return None

        try:
            cmd = [ffmpeg, "-i", video_path]
            # FFmpeg escribe información del contenedor en stderr
            res = subprocess.run(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
            )
            # Buscar "Duration: 00:02:15.34"
            match = re.search(r"Duration:\s*(\d{2}):(\d{2}):(\d{2}(?:\.\d+)?)", res.stderr)
            if match:
                hours = int(match.group(1))
                minutes = int(match.group(2))
                seconds = float(match.group(3))
                total_ms = int((hours * 3600 + minutes * 60 + seconds) * 1000)
                return total_ms
        except Exception:
            pass

        return None

    @staticmethod
    def get_video_dimensions(video_path: str, ffmpeg_path: Optional[str] = None) -> Tuple[int, int]:
        """
        Obtiene las dimensiones (ancho, alto) del archivo de vídeo.
        Si no se detectan, devuelve (1920, 1080) por defecto.
        """
        ffmpeg = ffmpeg_path or VideoBurnerService.get_ffmpeg_path()
        if not ffmpeg or not os.path.exists(video_path):
            return 1920, 1080

        try:
            cmd = [ffmpeg, "-i", video_path]
            res = subprocess.run(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
            )
            match = re.search(r"Stream.*Video:.*,\s*(\d{2,5})x(\d{2,5})", res.stderr)
            if match:
                return int(match.group(1)), int(match.group(2))
        except Exception:
            pass

        return 1920, 1080

    @staticmethod
    def generate_ass_script(
        items: List[SubtitleItem],
        options: BurnInOptions,
        video_width: int = 1920,
        video_height: int = 1080,
    ) -> str:
        """
        Genera el script ASS (Advanced SubStation Alpha) configurado con las opciones visuales,
        proporcional a la resolución del vídeo y corrigiendo solapamientos.
        """
        # 1. Sanitizar y corregir solapamientos temporales si está habilitado
        processed_items: List[SubtitleItem] = []
        if items:
            sorted_items = sorted(items, key=lambda x: (x.start_ms, x.end_ms))
            for i, it in enumerate(sorted_items):
                s_ms = max(0, it.start_ms)
                e_ms = max(s_ms + 250, it.end_ms)
                processed_items.append(SubtitleItem(
                    index=i + 1,
                    start_ms=s_ms,
                    end_ms=e_ms,
                    text=it.text,
                    style=it.style,
                    extra=it.extra
                ))

            if options.fix_overlaps and len(processed_items) > 1:
                for i in range(len(processed_items) - 1):
                    curr_item = processed_items[i]
                    next_item = processed_items[i + 1]
                    if curr_item.end_ms > next_item.start_ms:
                        if next_item.start_ms > curr_item.start_ms:
                            # Acortar el actual dejando un respiro de 40ms antes del siguiente
                            curr_item.end_ms = max(curr_item.start_ms + 200, next_item.start_ms - 40)

        # 2. Resolución de referencia (PlayResX / PlayResY)
        vw = max(320, video_width)
        vh = max(240, video_height)

        # Mapeo de tamaño proporcional a la altura del vídeo (evita subtítulos gigantes en cualquier resolución)
        size_ratios = {
            "Pequeño": 0.035,   # ~38px en 1080p, ~24px en 700p
            "Mediano": 0.045,   # ~48px en 1080p, ~31px en 700p (legibilidad óptima estándar)
            "Grande": 0.058,    # ~62px en 1080p, ~40px en 700p
        }
        ratio = size_ratios.get(options.font_size, 0.045)
        fontsize = max(16, int(round(vh * ratio)))

        # Mapeo de color en formato ASS (&HAABBGGRR)
        color_map = {
            "Blanco": "&H00FFFFFF",
            "Amarillo": "&H0000FFFF",  # Blue=0, Green=FF, Red=FF
            "Cian": "&H00FFFF00",      # Blue=FF, Green=FF, Red=0
        }
        primary_color = color_map.get(options.font_color, "&H00FFFFFF")

        # Márgenes proporcionales a la pantalla
        margin_v = max(15, int(round(vh * 0.048)))
        margin_lr = max(20, int(round(vw * 0.04)))

        # Mapeo de estilo de caja / fondo
        if options.box_style == "Sin fondo":
            # BorderStyle 1 = Outline + Drop Shadow
            border_style = 1
            outline = max(2, int(round(vh * 0.003)))
            shadow = max(1, int(round(vh * 0.002)))
            outline_color = "&H00000000"  # Contorno negro nítido
            back_color = "&H80000000"     # Sombra semitransparente
        elif options.box_style == "Caja sólida":
            # BorderStyle 3 = Opaque Box (OutlineColour define el fondo de la caja)
            border_style = 3
            outline = max(2, int(round(vh * 0.004)))
            shadow = 0
            outline_color = "&H00000000"  # Caja 100% opaca negra
            back_color = "&H00000000"
        else:
            # "Caja semitransparente" (50% opacidad &H80000000)
            border_style = 3
            outline = max(2, int(round(vh * 0.004)))
            shadow = 0
            outline_color = "&H80000000"  # Caja semitransparente
            back_color = "&H80000000"

        header = f"""[Script Info]
Title: SRT4U Burn-In Subtitles
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.601
PlayResX: {vw}
PlayResY: {vh}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,sans-serif,{fontsize},{primary_color},&H000000FF,{outline_color},{back_color},0,0,0,0,100,100,0,0,{border_style},{outline},{shadow},2,{margin_lr},{margin_lr},{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        events = []
        for item in processed_items:
            clean_text = item.text or ""
            clean_text = clean_text.replace("<i>", r"{\i1}").replace("</i>", r"{\i0}")
            clean_text = clean_text.replace("<b>", r"{\b1}").replace("</b>", r"{\b0}")
            clean_text = clean_text.replace("<u>", r"{\u1}").replace("</u>", r"{\u0}")
            ass_text = clean_text.replace("\n", r"\N")
            start = item.get_ass_start()
            end = item.get_ass_end()
            style = "Default"
            events.append(f"Dialogue: 0,{start},{end},{style},,0,0,0,,{ass_text}")

        return header + "\n".join(events) + "\n"


class BurnInWorker(QThread):
    progress_updated = pyqtSignal(float, str, str)  # (percent 0-100, speed_str, eta_str)
    finished_success = pyqtSignal(str)              # output_path
    failed = pyqtSignal(str)                        # error_message
    cancelled = pyqtSignal()

    def __init__(
        self,
        video_path: str,
        output_path: str,
        subtitle_items: List[SubtitleItem],
        options: BurnInOptions,
        parent=None,
    ):
        super().__init__(parent)
        self.video_path = video_path
        self.output_path = output_path
        self.subtitle_items = subtitle_items
        self.options = options
        self._is_cancelled = False
        self._process: Optional[subprocess.Popen] = None

    def cancel(self):
        self._is_cancelled = True
        if self._process and self._process.poll() is None:
            try:
                self._process.terminate()
                self._process.wait(timeout=1.5)
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass

    def run(self):
        ffmpeg_bin = VideoBurnerService.get_ffmpeg_path()
        if not ffmpeg_bin:
            self.failed.emit(
                "No se encontró un binario de FFmpeg funcional en el sistema ni en el paquete de la aplicación.\n"
                "Asegúrate de tener FFmpeg instalado para incrustar subtítulos."
            )
            return

        if not os.path.exists(self.video_path):
            self.failed.emit(f"El archivo de vídeo no existe:\n{self.video_path}")
            return

        # Asegurar directorio de salida
        out_dir = os.path.dirname(os.path.abspath(self.output_path))
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)

        # 1. Obtener duración y dimensiones del vídeo
        duration_ms = VideoBurnerService.get_video_duration_ms(self.video_path, ffmpeg_bin)
        duration_sec = (duration_ms / 1000.0) if duration_ms and duration_ms > 0 else None
        vw, vh = VideoBurnerService.get_video_dimensions(self.video_path, ffmpeg_bin)

        # 2. Generar archivo ASS en directorio temporal
        temp_dir = tempfile.mkdtemp(prefix="srt4u_burn_")
        ass_filename = "subtitles.ass"
        ass_path = os.path.join(temp_dir, ass_filename)
        stderr_log_path = os.path.join(temp_dir, "ffmpeg_stderr.log")

        try:
            ass_content = VideoBurnerService.generate_ass_script(
                self.subtitle_items, self.options, video_width=vw, video_height=vh
            )
            with open(ass_path, "w", encoding="utf-8") as f:
                f.write(ass_content)

            # 3. Configurar parámetros de codificación
            if self.options.quality_preset == "Rápido":
                v_preset = "ultrafast"
                v_crf = "23"
            else:
                v_preset = "medium"
                v_crf = "20"

            cmd = [
                ffmpeg_bin,
                "-y",
                "-i", os.path.abspath(self.video_path),
                "-vf", f"ass={ass_filename}",
                "-c:v", "libx264",
                "-preset", v_preset,
                "-crf", v_crf,
                "-c:a", "copy",
                "-progress", "pipe:1",
                os.path.abspath(self.output_path),
            ]

            with open(stderr_log_path, "w", encoding="utf-8") as stderr_file:
                self._process = subprocess.Popen(
                    cmd,
                    cwd=temp_dir,
                    stdout=subprocess.PIPE,
                    stderr=stderr_file,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )

                current_time_sec = 0.0
                current_speed_str = "1.0x"

                while True:
                    if self._is_cancelled:
                        if os.path.exists(self.output_path):
                            try:
                                os.remove(self.output_path)
                            except Exception:
                                pass
                        self.cancelled.emit()
                        return

                    line = self._process.stdout.readline()
                    if not line:
                        if self._process.poll() is not None:
                            break
                        continue

                    line = line.strip()
                    if line.startswith("out_time_us="):
                        try:
                            us = int(line.split("=")[1])
                            current_time_sec = us / 1000000.0
                        except Exception:
                            pass
                    elif line.startswith("speed="):
                        val = line.split("=")[1].strip()
                        if val != "N/A":
                            current_speed_str = val

                    # Emitir progreso periódico al recibir progress=continue
                    if line.startswith("progress=") and duration_sec and duration_sec > 0:
                        percent = min(100.0, max(0.0, (current_time_sec / duration_sec) * 100.0))
                        
                        # Calcular ETA
                        speed_float = 1.0
                        try:
                            speed_float = float(current_speed_str.rstrip("x"))
                            if speed_float <= 0.01:
                                speed_float = 1.0
                        except Exception:
                            speed_float = 1.0

                        remaining_sec = max(0.0, (duration_sec - current_time_sec) / speed_float)
                        eta_mins = int(remaining_sec // 60)
                        eta_secs = int(remaining_sec % 60)
                        eta_str = f"{eta_mins:02d}:{eta_secs:02d}"

                        self.progress_updated.emit(percent, current_speed_str, eta_str)

                self._process.wait()

            if self._is_cancelled:
                if os.path.exists(self.output_path):
                    try:
                        os.remove(self.output_path)
                    except Exception:
                        pass
                self.cancelled.emit()
                return

            if self._process.returncode == 0:
                self.progress_updated.emit(100.0, current_speed_str, "00:00")
                self.finished_success.emit(self.output_path)
            else:
                stderr_text = ""
                if os.path.exists(stderr_log_path):
                    try:
                        with open(stderr_log_path, "r", encoding="utf-8", errors="replace") as ef:
                            stderr_text = ef.read()
                    except Exception:
                        pass
                self.failed.emit(f"FFmpeg finalizó con error (código {self._process.returncode}):\n{stderr_text[-600:]}")

        except Exception as e:
            if not self._is_cancelled:
                self.failed.emit(f"Excepción al ejecutar FFmpeg:\n{str(e)}")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
