<#
Prueba de punta a punta de FiscalberrySetup.exe (#187). La corre la CI en
Windows, sobre un runner limpio:

  1. Instalación silenciosa por usuario: quedan el ejecutable y unins000.exe.
  2. El binario instalado pasa --selftest y "Aplicaciones" muestra su versión.
     Su --discovery-report lee de verdad las APIs de Windows que usa el
     asistente de impresoras (adaptadores de red, ARP) sin reventar.
  3. Actualización silenciosa con Fiscalberry "abierto" (su mutex existe): el
     setup espera a que se cierre, instala, conserva el desinstalador y, por
     /RELAUNCH=1, vuelve a abrir la app con --minimized. Nunca dos procesos.
  4. Desinstalación: se va la app y el arranque con Windows, pero config.ini
     (la vinculación del comercio) queda para una reinstalación.

Uso: .\build_tools\test-windows-installer.ps1 [-Setup dist\FiscalberrySetup.exe]
#>
param(
    [string]$Setup = "dist\FiscalberrySetup.exe"
)

$ErrorActionPreference = "Stop"

$setupPath = (Resolve-Path $Setup).Path
$installDir = Join-Path $env:LOCALAPPDATA "Programs\Fiscalberry"
$exe = Join-Path $installDir "fiscalberry-gui.exe"
$uninstaller = Join-Path $installDir "unins000.exe"
$configIni = Join-Path $env:LOCALAPPDATA "Fiscalberry\Fiscalberry\config.ini"
$appLog = Join-Path $env:LOCALAPPDATA "Fiscalberry\Fiscalberry\logs\fiscalberry.log"
# Mismos valores que installer/fiscalberry.iss y single_instance.py.
$uninstallKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\{55BB025A-ED36-4DB6-A2A3-706DD36AB936}_is1"
$runKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
$mutexName = "Local\FiscalberrySingleInstance"

$tmp = if ($env:RUNNER_TEMP) { $env:RUNNER_TEMP } else { $env:TEMP }
$logs = Join-Path $tmp "fiscalberry-installer-test"
New-Item -ItemType Directory -Force -Path $logs | Out-Null

function Start-Setup([string[]]$Arguments) {
    $proc = Start-Process -FilePath $setupPath -ArgumentList $Arguments -PassThru
    # Sin tocar el Handle antes de que termine, ExitCode puede quedar vacío.
    $null = $proc.Handle
    return $proc
}

function Wait-Exit($Proc, [int]$Seconds, [string]$What) {
    if (-not $Proc.WaitForExit($Seconds * 1000)) {
        throw "$What no terminó en $Seconds s"
    }
    if ($Proc.ExitCode -ne 0) {
        throw "$What terminó con código $($Proc.ExitCode)"
    }
}

function Wait-Until([scriptblock]$Condition, [int]$Seconds, [string]$Failure) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    while (-not (& $Condition)) {
        if ((Get-Date) -gt $deadline) { throw $Failure }
        Start-Sleep -Milliseconds 500
    }
}

# Ante una falla: lo que dejó Fiscalberry en su log, en la salida del job y
# entre los artefactos.
function Show-AppLog {
    if (Test-Path $appLog) {
        Copy-Item $appLog (Join-Path $logs "fiscalberry.log") -Force
        Write-Host "--- final de $appLog"
        Get-Content $appLog -Tail 60 | Write-Host
    } else {
        Write-Host "--- no hay log de Fiscalberry en $appLog"
    }
}

