; Inno Setup script for eter (Windows installer).
; Build:  ISCC /DMyAppVersion=0.2.0 packaging\eter.iss
; Expects the PyInstaller onedir output in dist\eter\ (contains eter.exe).

#define MyAppName "eter"
#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif
#define MyAppExeName "eter.exe"
#define MyAppPublisher "gdarko"
#define MyAppURL "https://github.com/gdarko/eter"

[Setup]
; Keep AppId stable across versions so upgrades replace in place.
AppId={{9B1F4C7A-2E63-4D18-A5C9-0D7E3F6B8A24}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
; Per-user install, no admin/UAC prompt.
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=eter-Setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked
Name: "startupicon"; Description: "Launch eter at login"; GroupDescription: "Startup:"

[Files]
Source: "..\dist\eter\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{userstartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: startupicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch eter"; Flags: nowait postinstall skipifsilent
