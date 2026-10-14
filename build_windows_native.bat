@echo off
setlocal
cd /d "%~dp0"

REM Native C++ library build only. This is not needed for the Python test app.
REM sherpa-onnx officially does not support MinGW on Windows. The supported
REM source-build route needs the MSVC C++ Build Tools (the full Visual Studio IDE
REM is not necessary, but the Microsoft C++ toolchain is).

where cmake >nul 2>nul
if errorlevel 1 (
    echo ERROR: CMake 3.24 or newer was not found on PATH.
    echo Install CMake from https://cmake.org/download/
    exit /b 1
)
REM If Build Tools are installed, initialize their environment from ordinary CMD.
if not defined VSCMD_VER (
    set "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
    if exist "%VSWHERE%" (
        for /f "usebackq tokens=*" %%i in (`"%VSWHERE%" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath`) do set "VSROOT=%%i"
        if defined VSROOT if exist "%VSROOT%\Common7\Tools\VsDevCmd.bat" call "%VSROOT%\Common7\Tools\VsDevCmd.bat" -arch=x64 -host_arch=x64
    )
)
where cl >nul 2>nul
if errorlevel 1 (
    echo ERROR: The MSVC compiler 'cl.exe' was not found.
    echo MinGW is not supported by upstream sherpa-onnx on Windows.
    echo Install Microsoft Visual Studio Build Tools with the C++ build tools workload.
    echo The full Visual Studio IDE is not needed; this script initializes the compiler from CMD.
    echo If you do not want to install a compiler, use setup_windows.bat instead.
    exit /b 1
)

python scripts\download_miniaudio.py
if errorlevel 1 exit /b 1
python scripts\download_model.py
if errorlevel 1 exit /b 1
cmake -S . -B build -G "Visual Studio 17 2022" -A x64 -DSTREAMTTS_BUILD_DEMO=ON -DBUILD_SHARED_LIBS=ON
if errorlevel 1 exit /b 1
cmake --build build --config Release --parallel
if errorlevel 1 exit /b 1
ctest --test-dir build -C Release --output-on-failure
if errorlevel 1 exit /b 1

echo Native C++ build completed.
