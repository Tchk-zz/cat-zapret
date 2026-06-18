@echo off
REM ============================================================
REM  Build ZapretGUI.exe and wrap it into ZapretGUI-Setup.exe
REM  using Inno Setup. Just double-click this file.
REM ============================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo === Step 1/2: building ZapretGUI.exe ===
call build.bat
if not exist "dist\ZapretGUI.exe" (
    echo [ERROR] dist\ZapretGUI.exe was not built. See the messages above.
    pause
    exit /b 1
)

echo.
echo === Step 2/2: building the installer ===
set "ISCC="
where iscc >nul 2>&1 && set "ISCC=iscc"
if not defined ISCC if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC (
    echo [ERROR] Inno Setup not found.
    echo Install it from https://jrsoftware.org/isdl.php and run this file again.
    pause
    exit /b 1
)

"!ISCC!" installer.iss
if errorlevel 1 (
    echo [ERROR] Installer build failed. See the messages above.
    pause
    exit /b 1
)

echo.
echo ============================================
echo  DONE! Result: Output\ZapretGUI-Setup.exe
echo ============================================
pause
