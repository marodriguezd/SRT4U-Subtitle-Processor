@echo off
echo Building SRT4U Subtitle Processor...
pyinstaller --noconsole --onefile --name "SRT4U" ^
--add-data "application;application" ^
--add-data "assets;assets" ^
--icon "assets\icon.ico" ^
main.py
echo.
echo Done! Check the "dist" folder.
pause
