@echo off
cd /d "%~dp0"
title LogPulse - Automated Test Suite

echo ============================================================
echo   LogPulse - Automated Test Suite Runner (Pytest)
echo ============================================================
echo.

:: 1. Check Python
echo [1/4] Checking Python installation...
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not found on PATH.
    echo Please install Python 3.9+ and add it to PATH.
    echo.
    pause
    exit /b 1
)
for /f "tokens=*" %%i in ('python --version') do set PY_VER=%%i
echo   Found %PY_VER%
echo.

:: 2. Check virtual environment
echo [2/4] Checking virtual environment in %CD%\.venv ...
if not exist ".venv\Scripts\python.exe" (
    echo   .venv not found. Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        echo.
        pause
        exit /b 1
    )
    echo   Created virtual environment.
) else (
    echo   Virtual environment found.
)
echo.

:: 3. Activate virtual environment
echo [3/4] Activating virtual environment...
call ".venv\Scripts\activate.bat"
if errorlevel 1 (
    echo [ERROR] Failed to activate virtual environment.
    echo.
    pause
    exit /b 1
)
echo   Activated: %VIRTUAL_ENV%
echo.

:: Ensure pytest is installed in the virtual environment
python -c "import pytest" >nul 2>&1
if errorlevel 1 (
    echo   Installing pytest in virtual environment...
    python -m pip install pytest --quiet
)

:: Ensure project dependencies are installed
python -c "import pandas, yaml, dateutil" >nul 2>&1
if errorlevel 1 (
    echo   Installing project dependencies from requirements.txt...
    python -m pip install -r requirements.txt --quiet
)

:: 4. Run Pytest
echo [4/4] Executing test suite...
echo ============================================================
echo.

python -m pytest tests -v

set TEST_EXIT=%errorlevel%

echo.
echo ============================================================
if %TEST_EXIT% equ 0 (
    echo   [SUCCESS] All tests passed cleanly.
) else (
    echo   [FAILURE] Tests finished with exit code %TEST_EXIT%.
)
echo ============================================================
echo.
pause
exit /b %TEST_EXIT%
