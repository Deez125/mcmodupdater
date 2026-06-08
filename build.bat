@echo off
REM Builds a single-file Windows .exe your friends can just double-click.
REM Run this from the project root after installing deps.

python -m pip install -r requirements-dev.txt
pyinstaller --noconfirm --onefile --windowed ^
  --name "MCModUpdater" ^
  --collect-all customtkinter ^
  --add-data "icon.png;." ^
  --icon "icon.png" ^
  run.py

echo.
echo Done. Your .exe is in the "dist" folder.
pause
