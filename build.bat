@echo off
REM ============================================================
REM  Build a single-file ZapretGUI.exe with PyInstaller.
REM  Just double-click this file. It will report any error.
REM
REM  When called from build_installer.bat, pass the /nopause flag
REM  to skip the "Press any key" prompts so the installer build
REM  can continue automatically:
REM      call build.bat /nopause
REM ============================================================
setlocal

cd /d "%~dp0"

REM Parse the /nopause flag — when set, we never call pause, so the
REM script can be chained from build_installer.bat without blocking.
set "NOPAUSE="
if /i "%~1"=="/nopause" set "NOPAUSE=1"
if /i "%~1"=="--nopause" set "NOPAUSE=1"

REM Helper: pause only in interactive mode (not when /nopause was passed).
goto :after_pause_helper
:smart_pause
if not defined NOPAUSE pause
goto :eof
:after_pause_helper

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
    call :smart_pause
    exit /b 1
)
echo Using Python: %PY%
%PY% --version
echo.

REM --- 2. Install dependencies ---
echo Installing dependencies...
%PY% -m pip install --upgrade pip
if errorlevel 1 (
    echo [WARN] pip upgrade failed, continuing with the existing version...
)
%PY% -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies from requirements.txt
    call :smart_pause
    exit /b 1
)
%PY% -m pip install "pyinstaller>=6.0"
if errorlevel 1 (
    echo [ERROR] Failed to install PyInstaller.
    call :smart_pause
    exit /b 1
)
echo.

REM --- 2b. Download the full zapret bundle to embed into the exe ---
echo Preparing embedded zapret bundle (downloads once)...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0fetch_zapret.ps1"
if errorlevel 1 (
    echo [ERROR] Could not download the zapret bundle to embed.
    echo The first build needs internet access. Check your connection and retry.
    call :smart_pause
    exit /b 1
)
if not exist "vendor\zapret\bin\winws.exe" (
    echo [ERROR] zapret bundle is missing after download.
    echo Expected vendor\zapret\bin\winws.exe but it was not found.
    echo Check your internet connection / antivirus and run build.bat again.
    call :smart_pause
    exit /b 1
)
echo zapret bundle is ready and will be embedded into the exe.
echo.

REM --- 3. Build (use python -m so PATH does not matter) ---
echo Building exe...
REM Remove stale artifacts first. Otherwise build_installer.bat could package
REM an old dist\ZapretGUI.exe after a failed build.
if exist "dist\ZapretGUI.exe" del /f /q "dist\ZapretGUI.exe" >nul 2>&1
if exist "build" rmdir /s /q "build" >nul 2>&1
%PY% -m PyInstaller zapret-gui.spec --noconfirm
if errorlevel 1 (
    echo [ERROR] PyInstaller build failed. Read the messages above.
    call :smart_pause
    exit /b 1
)
if not exist "dist\ZapretGUI.exe" (
    echo [ERROR] PyInstaller finished but dist\ZapretGUI.exe was not created.
    call :smart_pause
    exit /b 1
)

echo.
echo ============================================
echo  DONE! Result: dist\ZapretGUI.exe
echo ============================================
call :smart_pause
endlocal
exit /b 0
