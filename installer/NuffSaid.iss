; NuffSaid installer (Inno Setup 6). Build: ISCC.exe installer\NuffSaid.iss  ->  release-installer\NuffSaid-Setup.exe
; Per-user install, no admin prompt. The speech model and the optional NVIDIA boost download on first run (first_run.py).
#define AppVersion "1.0.0"

[Setup]
AppId={{6E1C9C55-4E0B-4E4E-9B1E-5A2D3F7C1A01}
AppName=NuffSaid
AppVersion={#AppVersion}
AppVerName=NuffSaid {#AppVersion}
AppPublisher=Sachin
AppPublisherURL=https://nuffsaid.pages.dev
AppSupportURL=https://github.com/sachikaindra/nuffsaid
AppUpdatesURL=https://github.com/sachikaindra/nuffsaid/releases
DefaultDirName={localappdata}\Programs\NuffSaid
DefaultGroupName=NuffSaid
DisableProgramGroupPage=yes
DisableDirPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\release-installer
OutputBaseFilename=NuffSaid-Setup
SetupIconFile=..\assets\nuffsaid.ico
UninstallDisplayIcon={app}\NuffSaid.exe
UninstallDisplayName=NuffSaid
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
LicenseFile=..\LICENSE.txt
CloseApplications=yes

[Tasks]
Name: "desktopicon"; Description: "Add a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked
Name: "startup"; Description: "Start NuffSaid with Windows"; GroupDescription: "Startup:"

[Files]
Source: "..\release-build\NuffSaid\NuffSaid.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\release-build\NuffSaid\_internal\*"; DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs
; Keep the user's settings on updates.
Source: "..\release-build\NuffSaid\config.yaml"; DestDir: "{app}"; Flags: onlyifdoesntexist uninsneveruninstall

[Icons]
Name: "{group}\NuffSaid"; Filename: "{app}\NuffSaid.exe"
Name: "{group}\Uninstall NuffSaid"; Filename: "{uninstallexe}"
Name: "{userdesktop}\NuffSaid"; Filename: "{app}\NuffSaid.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "NuffSaid"; ValueData: """{app}\NuffSaid.exe"""; Flags: uninsdeletevalue; Tasks: startup

[Run]
Filename: "{app}\NuffSaid.exe"; Description: "Open NuffSaid"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{cmd}"; Parameters: "/C taskkill /IM NuffSaid.exe /F"; Flags: runhidden; RunOnceId: "StopNuffSaid"