function Stop-Fiscalberry {
    Get-Process -Name "fiscalberry-gui" -ErrorAction SilentlyContinue | Stop-Process -Force
    Wait-Until { -not (Get-Process -Name "fiscalberry-gui" -ErrorAction SilentlyContinue) } 30 `
        "Fiscalberry no terminó de cerrarse"
}

# 1) Instalación limpia ------------------------------------------------------
Write-Host "== Instalación"
$install = Start-Setup @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/LOG=`"$logs\install.log`"")
Wait-Exit $install 300 "La instalación"
if (-not (Test-Path $exe)) { throw "No quedó instalado $exe" }
if (-not (Test-Path $uninstaller)) { throw "No quedó el desinstalador $uninstaller" }
$run = (Get-ItemProperty -Path $runKey -Name "Fiscalberry" -ErrorAction SilentlyContinue).Fiscalberry
if ($run -notlike "*fiscalberry-gui.exe*--minimized*") {
    throw "El arranque con Windows no quedó configurado con --minimized: '$run'"
}

# 2) El binario instalado arranca ------------------------------------------
Write-Host "== Selftest del binario instalado"
$report = Join-Path $logs "selftest.txt"
# Es una GUI (sin consola): con el operador & PowerShell no esperaría a que
# termine. Se espera el proceso de forma explícita.
$selftest = Start-Process -FilePath $exe -ArgumentList @("--selftest", "--report", "`"$report`"") -PassThru
$null = $selftest.Handle
if (-not $selftest.WaitForExit(180000)) { throw "El selftest no terminó en 180 s" }
$contenido = if (Test-Path $report) { Get-Content $report -Raw } else { "(sin reporte)" }
Write-Host "selftest: código $($selftest.ExitCode) -> $contenido"
if ($selftest.ExitCode -ne 0 -or $contenido -notmatch "FISCALBERRY_SELFTEST_OK") {
    Show-AppLog
    throw "El binario instalado no superó el selftest"
}
# El primer arranque (el selftest) tiene que dejar un config.ini completo: un
# import circular lo dejaba vacío y la app arrancaba sin uuid ni sio_host.
if (-not (Select-String -Path $configIni -Pattern "sio_host" -SimpleMatch -Quiet)) {
    Show-AppLog
    throw "El primer arranque dejó $configIni sin sio_host"
}
$productVersion = (Get-Item $exe).VersionInfo.ProductVersion
$displayVersion = (Get-ItemProperty -Path $uninstallKey).DisplayVersion
if ($displayVersion -ne $productVersion) {
    throw "Aplicaciones muestra la versión '$displayVersion' y el ejecutable es '$productVersion'"
}

# El asistente de impresoras usa APIs de Windows que en Linux solo se prueban
# con fakes: acá se leen de verdad. El runner no tiene impresoras, pero sí red.
Write-Host "== Lo que ve el asistente de impresoras"
$discovery = Join-Path $logs "discovery.json"
$proc = Start-Process -FilePath $exe -ArgumentList @("--discovery-report", "--report", "`"$discovery`"") -PassThru
$null = $proc.Handle
if (-not $proc.WaitForExit(120000)) {
    Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    throw "El informe de descubrimiento no terminó en 120 s"
}
if (-not (Test-Path $discovery)) {
    Show-AppLog
    throw "El informe de descubrimiento no se escribió (código $($proc.ExitCode))"
}
$crudo = Get-Content $discovery -Raw
Write-Host $crudo
$informe = $crudo | ConvertFrom-Json
if ($proc.ExitCode -ne 0) {
    Show-AppLog
    throw "El informe de descubrimiento falló en: $($informe.fallas -join ', ')"
}
$fisicos = @($informe.adaptadores | Where-Object { $_.kind -eq "fisico" -and $_.up -and $_.prefix -gt 0 })
if ($fisicos.Count -lt 1) {
    throw "GetAdaptersAddresses no devolvió ningún adaptador físico conectado con IPv4"
}
foreach ($a in $fisicos) {
    if (-not ($a.address -as [ipaddress])) { throw "Dirección inválida en el adaptador '$($a.name)': $($a.address)" }
}

# 3) Actualización con Fiscalberry abierto -----------------------------------
Write-Host "== Actualización silenciosa con la app abierta y /RELAUNCH=1"
# Lo que deja una instancia viva: el mutex con nombre.
$mutex = New-Object System.Threading.Mutex($false, $mutexName)
$update = Start-Setup @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS", "/RELAUNCH=1", "/LOG=`"$logs\update.log`"")
Start-Sleep -Seconds 5
if ($update.HasExited) {
    throw "El setup no esperó a que se cerrara Fiscalberry (terminó con código $($update.ExitCode))"
}
# "Se cierra" Fiscalberry: el setup tiene que seguir solo.
$mutex.Dispose()
Wait-Exit $update 300 "La actualización"

if (-not (Test-Path $uninstaller)) { throw "La actualización borró unins000.exe" }
if (-not (Test-Path (Join-Path $installDir "_internal"))) { throw "La actualización dejó la instalación sin _internal" }
if (-not (Select-String -Path "$logs\update.log" -Pattern "--minimized" -SimpleMatch -Quiet)) {
    throw "El setup no relanzó Fiscalberry con --minimized (ver update.log)"
}
# La app relanzada puede no llegar a abrir ventana en un runner sin GPU, pero
# nunca tiene que haber dos procesos.
Start-Sleep -Seconds 5
$procesos = @(Get-Process -Name "fiscalberry-gui" -ErrorAction SilentlyContinue)
if ($procesos.Count -gt 1) {
    Show-AppLog
    throw "Quedaron $($procesos.Count) procesos de Fiscalberry"
}
Stop-Fiscalberry

# 4) Desinstalación ---------------------------------------------------------
Write-Host "== Desinstalación"
if (-not (Test-Path $configIni)) { throw "El selftest no generó $configIni" }
$uninstall = Start-Process -FilePath $uninstaller -ArgumentList @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART") -PassThru
$null = $uninstall.Handle
Wait-Exit $uninstall 300 "La desinstalación"
# El desinstalador se relanza desde %TEMP% para poder borrarse a sí mismo.
Wait-Until { -not (Test-Path $exe) } 120 "La desinstalación no borró $exe"
if (Get-ItemProperty -Path $runKey -Name "Fiscalberry" -ErrorAction SilentlyContinue) {
    throw "La desinstalación dejó el arranque con Windows"
}
if (-not (Test-Path $configIni)) { throw "La desinstalación borró config.ini (se pierde la vinculación)" }

Show-AppLog
Write-Host "Instalador OK: instalación, actualización con /RELAUNCH=1 y desinstalación."
