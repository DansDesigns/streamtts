@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo StreamTTS Python environment is missing.
    echo Run setup_windows.bat first.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" python\gui_app.py
if errorlevel 1 (
    echo.
    echo StreamTTS GUI exited with an error. Read the details above.
    pause
)
