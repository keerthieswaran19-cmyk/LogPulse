@echo off
cd /d "%~dp0"
title LogPulse - Analytics Dashboard Runner

echo ============================================================
echo   LogPulse - Application Log Analytics Dashboard
echo ============================================================
echo.

:: 1. Check Python
echo [1/6] Checking Python installation...
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not found on PATH.
    echo Please install Python 3.9+ from https://www.python.org/ and try again.
    echo.
    pause
    exit /b 1
)
for /f "tokens=*" %%i in ('python --version') do set PY_VER=%%i
echo   Found %PY_VER%
echo.

:: 2. Check virtual environment
echo [2/6] Checking virtual environment in %CD%\.venv ...
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
echo [3/6] Activating virtual environment...
call ".venv\Scripts\activate.bat"
if errorlevel 1 (
    echo [ERROR] Failed to activate virtual environment.
    echo.
    pause
    exit /b 1
)
echo   Activated: %VIRTUAL_ENV%
echo.

:: 4. Upgrade pip
echo [4/6] Checking pip...
python -m pip install --upgrade pip --quiet
echo.

:: 5. Install requirements
echo [5/6] Checking dependencies from requirements.txt...
if exist "requirements.txt" (
    python -m pip install -r requirements.txt --quiet
    if errorlevel 1 (
        echo [ERROR] Failed to install dependencies.
        echo.
        pause
        exit /b 1
    )
    echo   Dependencies up to date.
)
echo.

:: 6. Verify Streamlit
echo [6/6] Verifying Streamlit...
python -c "import streamlit" >nul 2>&1
if errorlevel 1 (
    echo   Installing Streamlit...
    python -m pip install streamlit --quiet
    if errorlevel 1 (
        echo [ERROR] Failed to install Streamlit.
        echo.
        pause
        exit /b 1
    )
)
echo   Streamlit ready.
echo.

echo ============================================================
echo   Launching LogPulse Dashboard in browser...
echo   URL: http://localhost:8501
echo   Press CTRL+C in this window to stop the server.
echo ============================================================
echo.

python -m streamlit run dashboard/app.py

if errorlevel 1 (
    echo.
    echo [ERROR] Dashboard exited with error.
    echo.
    pause
)
