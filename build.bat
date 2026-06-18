@echo off
REM ============================================================
REM  Build a single-file ZapretGUI.exe with PyInstaller.
REM  Just double-click this file. It will report any error.
REM ============================================================
setlocal
cd /d "%~dp0"

echo ============================================
echo  Building ZapretGUI.exe
echo ============================================
echo.

REM --- 1. Find a working Python (python or py launcher) ---
set "PY="
python --version >nul 2>&1 && set "PY=python"
if not defined PY (
    py --version >nul 2>&1 && set "PY=py"
)
if not defined PY (
    echo [ERROR] Python not found.
    echo Install Python from https://www.python.org/downloads/
    echo and TICK "Add Python to PATH" during setup, then reopen this file.
    echo.
    pause
    exit /b 1
)
echo Using Python: %PY%
%PY% --version
echo.

REM --- 2. Install dependencies ---
echo Installing dependencies...
%PY% -m pip install --upgrade pip
%PY% -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies from requirements.txt
    pause
    exit /b 1
)
%PY% -m pip install pyinstaller
if errorlevel 1 (
    echo [ERROR] Failed to install PyInstaller.
    pause
    exit /b 1
)
echo.

REM --- 2b. Download the full zapret bundle to embed into the exe ---
echo Preparing embedded zapret bundle (downloads once)...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0fetch_zapret.ps1"
if errorlevel 1 (
    echo [ERROR] Could not download the zapret bundle to embed.
    echo The first build needs internet access. Check your connection and retry.
    pause
    exit /b 1
)
if not exist "vendor\zapret\bin\winws.exe" (
    echo [ERROR] zapret bundle is missing after download.
    echo Expected vendor\zapret\bin\winws.exe but it was not found.
    echo Check your internet connection / antivirus and run build.bat again.
    pause
    exit /b 1
)
echo zapret bundle is ready and will be embedded into the exe:
dir /b "vendor\zapret\*.bat" 2>nul | find /c ".bat" >nul && (
    for /f %%C in ('dir /b "vendor\zapret\*.bat" 2^>nul ^| find /c ".bat"') do echo   embedded strategy .bat files: %%C
)
echo.

REM --- 3. Build (use python -m so PATH does not matter) ---
echo Building exe...
%PY% -m PyInstaller zapret-gui.spec --noconfirm
if errorlevel 1 (
    echo [ERROR] Build failed. Read the messages above.
    pause
    exit /b 1
)

echo.
echo ============================================
echo  DONE! Result: dist\ZapretGUI.exe
echo ============================================
pause
