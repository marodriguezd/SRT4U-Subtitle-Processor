@echo off
REM SRT4U - local Windows build (BASE variant: GUI + CLI).
REM Same recipe as the "Build Windows (.exe)" job in build.yml; keep both in
REM sync. Bundles application, assets, LICENSE and a 64-bit static ffmpeg.exe
REM from .\bin\ (eugeneware/ffmpeg-static, see FFMPEG_VERSION in the workflow).

if not exist "bin\ffmpeg.exe" (
    echo [ERROR] No se encontro .\bin\ffmpeg.exe
    echo.
    echo Coloca un ffmpeg.exe estatico de 64 bits en .\bin\ para que el ejecutable
    echo sea autocontenido. Ver FFMPEG_VERSION en .github/workflows/build.yml.
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

REM FULL variant (API + Whisper): pip install ".[api,transcription]", then
REM uncomment the --collect-all/--hidden-import flags below. Models are never bundled.
echo.
echo Done! Check the "dist" folder ^(dist\SRT4U.exe^).
pause
