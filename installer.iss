; Inno Setup script for Zapret GUI.
; 1) Build the exe first (build.bat).
; 2) Compile this with Inno Setup (build_installer.bat or open in the Inno IDE).
; The installed app downloads zapret from Flowseal automatically on first launch,
; so the installer itself only needs to ship ZapretGUI.exe.

#define MyAppName "Zapret GUI"
; Version can be overridden from the command line (CI passes the git tag):
;   ISCC /DMyAppVersion=1.2.3 installer.iss
#ifndef MyAppVersion
#define MyAppVersion "1.0.0"
#endif
#define MyAppPublisher "Zapret GUI"
#define MyAppExeName "ZapretGUI.exe"

[Setup]
AppId={{B7F3B0E2-6E2A-4C9E-9E0A-3B2D5E7F1A10}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\ZapretGUI
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=Output
OutputBaseFilename=ZapretGUI-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=ui\assets\app.ico
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "autostart"; Description: "Запускать Zapret GUI вместе с Windows (свёрнуто в трей)"; Flags: unchecked

[Files]
Source: "dist\ZapretGUI.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "ZapretGUI"; ValueData: """{app}\{#MyAppExeName}"" --minimized"; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{localappdata}\ZapretGUI"
