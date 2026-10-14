@echo off
setlocal
cd /d "%~dp0"

echo ================================================
echo StreamTTS - Windows Python setup
echo ================================================
echo This route runs from normal CMD or Windows Terminal.
echo It does not require Visual Studio or a C++ compiler.
echo.

where py >nul 2>nul
if %errorlevel%==0 (
    set "PY=py -3"
) else (
    where python >nul 2>nul
    if errorlevel 1 (
        echo ERROR: Python 3 was not found.
        echo Install Python 3.10 or newer from https://www.python.org/downloads/windows/
        echo During installation, enable the option to add Python to PATH.
        pause
        exit /b 1
    )
    set "PY=python"
)

%PY% --version
if errorlevel 1 goto :failed

if not exist ".venv\Scripts\python.exe" (
    echo Creating a private Python environment...
    %PY% -m venv .venv
    if errorlevel 1 goto :failed
)

call ".venv\Scripts\activate.bat"
if errorlevel 1 goto :failed

echo.
echo Installing prebuilt Python packages and system-voice support. No C++ compiler is used here...
python -m pip install --upgrade pip
if errorlevel 1 goto :failed
python -m pip install sherpa-onnx sherpa-onnx-bin numpy sounddevice librosa pyttsx3 pywin32
if errorlevel 1 goto :failed

echo.
echo Downloading the sample English voice model. This needs internet access...
python scripts\download_model.py
if errorlevel 1 goto :failed

echo.
echo Setup complete. Launch run_windows_gui.bat for the settings GUI, or run_windows_test.bat for the terminal tester.
echo.
pause
exit /b 0

:failed
echo.
echo Setup failed. Read the error above and check internet access / Python installation.
pause
exit /b 1
