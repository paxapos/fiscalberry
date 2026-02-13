; Fiscalberry Inno Setup Script
; Este script crea un instalador profesional de Windows para Fiscalberry

#define MyAppName "Fiscalberry"
#define MyAppVersion "3.0.0"
#define MyAppPublisher "PaxaPos"
#define MyAppURL "https://github.com/paxapos/fiscalberry"
#define MyAppExeName "fiscalberry-gui.exe"
#define MyAppExeNameCLI "fiscalberry-cli.exe"

[Setup]
; Información básica de la aplicación
AppId={{8B9CAD0E-1F20-4192-BFF0-E1E043CEA4DB}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
LicenseFile=LICENSE
InfoBeforeFile=README.md
; Icono del instalador
SetupIconFile=src\fiscalberry\ui\assets\fiscalberry.ico
; Configuración de compresión
Compression=lzma2/max
SolidCompression=yes
; Configuración de Windows
WizardStyle=modern
PrivilegesRequired=lowest
; Archivos de salida
OutputDir=installer
OutputBaseFilename=fiscalberry-{#MyAppVersion}-setup
; Arquitectura
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Desinstalador
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "quicklaunchicon"; Description: "{cm:CreateQuickLaunchIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked; OnlyBelowVersion: 6.1; Check: not IsAdminInstallMode

[Files]
; Ejecutable GUI y todas sus dependencias
Source: "dist\fiscalberry-gui.exe"; DestDir: "{app}"; Flags: ignoreversion
; Ejecutable CLI
Source: "dist\fiscalberry-cli.exe"; DestDir: "{app}"; Flags: ignoreversion
; Archivos de configuración y documentación
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "config.ini.example"; DestDir: "{app}"; Flags: ignoreversion; AfterInstall: CreateConfigIfNotExists
; NOTA: Si PyInstaller genera carpetas en lugar de .exe únicos, usa:
; Source: "dist\fiscalberry-gui\*"; DestDir: "{app}\gui"; Flags: ignoreversion recursesubdirs createallsubdirs
; Source: "dist\fiscalberry-cli\*"; DestDir: "{app}\cli"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; Menú Inicio - GUI
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
; Menú Inicio - CLI
Name: "{group}\{#MyAppName} CLI"; Filename: "{app}\{#MyAppExeNameCLI}"
; Menú Inicio - Desinstalador
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
; Escritorio (opcional)
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
; Barra de tareas (opcional, solo Windows 7)
Name: "{userappdata}\Microsoft\Internet Explorer\Quick Launch\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: quicklaunchicon

[Run]
; Opción para ejecutar la aplicación al finalizar la instalación
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Code]
// Función para crear config.ini si no existe
procedure CreateConfigIfNotExists();
var
  ConfigPath: String;
begin
  ConfigPath := ExpandConstant('{app}\config.ini');
  if not FileExists(ConfigPath) then
  begin
    FileCopy(ExpandConstant('{app}\config.ini.example'), ConfigPath, False);
  end;
end;

// Función para detectar si hay una versión anterior instalada
function InitializeSetup(): Boolean;
var
  OldVersion: String;
begin
  Result := True;
  if RegQueryStringValue(HKLM, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{8B9CAD0E-1F20-4192-BFF0-E1E043CEA4DB}_is1', 'DisplayVersion', OldVersion) then
  begin
    if MsgBox('Se detectó una versión anterior de Fiscalberry (' + OldVersion + '). ¿Desea continuar con la instalación?', mbConfirmation, MB_YESNO) = IDNO then
      Result := False;
  end;
end;
