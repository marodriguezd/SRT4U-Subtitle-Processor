@echo off
echo Building SRT4U Subtitle Processor...
pyinstaller --noconsole --onefile --name "SRT4U" ^
--add-data "application;application" ^
main.py
echo.
echo Done! Check the "dist" folder.
pause
