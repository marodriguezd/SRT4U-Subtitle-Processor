@echo off
REM ============================================================================
REM SRT4U - build local de Windows (variante BASE: GUI + CLI)
REM
REM Esta es la MISMA receta que usa el job "Build Windows (.exe)" del workflow
REM .github/workflows/build.yml, para que el .exe local sea equivalente al
REM publicado. No debe divergir: si cambias uno, cambia el otro.
REM
REM Material que se empaqueta (los cuatro, igual que en CI):
REM   application -> codigo de la app
REM   assets      -> iconos y capturas
REM   LICENSE     -> licencia (la pagina "Ver licencia" la abre en local)
REM   ffmpeg.exe  -> burn-in autocontenido
REM
REM La variante BASE NO necesita extras: la API (FastAPI) y Whisper
REM (faster-whisper) se importan de forma perezosa y la app las detecta en
REM tiempo de ejecucion. Para la variante FULL ver el comentario final.
REM
REM Requisito previo: un ffmpeg.exe estatico DE 64 bits en .\bin\ffmpeg.exe
REM   - Descargalo de https://www.gyan.dev/ffmpeg/builds/ (ffmpeg release
REM     essentials, "ffmpeg-*-essentials_build.zip") o de
REM     https://github.com/eugeneware/ffmpeg-static/releases
REM     (mismo binario que fija CI: FFMPEG_VERSION=b6.1.1, asset
REM     ffmpeg-win32-x64), y copialo a .\bin\ffmpeg.exe
REM   - Sin el, el burn-in usara el FFmpeg del sistema si esta en PATH, pero el
REM     .exe no quedara autocontenido.
REM ============================================================================

if not exist "bin\ffmpeg.exe" (
    echo [ERROR] No se encontro .\bin\ffmpeg.exe
    echo.
    echo Coloca un ffmpeg.exe estatico de 64 bits en .\bin\ para que el ejecutable
    echo sea autocontenido. Ver el comentario de este .bat para el enlace.
    echo.
    pause
    exit /b 1
)

if not exist "LICENSE" (
    echo [ERROR] No se encontro .\LICENSE en la raiz del repositorio.
    pause
    exit /b 1
)

if not exist "main.py" (
    echo [ERROR] Ejecuta este script desde la raiz del repositorio ^(junto a main.py^).
    pause
    exit /b 1
)

pyinstaller --noconsole --onefile --name "SRT4U" ^
--add-data "application;application" ^
--add-data "assets;assets" ^
--add-data "LICENSE;." ^
--add-binary "bin\ffmpeg.exe;." ^
--icon "assets\icon.ico" ^
main.py

if errorlevel 1 (
    echo.
    echo [ERROR] Pyinstaller fallo. Revisa el mensaje anterior.
    pause
    exit /b 1
)

REM Variante FULL (API + transcripcion Whisper): requiere antes
REM   1. pip install ".[api,transcription]"
REM   2. descomenta --collect-all faster_whisper --collect-all ctranslate2
REM      y --hidden-import uvicorn a continuacion. Los modelos Whisper
REM      NUNCA se empaquetan: se descargan una vez con aviso.
echo.
echo Done! Check the "dist" folder ^(dist\SRT4U.exe^).
pause
