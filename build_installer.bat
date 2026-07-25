@echo off
REM ============================================================
REM  Build ZapretGUI.exe and wrap it into ZapretGUI-Setup.exe
REM  using Inno Setup. Just double-click this file.
REM ============================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ============================================================
echo  Building ZapretGUI-Setup.exe (installer)
echo ============================================================
echo.

echo === Step 1/2: building ZapretGUI.exe ===
REM Call build.bat with /nopause so it doesn't block waiting for a keypress.
call build.bat /nopause
set "BUILD_RC=%errorlevel%"
if not "%BUILD_RC%"=="0" (
    echo.
    echo [ERROR] Build step failed with exit code %BUILD_RC%.
    echo Installer will not be created from a stale exe.
    echo.
    pause
    exit /b 1
)
if not exist "dist\ZapretGUI.exe" (
    echo.
    echo [ERROR] Build step reported success but dist\ZapretGUI.exe is missing.
    echo This should never happen — check the build output above.
    echo.
    pause
    exit /b 1
)
echo.
echo Build OK: dist\ZapretGUI.exe is ready.
echo.

echo === Step 2/2: building the installer ===
if exist "Output\ZapretGUI-Setup.exe" del /f /q "Output\ZapretGUI-Setup.exe" >nul 2>&1

REM Make sure the Output directory exists (Inno creates it, but we create it
REM here too so the final check for the exe doesn't fail on a missing folder).
if not exist "Output" mkdir "Output" 2>nul

REM --- Find ISCC.exe (Inno Setup Compiler) ---
REM We resolve %ProgramFiles(x86)% OUTSIDE the IF block because the
REM parentheses in "(x86)" break the IF parser when combined with
REM enabledelayedexpansion. This is a well-known batch scripting gotcha.
set "ISCC="
where iscc >nul 2>&1 && set "ISCC=iscc"

if not defined ISCC (
    REM Cache the Program Files paths in temp vars (no parens in the var name).
    set "PF86=%ProgramFiles(x86)%"
    set "PF64=%ProgramFiles%"

    REM Check 64-bit Program Files first (some installs land here).
    if exist "!PF64!\Inno Setup 6\ISCC.exe" set "ISCC=!PF64!\Inno Setup 6\ISCC.exe"

    REM Then 32-bit Program Files (x86) — the default install location.
    if not defined ISCC if exist "!PF86!\Inno Setup 6\ISCC.exe" set "ISCC=!PF86!\Inno Setup 6\ISCC.exe"

    REM Also check common alternative paths (Inno Setup 5, custom install dirs).
    if not defined ISCC if exist "!PF86!\Inno Setup 5\ISCC.exe" set "ISCC=!PF86!\Inno Setup 5\ISCC.exe"
    if not defined ISCC if exist "!PF64!\Inno Setup 5\ISCC.exe" set "ISCC=!PF64!\Inno Setup 5\ISCC.exe"
)

if not defined ISCC (
    echo.
    echo [ERROR] Inno Setup ^(ISCC.exe^) not found on this machine.
    echo.
    echo Install Inno Setup 6 from: https://jrsoftware.org/isdl.php
    echo Then run this script again.
    echo.
    echo If you already installed it to a custom folder, add that folder to
    echo your PATH environment variable, or edit this script to point at
    echo the ISCC.exe location directly.
    echo.
    echo Looked in:
    echo   - PATH ^(where iscc^)
    echo   - !PF64!\Inno Setup 6\ISCC.exe
    echo   - !PF86!\Inno Setup 6\ISCC.exe
    echo   - !PF86!\Inno Setup 5\ISCC.exe
    echo   - !PF64!\Inno Setup 5\ISCC.exe
    echo.
    pause
    exit /b 1
)

echo Using Inno Setup: !ISCC!
echo.

REM --- Read the app version from VERSION file ---
REM The VERSION file is a single line like "1.7.3". We pass it to ISCC as
REM /DMyAppVersion=<value> so installer.iss and the in-app version always
REM agree. We use a FOR /F loop with delims= that strips CR/LF/whitespace.
REM
REM Why we do this here (and NOT inside installer.iss via ISPP): ISPP has a
REM very limited function set (ReadIni, ReadReg, GetFileVersion...). It
REM cannot reliably read a plain-text file. Reading from the .bat is the
REM standard documented Inno Setup pattern.
set "APP_VERSION=1.0.0"
if exist "VERSION" (
    for /f "usebackq tokens=* delims=" %%V in ("VERSION") do (
        set "APP_VERSION=%%V"
    )
)
REM Strip any surrounding whitespace cmd may have left.
for /f "tokens=* delims= " %%W in ("!APP_VERSION!") do set "APP_VERSION=%%W"
REM Validate the version before passing it to the Inno preprocessor. This
REM prevents a malformed VERSION file from breaking the ISCC command line.
echo(!APP_VERSION!| findstr /r "^[0-9][0-9]*\.[0-9][0-9]*\.[0-9][0-9]*$" >nul
if errorlevel 1 (
    echo [ERROR] VERSION must be in N.N.N format, got: !APP_VERSION!
    echo Example: 1.7.3
    echo.
    pause
    exit /b 1
)
echo Using app version from VERSION file: !APP_VERSION!
echo.

REM --- Compile the installer ---
REM We pass /Qp so ISCC prints a single progress line per file (quieter than
REM the default, but still shows errors). /O overrides OutputDir just in case.
REM /DMyAppVersion=!APP_VERSION! passes the version into the ISPP preprocessor
REM so installer.iss uses it for AppVersion and the OutputBaseFilename.
"!ISCC!" /Qp /DMyAppVersion="!APP_VERSION!" installer.iss
set "ISCC_RC=%errorlevel%"
if not "%ISCC_RC%"=="0" (
    echo.
    echo [ERROR] Inno Setup compilation failed with exit code %ISCC_RC%.
    echo.
    echo Re-running ISCC without /Qp to show full output:
    echo.
    "!ISCC!" /DMyAppVersion="!APP_VERSION!" installer.iss
    echo.
    echo Common causes:
    echo   - dist\ZapretGUI.exe is missing or locked by another process.
    echo   - ui\assets\app.ico is missing.
    echo   - Syntax error in installer.iss.
    echo.
    pause
    exit /b 1
)

if not exist "Output\ZapretGUI-Setup.exe" (
    echo.
    echo [ERROR] Inno Setup reported success ^(exit code 0^) but
    echo Output\ZapretGUI-Setup.exe was not created.
    echo.
    echo This is unusual — re-running ISCC with full output:
    echo.
    "!ISCC!" /DMyAppVersion="!APP_VERSION!" installer.iss
    echo.
    echo Check the output above for warnings. If the file was created in a
    echo different folder, look for *.exe in the project:
    dir /s /b *.exe 2>nul | findstr /i "Setup"
    echo.
    pause
    exit /b 1
)

echo.
echo ============================================
echo  DONE! Result: Output\ZapretGUI-Setup.exe
echo ============================================
echo.
echo You can distribute this installer to users.
echo It will install ZapretGUI to Program Files and optionally
echo set up autostart via Windows Task Scheduler (no UAC prompt).
echo.
pause
endlocal
exit /b 0
