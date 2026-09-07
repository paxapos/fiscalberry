#define AppName "Fiscalberry"
#define AppPublisher "PaxaPOS"
#define AppExeName "fiscalberry-gui.exe"
#define AppVersion GetFileVersion("..\dist\fiscalberry-gui\fiscalberry-gui.exe")

[Setup]
AppId={{55BB025A-ED36-4DB6-A2A3-706DD36AB936}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={localappdata}\Programs\Fiscalberry
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=FiscalberrySetup
SetupIconFile=..\src\fiscalberry\ui\assets\fiscalberry.ico
UninstallDisplayIcon={app}\{#AppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no

[Tasks]
Name: "desktopicon"; Description: "Crear un acceso directo en el escritorio"; GroupDescription: "Accesos directos:"; Flags: unchecked

[Files]
Source: "..\dist\fiscalberry-gui\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Fiscalberry"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\Fiscalberry"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Fiscalberry"; ValueData: """{app}\{#AppExeName}"" --minimized"; Flags: uninsdeletevalue

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Abrir Fiscalberry"; Flags: nowait postinstall skipifsilent