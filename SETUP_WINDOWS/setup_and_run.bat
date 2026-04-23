@echo off
setlocal enabledelayedexpansion

REM Impedisci che questo script si chiuda subito
if "%BIBLIOFORGE_RUNNING%"=="1" (
    echo.
    echo [ERROR] Lo script si sta richiamando a se stesso!
    echo Contatta: francesco.caldarelli@studenti.unicam.it
    echo.
    pause
    exit /b 1
)
set "BIBLIOFORGE_RUNNING=1"

REM BiblioForge - Setup and Run Script for Windows
echo.
echo ========================================
echo   BiblioForge - Setup e Avvio (Windows)
echo ========================================
echo.

REM Get current directory
echo Debug: Directory corrente: %CD%
echo Debug: Cartella script: %~dp0
echo.

REM Navigate to the script directory first
cd /d "%~dp0"
if errorlevel 1 (
    echo.
    echo [ERROR] Impossibile accedere alla cartella dello script
    echo Directory: %~dp0
    echo.
    pause
    exit /b 1
)
echo Debug: Navigato in: %CD%
echo.

REM Navigate to the BiblioForge project directory
cd ../BiblioForge
if errorlevel 1 (
    echo.
    echo [ERROR] Cartella BiblioForge non trovata!
    echo Ho cercato in: %CD%\..\BiblioForge
    echo.
    echo Verificate che:
    echo   1. Avete estratto il file ZIP completo
    echo   2. Siete nella cartella SETUP_WINDOWS
    echo   3. Sopra c'e' la cartella "BiblioForge"
    echo.
    pause
    exit /b 1
)

if not exist "main.py" (
    echo.
    echo [ERROR] File main.py non trovato in %CD%
    echo Verificate che lo ZIP sia stato estratto correttamente
    echo.
    pause
    exit /b 1
)

echo Debug: Navigato nella cartella del progetto: %CD%
echo.

REM Color codes for output
echo Ricerca di Python in corso...
echo.

REM Search for Python in common locations
set "PYTHON_FOUND="
set "PYTHON_PATH="

REM Try python in PATH first
python --version >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_FOUND=1"
    set "PYTHON_PATH=python"
    goto :found_python
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

REM Search in OneDrive/AppData variations (per Anaconda, Conda, ecc)
if not defined PYTHON_FOUND (
    for /d %%i in ("%UserProfile%\AppData\Local\*Python*") do (
        if exist "%%i\python.exe" (
            set "PYTHON_FOUND=1"
            set "PYTHON_PATH=%%i\python.exe"
            goto :found_python
        )
    )
)

REM Try to find Python via Windows Registry (check current user)
if not defined PYTHON_FOUND (
    for /f "tokens=2*" %%i in ('reg query "HKCU\Software\Python\PythonCore" 2^>nul ^| findstr /i "InstallPath"') do (
        if exist "%%j\python.exe" (
            set "PYTHON_FOUND=1"
            set "PYTHON_PATH=%%j\python.exe"
            goto :found_python
        )
    )
)

REM Try to find Python via Windows Registry (check local machine)
if not defined PYTHON_FOUND (
    for /f "tokens=2*" %%i in ('reg query "HKLM\Software\Python\PythonCore" 2^>nul ^| findstr /i "InstallPath"') do (
        if exist "%%j\python.exe" (
            set "PYTHON_FOUND=1"
            set "PYTHON_PATH=%%j\python.exe"
            goto :found_python
        )
    )
)

REM Try to find Python via Windows Registry (check 32-bit registry on 64-bit system)
if not defined PYTHON_FOUND (
    for /f "tokens=2*" %%i in ('reg query "HKLM\Software\Wow6432Node\Python\PythonCore" 2^>nul ^| findstr /i "InstallPath"') do (
        if exist "%%j\python.exe" (
            set "PYTHON_FOUND=1"
            set "PYTHON_PATH=%%j\python.exe"
            goto :found_python
        )
    )
)

:found_python
if not defined PYTHON_FOUND (
    echo [AVVISO] Python non trovato nel sistema
    echo.
    echo Posso scaricare e installare Python automaticamente per te.
    echo Vuoi che continui?
    echo.
    set /p DOWNLOAD_CHOICE="Digita 'S' per scaricare, oppure 'N' per fare altro: "
    
    if /i "!DOWNLOAD_CHOICE!"=="S" (
        echo.
        echo Scaricamento di Python 3.12 in corso...
        echo.
        
        REM Create temp folder
        set "TEMP_PYTHON=%TEMP%\python_installer"
        if not exist "!TEMP_PYTHON!" mkdir "!TEMP_PYTHON!"
        
        REM Download Python installer using PowerShell
        set "PYTHON_URL=https://www.python.org/ftp/python/3.12.3/python-3.12.3-amd64.exe"
        set "INSTALLER_PATH=!TEMP_PYTHON!\python-installer.exe"
        
        echo Percorso: !INSTALLER_PATH!
        echo URL: !PYTHON_URL!
        echo.
        
        REM Use PowerShell to download (available on all modern Windows)
        powershell -NoProfile -Command "try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; (New-Object Net.WebClient).DownloadFile('!PYTHON_URL!', '!INSTALLER_PATH!'); Write-Host 'Download completato'; exit 0 } catch { Write-Host 'Errore download: ' $_.Exception.Message; exit 1 }"
        
        if errorlevel 1 (
            echo.
            echo [ERROR] Scaricamento fallito
            echo.
            echo Scarica manualmente Python da: https://www.python.org/downloads/
            echo.
            pause
            goto :error_exit
        )
        
        if not exist "!INSTALLER_PATH!" (
            echo.
            echo [ERROR] File scaricato non trovato in: !INSTALLER_PATH!
            echo.
            pause
            goto :error_exit
        )
        
        echo.
        echo Installazione di Python in corso...
        echo Assicurati di completare l'installazione!
        echo.
        
        REM Run installer with parameters to add to PATH
        "!INSTALLER_PATH!" /quiet /PrependPath=1 InstallAllUsers=0
        
        echo.
        echo Attesa del completamento dell'installazione...
        timeout /t 30 /nobreak
        
        echo.
        echo Verifica se Python è stato installato...
        python --version >nul 2>&1
        if errorlevel 1 (
            echo.
            echo [ATTENZIONE] Python potrebbe non essere stato installato correttamente
            echo Riprovare aprendo nuovamente questo script
            echo.
            pause
            goto :error_exit
        )
        
        echo.
        echo Python installato con successo!
        echo Riavvio dello script...
        echo.
        
        REM Clean up installer
        if exist "!INSTALLER_PATH!" del "!INSTALLER_PATH!"
        
        REM Restart the script
        call "%~f0"
        exit /b %ERRORLEVEL%
        
    ) else (
        echo.
        echo [AVVISO] Python non trovato e installazione annullata
        echo.
        echo Opzioni:
        echo 1. Scarica Python da https://www.python.org/downloads/
        echo 2. Assicurati di spuntare "Add Python to PATH"
        echo 3. Riapri questo script
        echo.
        pause
        exit /b 1
    )
)

echo [1/4] Python trovato!
for /f "tokens=*" %%i in ('!PYTHON_PATH! --version') do set PYTHON_VERSION=%%i
echo        Versione: !PYTHON_VERSION!
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
