@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo StreamTTS has not been set up yet.
    echo First run setup_windows.bat from this folder.
    pause
    exit /b 1
)

if not exist "models\vits-piper-en_US-amy-low\en_US-amy-low.onnx" (
    echo Sample voice model is missing.
    echo Run setup_windows.bat to install it.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" "python\interactive_test.py"
if errorlevel 1 (
    echo.
    echo StreamTTS exited with an error. See the message above.
    pause
)
