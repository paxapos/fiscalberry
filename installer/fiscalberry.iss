; Instalador de Fiscalberry para Windows (Inno Setup 6).
;
; Se instala por usuario, sin UAC, en %LOCALAPPDATA%\Programs\Fiscalberry, y
; deja a Fiscalberry arrancando con la sesión (oculto en la bandeja).
;
; Lo usan tanto la persona que lo descarga como el auto-updater de la GUI
; (src/fiscalberry/common/updater/installer.py), que lo corre en silencio con
; /RELAUNCH=1 para que, al terminar, Fiscalberry vuelva a abrirse.
;
; Este archivo tiene BOM UTF-8 a propósito: sin BOM, Inno Setup lo lee como
; ANSI y los acentos de los mensajes salen rotos.

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
UninstallDisplayName={#AppName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear un acceso directo en el escritorio"; GroupDescription: "Accesos directos:"; Flags: unchecked

; Las dependencias de PyInstaller (_internal) de la versión anterior se borran
; antes de copiar las nuevas: una DLL o un módulo que la versión nueva ya no
; trae, si queda ahí, puede cargarse en su lugar y romper el arranque.
[InstallDelete]
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\dist\fiscalberry-gui\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Fiscalberry"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\Fiscalberry"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

; La desinstalación borra esta clave pero NO el config.ini ni los logs (viven en
; %LOCALAPPDATA%\Fiscalberry, fuera de {app}): al reinstalar se reutiliza la
; vinculación con el comercio.
[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Fiscalberry"; ValueData: """{app}\{#AppExeName}"" --minimized"; Flags: uninsdeletevalue

[Run]
; Actualización silenciosa del auto-updater (/RELAUNCH=1): volver a abrir
; Fiscalberry, oculto en la bandeja. Sin skipifsilent: es justamente el caso
; silencioso el que tiene que relanzar.
Filename: "{app}\{#AppExeName}"; Parameters: "--minimized"; Flags: nowait; Check: DebeRelanzar
; Instalación hecha por una persona: ofrecer abrirlo al terminar.
Filename: "{app}\{#AppExeName}"; Description: "Abrir Fiscalberry"; Flags: nowait postinstall skipifsilent

[Code]
const
  { El mismo nombre que src/fiscalberry/common/single_instance.py: existe   }
  { mientras Fiscalberry esté abierto, y lo libera Windows al cerrarse.     }
  MutexFiscalberry = 'Local\FiscalberrySingleInstance';
  SegundosDeEspera = 60;

function FiscalberryAbierto(): Boolean;
begin
  Result := CheckForMutexes(MutexFiscalberry);
end;

function EsperarQueSeCierre(): Boolean;
var
  Vueltas: Integer;
begin
  Vueltas := 0;
  while FiscalberryAbierto() and (Vueltas < SegundosDeEspera * 2) do
  begin
    Sleep(500);
    Vueltas := Vueltas + 1;
  end;
  Result := not FiscalberryAbierto();
end;

{ Con Fiscalberry abierto no se pueden reemplazar sus archivos.             }
{ - En silencio (el auto-updater): Fiscalberry se está cerrando solo para   }
{   dejar instalar; se espera hasta SegundosDeEspera.                       }
{ - Con una persona delante: se le explica cómo cerrarlo, con Reintentar.   }
function PedirQueSeCierre(Silencioso: Boolean; Accion: String): Boolean;
begin
  Result := True;
  if not FiscalberryAbierto() then
    Exit;

  if Silencioso then
  begin
    Log('Fiscalberry sigue abierto: se espera hasta ' + IntToStr(SegundosDeEspera) + ' segundos a que se cierre.');
    Result := EsperarQueSeCierre();
    if Result then
      Log('Fiscalberry se cerró: se continúa con la ' + Accion + '.')
    else
      Log('Fiscalberry no se cerró a tiempo: se cancela la ' + Accion + '.');
    Exit;
  end;

  while FiscalberryAbierto() do
  begin
    if MsgBox('Fiscalberry está abierto y hay que cerrarlo para continuar con la ' + Accion + '.' + #13#10#13#10 +
              'Hacé clic derecho en el ícono de Fiscalberry, junto al reloj de Windows, elegí "Salir (deja de imprimir)" y después tocá Reintentar.',
              mbError, MB_RETRYCANCEL) = IDCANCEL then
    begin
      Result := False;
      Exit;
    end;
  end;
end;

function InitializeSetup(): Boolean;
begin
  Result := PedirQueSeCierre(WizardSilent(), 'instalación');
end;

function InitializeUninstall(): Boolean;
begin
  Result := PedirQueSeCierre(UninstallSilent(), 'desinstalación');
end;

function DebeRelanzar(): Boolean;
begin
  Result := ExpandConstant('{param:RELAUNCH|0}') = '1';
end;
