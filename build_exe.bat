@echo off
echo Building SRT4U Subtitle Processor (BASE: GUI + CLI, sin API ni Whisper)...
REM Base compila sin los extras: la API (FastAPI) y Whisper (faster-whisper)
REM se importan de forma perezosa y la app los detecta en runtime.
REM Variante FULL (requiere extras instalados + FFmpeg en bin\):
REM   1. pip install ".[api,transcription]"
REM   2. coloca ffmpeg.exe en bin\ (o PATH) para transcripcion/burn-in
REM   3. descomenta --collect-all faster_whisper --collect-all ctranslate2
REM      y --hidden-import uvicorn a continuacion. Los modelos Whisper
REM      NUNCA se empaquetan: se descargan una vez con aviso.
pyinstaller --noconsole --onefile --name "SRT4U" ^
--add-data "application;application" ^
--add-data "assets;assets" ^
--icon "assets\icon.ico" ^
main.py
echo.
echo Done! Check the "dist" folder.
pause
