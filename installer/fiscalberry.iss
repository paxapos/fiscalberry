; Instalador de Fiscalberry (GUI de Windows): por usuario, sin UAC.
; Lo compila .github/workflows/build-release.yml; ver docs/installer-windows.md.
; Archivo en UTF-8 con BOM: así lo lee bien cualquier Inno Setup 6.

#define AppName "Fiscalberry"
#define AppPublisher "PaxaPOS"
#define AppExeName "fiscalberry-gui.exe"
#define AppVersion GetFileVersion("..\dist\fiscalberry-gui\fiscalberry-gui.exe")
; El mismo nombre que crea la app (src/fiscalberry/common/single_instance.py):
; mientras exista, Fiscalberry está abierto y no se pueden pisar sus archivos.
#define AppMutex "Local\FiscalberrySingleInstance"

[Setup]
; No cambiar: el updater encuentra la instalación por este AppId
; (install_kind.INNO_APP_ID) y las actualizaciones pisan la anterior.
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

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear un acceso directo en el escritorio"; GroupDescription: "Accesos directos:"; Flags: unchecked

[InstallDelete]
; Cada versión trae su _internal completo. Sin esto quedarían librerías de la
; versión anterior mezcladas con las de la nueva.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\dist\fiscalberry-gui\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Fiscalberry"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\Fiscalberry"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Fiscalberry"; ValueData: """{app}\{#AppExeName}"" --minimized"; Flags: uninsdeletevalue

[Run]
; Actualización silenciosa pedida por el updater (/RELAUNCH=1): vuelve a abrir
; Fiscalberry en la bandeja. Sin skipifsilent a propósito.
Filename: "{app}\{#AppExeName}"; Parameters: "--minimized"; Flags: nowait; Check: DebeRelanzar
; Instalación a mano: casilla "Abrir Fiscalberry" al terminar.
Filename: "{app}\{#AppExeName}"; Description: "Abrir Fiscalberry"; Flags: nowait postinstall skipifsilent

; config.ini y los logs viven en %LOCALAPPDATA%\Fiscalberry, fuera de {app}:
; desinstalar no los toca, y al reinstalar se reutiliza la vinculación.

[Code]
const
  EsperaSilenciosaSeg = 60;

function FiscalberryAbierto(): Boolean;
begin
  Result := CheckForMutexes('{#AppMutex}');
end;

{ Espera hasta Segundos a que Fiscalberry termine de cerrarse. }
function EsperarCierre(Segundos: Integer): Boolean;
var
  Intentos: Integer;
begin
  Intentos := Segundos * 2;
  while FiscalberryAbierto() and (Intentos > 0) do
  begin
    Sleep(500);
    Intentos := Intentos - 1;
  end;
  Result := not FiscalberryAbierto();
end;

{ Nunca se pisan los archivos de un Fiscalberry abierto: su servicio de
  impresión vive en ese proceso. }
function PuedeSeguir(Silencioso: Boolean; const Accion: String): Boolean;
begin
  if Silencioso then
  begin
    { El updater lanza el setup y cierra la app enseguida: solo hay que
      esperar a que termine de cerrarse. }
    Result := EsperarCierre(EsperaSilenciosaSeg);
    if not Result then
      Log('Fiscalberry sigue abierto después de ' + IntToStr(EsperaSilenciosaSeg) +
          ' s: se cancela.');
    exit;
  end;

  { A mano: puede que se esté cerrando (tarda unos segundos en detener el
    servicio), así que primero se espera un poco antes de preguntar. }
  Result := EsperarCierre(3);
  while not Result do
  begin
    if MsgBox('Fiscalberry está abierto.' + #13#10#13#10 +
              'Cerralo desde su ícono junto al reloj (clic derecho, "Salir") ' +
              'y tocá Reintentar para ' + Accion + '.',
              mbInformation, MB_RETRYCANCEL) = IDCANCEL then
      exit;
    Result := EsperarCierre(10);
  end;
end;

function InitializeSetup(): Boolean;
begin
  Result := PuedeSeguir(WizardSilent(), 'continuar con la instalación');
end;

function InitializeUninstall(): Boolean;
begin
  Result := PuedeSeguir(UninstallSilent(), 'desinstalarlo');
end;

{ /RELAUNCH=1 lo pasa el updater: solo en ese caso se reabre la app sola. }
function DebeRelanzar(): Boolean;
begin
  Result := ExpandConstant('{param:RELAUNCH|0}') = '1';
end;
