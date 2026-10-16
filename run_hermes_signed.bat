@echo off
setlocal enabledelayedexpansion

echo =======================================================================
echo          HERMES AGENT / VENV DEVICE GUARD BYPASS LAUNCHER              
echo =======================================================================
echo.

:: Path to virtual environment site-packages
set "VENV_SITE_PACKAGES=C:\Users\scott\AppData\Local\hermes\hermes-agent\venv\Lib\site-packages"

:: Target variable for the found python executable
set "SIGNED_PYTHON="

:: 1. Check if Python is available on system PATH
for /f "tokens=*" %%i in ('where python 2^>nul') do (
    echo %%i | findstr /i /v "venv" | findstr /i /v "AppData\Local\hermes" >nul
    if !errorlevel! == 0 (
        if not defined SIGNED_PYTHON set "SIGNED_PYTHON=%%i"
    )
)

:: 2. Check standard AppData user installation paths
if "%SIGNED_PYTHON%"=="" (
    for %%V in (313 312 311 310 39) do (
        if exist "%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe" (
            set "SIGNED_PYTHON=%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe"
            goto :FOUND_PYTHON
        )
    )
)

:: 3. Check Program Files installation paths
if "%SIGNED_PYTHON%"=="" (
    for %%V in (313 312 311 310 39) do (
        if exist "C:\Program Files\Python%%V\python.exe" (
            set "SIGNED_PYTHON=C:\Program Files\Python%%V\python.exe"
            goto :FOUND_PYTHON
        )
    )
)

:FOUND_PYTHON
if "%SIGNED_PYTHON%"=="" (
    echo [ERROR] Could not locate an executable Python installation on this machine.
    echo Please verify where Python is installed.
    pause
    exit /b 1
)

echo [INFO] Located Python Executable: "%SIGNED_PYTHON%"
echo [INFO] Injecting VENV Site Packages: "%VENV_SITE_PACKAGES%"
echo.

:: Set PYTHONPATH to load dependencies from the virtual environment
set "PYTHONPATH=%VENV_SITE_PACKAGES%;%PYTHONPATH%"

:: Execute python script or launch interactive mode
if "%~1"=="" (
    "%SIGNED_PYTHON%" -c "import sys; print('[SUCCESS] Running via:', sys.executable)"
) else (
    "%SIGNED_PYTHON%" %*
)

echo.
echo =======================================================================
pause