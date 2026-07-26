; Inno Setup script for Zapret GUI.
; 1) Build the exe first (build.bat).
; 2) Compile this with Inno Setup (build_installer.bat or open in the Inno IDE).
; ZapretGUI.exe is built by build.bat and already contains the embedded zapret bundle.
; The installer ships that freshly built exe and does not package stale dist files.

#define MyAppName "Zapret GUI"
; Version can be overridden from the command line:
;   ISCC /DMyAppVersion=1.2.3 installer.iss
;
; build_installer.bat ALWAYS passes /DMyAppVersion=<value from VERSION file>
; before invoking ISCC, so the installer version and the in-app version
; always agree. The app reads the very same VERSION file at runtime
; (app/__init__.py -> _read_version()), and it is shipped next to the exe in
; the [Files] section below.
;
; If somebody compiles installer.iss manually without that flag, fall back
; to "1.0.0" so the script still compiles. We deliberately do NOT try to
; read the VERSION file from inside ISPP — the obvious approaches
; (ReadIni on a non-INI file, GetFileVersion on a not-yet-built exe) are
; either unreliable or require the exe to already exist. Passing the value
; from the .bat is simpler and uses only documented ISPP behaviour.
#ifndef MyAppVersion
  #define MyAppVersion "1.0.0"
#endif
#define MyAppPublisher "Zapret GUI"
#define MyAppExeName "ZapretGUI.exe"
; Path to the freshly built exe that gets packaged. Normally build.bat puts it
; in dist\, but the running app locks that file, so a build can be redirected:
;   pyinstaller zapret-gui.spec --distpath dist_release
;   ISCC /DMyAppExeSource="dist_release\ZapretGUI.exe" installer.iss
#ifndef MyAppExeSource
  #define MyAppExeSource "dist\ZapretGUI.exe"
#endif

