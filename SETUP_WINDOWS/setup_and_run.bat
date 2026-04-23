@echo off
REM BiblioForge - Setup and Run Script for Windows
REM This script sets up the environment and runs BiblioForge

setlocal enabledelayedexpansion
cd /d "%~dp0"

REM Navigate to the BiblioForge project directory
cd ../BiblioForge

REM Color codes for output
echo.
echo ========================================
echo   BiblioForge - Setup and Run (Windows)
echo ========================================
echo.

REM Search for Python in common locations
set "PYTHON_FOUND="
set "PYTHON_PATH="

REM Try python in PATH first
python --version >nul 2>&1
if errorlevel 0 (
    set "PYTHON_FOUND=1"
    set "PYTHON_PATH=python"
)

REM Search in AppData\Local\Programs\Python (modern Python installer default)
if not defined PYTHON_FOUND (
    for /d %%i in ("%AppData%\..\Local\Programs\Python*") do (
        if exist "%%i\python.exe" (
            set "PYTHON_FOUND=1"
            set "PYTHON_PATH=%%i\python.exe"
            goto :found_python
        )
    )
)

REM Search in Program Files
if not defined PYTHON_FOUND (
    for /d %%i in ("C:\Program Files\Python*") do (
        if exist "%%i\python.exe" (
            set "PYTHON_FOUND=1"
            set "PYTHON_PATH=%%i\python.exe"
            goto :found_python
        )
    )
)

REM Search in Program Files (x86)
if not defined PYTHON_FOUND (
    for /d %%i in ("C:\Program Files (x86)\Python*") do (
        if exist "%%i\python.exe" (
            set "PYTHON_FOUND=1"
            set "PYTHON_PATH=%%i\python.exe"
            goto :found_python
        )
    )
)

:found_python
if not defined PYTHON_FOUND (
    echo [ERROR] Python non trovato nel sistema
    echo.
    echo Soluzione:
    echo 1. Scarica Python da: https://www.python.org/downloads/
    echo 2. Avvia l'installer e ASSICURATI di selezionare:
    echo    - "Add Python to PATH" (checkbox in basso)
    echo    - Seleziona "Install for all users" (se hai permessi admin)
    echo 3. Completa l'installazione
    echo 4. Riapri questo script (.bat)
    echo.
    echo Alternativa: Se hai gia' Python installato ma non nel PATH:
    echo - Apri Pannello di Controllo ^> Sistema ^> Variabili di ambiente
    echo - Aggiungi il percorso di Python al PATH
    echo.
    pause
    exit /b 1
)

echo [1/4] Checking Python installation...
for /f "tokens=*" %%i in ('!PYTHON_PATH! --version') do set PYTHON_VERSION=%%i
echo        Found: !PYTHON_VERSION!
echo.

REM Check if virtual environment exists
if exist ".venv" (
    echo [2/4] Virtual environment already exists, skipping creation...
) else (
    echo [2/4] Creating virtual environment...
    !PYTHON_PATH! -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment
        pause
        exit /b 1
    )
    echo        Virtual environment created successfully
)
echo.

REM Activate virtual environment
echo [3/4] Activating virtual environment and installing dependencies...
call .venv\Scripts\activate.bat
if errorlevel 1 (
    echo [ERROR] Failed to activate virtual environment
    pause
    exit /b 1
)

REM Install requirements
pip install -q --upgrade pip
pip install -q -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies
    echo.
    echo Trying alternative method...
    pip install streamlit httpx pydantic pandas openpyxl google-api-python-client google-auth
    if errorlevel 1 (
        echo [ERROR] Failed to install dependencies with alternative method
        pause
        exit /b 1
    )
)
echo        Dependencies installed successfully
echo.

REM Run the application
echo [4/4] Starting BiblioForge...
echo        Dashboard will open at http://localhost:8501
echo.
echo Press Ctrl+C to stop the application
echo.

python main.py dashboard

REM If the program exits, show a message
echo.
echo BiblioForge has been closed
echo.
pause