[Setup]
AppId={{B7F3B0E2-6E2A-4C9E-9E0A-3B2D5E7F1A10}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\ZapretGUI
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
; OutputDir is relative to the .iss file location. Use the literal "Output"
; folder name so the setup exe lands at <project>\Output\ZapretGUI-Setup.exe.
OutputDir=Output
OutputBaseFilename=ZapretGUI-Setup
; LZMA2 with solid compression gives the smallest installer. We disable the
; separate-process LZMA encoder because on some machines (especially with
; aggressive antivirus) it fails silently and the setup exe is never produced.
Compression=lzma2
SolidCompression=yes
LZMAUseSeparateProcess=no
WizardStyle=modern
SetupIconFile=ui\assets\app.ico
; UninstallDisplayIcon is required so the installer doesn't warn about a
; missing icon in Add/Remove Programs.
UninstallDisplayIcon={app}\{#MyAppExeName}
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64
; We close the running GUI ourselves in [Code]. Inno's Restart Manager prompt
; could not reliably close the tray/elevated process and allowed users to
; continue with the old ZapretGUI.exe still locked, leaving an old version installed.
CloseApplications=no
RestartApplications=no

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "autostart"; Description: "Запускать Zapret GUI вместе с Windows (свёрнуто в трей, без UAC)"; Flags: unchecked

[InstallDelete]
; If a previous install left an old exe behind, remove it after our pre-install
; close step and before the new file is copied.
Type: files; Name: "{app}\{#MyAppExeName}"

[Files]
Source: "{#MyAppExeSource}"; DestDir: "{app}"; DestName: "{#MyAppExeName}"; Flags: ignoreversion
; VERSION — REQUIRED next to the exe. app.self_updater.local_version() reads
; this file to know which version is installed. Without it local_version()
; returns "" and the self-updater offers the same update over and over again,
; because an empty local version can never compare as up-to-date.
Source: "VERSION"; DestDir: "{app}"; Flags: ignoreversion
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
; roblox_profile.json — installed next to the exe so advanced users can edit
; the Roblox bypass IP ranges WITHOUT rebuilding. Loaded at runtime by
; app.bootstrap.load_roblox_profile(). The bundled copy inside the exe is
; only a fallback; this external copy takes priority once installed.
Source: "roblox_profile.json"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

; Old versions registered autostart via the HKCU Run key, which triggered a
; UAC prompt at EVERY logon (the exe requires admin for WinDivert). We now use
; a Task Scheduler entry with /RL HIGHEST instead — it runs elevated with NO
; UAC prompt at logon. The old Run-key value is cleaned up here too.
[Run]
; Launch the app after install (optional, postinstall checkbox).
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent; Check: NotWizardSilent

[Code]
// Inno Setup's [Run] section quoting is fragile for complex commands like
// schtasks /TR with embedded quotes. We do the schtasks + reg-delete + kill
// via Pascal Script's Exec() instead — string handling is much more
// predictable here than in the .iss Parameters column.

procedure KillProcessByName(FileName: String);
var
  ResultCode: Integer;
begin
  { /F is intentional: ZapretGUI can live in the tray/elevated state and Inno's
    automatic close step may not terminate it. If it remains running, Windows
    keeps the installed exe locked and the installer leaves the old version.

    /T IS DELIBERATELY ABSENT. When the update is started from inside the app,
    ZapretGUI spawns this very Setup process, so Setup is a CHILD of
    ZapretGUI.exe. Measured: `taskkill /F /PID <parent> /T` also kills a child
    created with DETACHED_PROCESS -- DETACHED_PROCESS only detaches the
    console, not the parent/child link. With /T the installer therefore killed
    ITSELF right after the user pressed "Install": the app closed, setup died
    mid-way and the old version stayed installed. Killing by image name without
    /T terminates every ZapretGUI.exe instance and leaves Setup alive. }
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM ' + FileName, '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  { Give Windows a moment to release file handles (WinDivert driver unload,
    antivirus inspection of the dying process, etc.). Without this pause the
    next [InstallDelete]/[Files] step can race the handle cleanup and fail
    with "file in use". }
  Sleep(700);
end;

function InitializeSetup(): Boolean;
begin
  { Do NOT kill the running app here. InitializeSetup runs before the wizard is
    shown, so the user's app was being closed even if they cancelled the setup
    on the very first page. The running app is closed later, in CurStepChanged
    at ssInstall -- i.e. only after the user confirmed the installation. }
  Result := True;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
  TaskCmd: String;
  ExePath: String;
begin
  if CurStep = ssInstall then
  begin
    { Safety retry immediately before [InstallDelete]/[Files]. }
    KillProcessByName('{#MyAppExeName}');
  end;
  if CurStep = ssPostInstall then
  begin
    { Create the autostart scheduled task AFTER the files are installed.
      Using [Code] + Exec avoids the .iss Parameters-quoting nightmare that
      previously caused "Mismatched or misplaced quotes on parameter Parameters"
      at the [Run] section line. Only run if the user ticked the autostart
      task on the Additional Tasks page. }
    if WizardIsTaskSelected('autostart') then
    begin
      ExePath := ExpandConstant('{app}\{#MyAppExeName}');
      // Build the schtasks command. /TR must receive a single argument
      // containing: "<exe path>" --minimized. Because Exec() calls
      // schtasks.exe directly (no cmd.exe layer), escaped quotes are the most
      // reliable way to keep Program Files paths valid.
      TaskCmd := '/Create /TN ZapretGUI_Autostart /TR "\"' + ExePath + '\" --minimized" /SC ONLOGON /RL HIGHEST /F';
      Exec(ExpandConstant('{sys}\schtasks.exe'), TaskCmd, '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
      if ResultCode <> 0 then
      begin
        MsgBox('Не удалось создать задачу автозапуска ZapretGUI. Код ошибки: ' + IntToStr(ResultCode), mbError, MB_OK);
      end;
      // Best-effort cleanup of the legacy Run-key autostart from older installs.
      Exec(ExpandConstant('{sys}\reg.exe'), 'delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v ZapretGUI /f', '', SW_HIDE, ewNoWait, ResultCode);
    end;
  end;
end;

function NotWizardSilent(): Boolean;
begin
  Result := not WizardSilent();
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    { Settings live in %LOCALAPPDATA%\ZapretGUI (app/config.py). The log file
      folder (logs\zapret-gui.log, app/applog.py) and the crash log live in
      the same folder, so removing this tree cleans those up too. Ask first --
      deleting the user's strategies/config silently is never acceptable. }
    DataDir := ExpandConstant('{localappdata}\ZapretGUI');
    if DirExists(DataDir) then
    begin
      if MsgBox('Удалить также настройки Zapret GUI (выбранная стратегия, тема, secret Telegram-прокси)?' + #13#10 + #13#10 +
                DataDir + #13#10 + #13#10 +
                'Нажмите "Нет", если планируете установить программу заново.',
                mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
      begin
        DelTree(DataDir, True, True, True);
      end;
    end;
  end;
end;

[UninstallRun]
; Remove the scheduled task on uninstall.
Filename: "schtasks.exe"; Parameters: "/Delete /TN ZapretGUI_Autostart /F"; Flags: runhidden

; Per-user data (config.json, tg-ws-proxy engine state) lives in
; %LOCALAPPDATA%\ZapretGUI -- see app/config.py default_data_dir(), which uses
; the LOCALAPPDATA environment variable. The old [UninstallDelete] entry used
; {autoappdata} (= roaming AppData), so it silently deleted nothing and left
; the real settings folder behind forever. It also deleted user data without
; asking. Both problems are fixed in CurUninstallStepChanged below.

