# Prueba de punta a punta de FiscalberrySetup.exe, en el runner de Windows.
#
# La corre build-release.yml después de compilar el instalador. Cubre lo que
# un usuario y el auto-updater hacen con él:
#
#   1. Instalación limpia en silencio: deja el programa, el desinstalador y el
#      arranque con la sesión (--minimized).
#   2. El binario INSTALADO pasa el selftest.
#   3. El asistente de impresoras puede leer esta PC (--discovery-report):
#      las APIs de Windows que llama por ctypes no revientan. Un struct mal
#      declarado solo se ve en un Windows de verdad.
#   4. Actualización silenciosa con Fiscalberry abierto: el setup espera a que
#      se libere el mutex de instancia única antes de tocar archivos, y no
#      borra el desinstalador.
#   5. Con /RELAUNCH=1 el setup vuelve a abrir Fiscalberry.
#   6. La desinstalación borra el programa y el arranque con la sesión, pero
#      conserva el config.ini (la vinculación con el comercio).
#
# Detalles que no son obvios y que ya hicieron fallar esta prueba antes:
#
# - fiscalberry-gui.exe es de subsistema GUI (console=False). PowerShell NO
#   espera a ese tipo de ejecutable si se lo invoca con `&`, y tampoco asigna
#   $LASTEXITCODE. Siempre Start-Process -Wait -PassThru.
# - Kivy parsea sys.argv al importarse y, sin KIVY_NO_ARGS, aborta con código 2
#   al ver `--selftest`. El workflow define KIVY_NO_ARGS en el entorno.
# - La marca de éxito del selftest es la de updater/selftest.py (OK_MARKER más
#   la versión), no un texto parecido.
# - Con Start-Process -PassThru SIN -Wait, ExitCode queda vacío si no se tocó
#   .Handle antes de que el proceso termine.

param(
    [Parameter(Mandatory = $true)][string]$Version,
    [string]$Setup = "dist\FiscalberrySetup.exe"
)

$ErrorActionPreference = "Stop"

$setupPath = (Resolve-Path $Setup).Path
$installDir = Join-Path $env:LOCALAPPDATA "Programs\Fiscalberry"
$exe = Join-Path $installDir "fiscalberry-gui.exe"
$uninstaller = Join-Path $installDir "unins000.exe"
$mutexName = "Local\FiscalberrySingleInstance"
$runKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
$silencioso = @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART")
$tmp = if ($env:RUNNER_TEMP) { $env:RUNNER_TEMP } else { [System.IO.Path]::GetTempPath() }

function Paso([string]$texto) {
    Write-Host ""
    Write-Host "=== $texto ==="
}

function Esperar([scriptblock]$Condicion, [int]$Segundos, [string]$Mensaje) {
    $limite = (Get-Date).AddSeconds($Segundos)
    while (-not (& $Condicion)) {
        if ((Get-Date) -gt $limite) { throw $Mensaje }
        Start-Sleep -Milliseconds 500
    }
}

function Ejecutar([string]$Archivo, [string[]]$Argumentos) {
    $proceso = Start-Process $Archivo -ArgumentList $Argumentos -Wait -PassThru
    return $proceso.ExitCode
}

function CarpetasDeDatos {
    @((Join-Path $env:LOCALAPPDATA "Fiscalberry"), (Join-Path $env:APPDATA "Fiscalberry")) |
        Where-Object { Test-Path $_ }
}

function ArranquesRegistrados {
    $logs = CarpetasDeDatos | ForEach-Object {
        Get-ChildItem $_ -Recurse -Filter "fiscalberry.log" -ErrorAction SilentlyContinue
    }
    if (-not $logs) { return 0 }
    return @($logs | Select-String -SimpleMatch "=== Iniciando Fiscalberry GUI ===").Count
}

function MutexAbierto {
    $existente = $null
    $abierto = [System.Threading.Mutex]::TryOpenExisting($mutexName, [ref]$existente)
    if ($existente) { $existente.Dispose() }
    return $abierto
}

function ValorDeArranque {
    $valor = Get-ItemProperty $runKey -Name "Fiscalberry" -ErrorAction SilentlyContinue
    if ($valor) { return $valor.Fiscalberry }
    return $null
}

# ---------------------------------------------------------------------------
Paso "1. Instalación limpia y silenciosa"
$codigo = Ejecutar $setupPath ($silencioso + @("/LOG=`"$(Join-Path $tmp 'fiscalberry-install.log')`""))
if ($codigo -ne 0) { throw "El instalador terminó con código $codigo" }
foreach ($archivo in @($exe, $uninstaller)) {
    if (-not (Test-Path $archivo)) { throw "Falta $archivo después de instalar" }
}
$arranque = ValorDeArranque
if (-not $arranque -or -not $arranque.Contains("--minimized")) {
    throw "El arranque con la sesión no quedó configurado con --minimized (valor: '$arranque')"
}
Write-Host "Arranque con la sesión: $arranque"

# ---------------------------------------------------------------------------
Paso "2. Selftest del binario instalado"
$reporte = Join-Path $tmp "fiscalberry-installed-selftest.txt"
$codigo = Ejecutar $exe @("--selftest", "--report", "`"$reporte`"")
if ($codigo -ne 0) { throw "El selftest del binario instalado salió con código $codigo" }
if (-not (Test-Path $reporte)) { throw "El selftest no escribió el reporte en $reporte" }
$contenido = Get-Content $reporte -Raw
Write-Host $contenido
$esperado = "FISCALBERRY_SELFTEST_OK $Version"
if (-not $contenido.Contains($esperado)) {
    throw "El binario instalado no superó el selftest: se esperaba '$esperado'"
}

# ---------------------------------------------------------------------------
Paso "3. Lo que ve el asistente de impresoras"
$informe = Join-Path $tmp "fiscalberry-discovery.json"
# Sin -Wait: si una API de Windows se colgara, la prueba tiene que fallar, no
# quedarse esperando hasta que GitHub corte el job.
$proceso = Start-Process $exe -ArgumentList @("--discovery-report", "--report", "`"$informe`"") -PassThru
$null = $proceso.Handle
if (-not $proceso.WaitForExit(120000)) {
    Stop-Process -Id $proceso.Id -Force -ErrorAction SilentlyContinue
    throw "--discovery-report no terminó en 120 s"
}
$codigo = $proceso.ExitCode
if (-not (Test-Path $informe)) { throw "--discovery-report no escribió el informe en $informe (código $codigo)" }
$texto = Get-Content $informe -Raw -Encoding UTF8
Write-Host $texto
$datos = $texto | ConvertFrom-Json
if ($codigo -ne 0 -or @($datos.fallas).Count -gt 0) {
    throw "El informe del asistente tuvo fallas (código $codigo): $($datos.fallas -join ', ')"
}
# El runner tiene red: si no aparece ningún adaptador, GetAdaptersAddresses se
# está leyendo mal.
$fisicos = @($datos.adaptadores | Where-Object { $_.kind -eq "fisico" -and $_.up -and $_.prefix -gt 0 })
if ($fisicos.Count -eq 0) { throw "El informe no encontró ningún adaptador de red físico con IPv4" }
foreach ($a in $fisicos) {
    if (-not ($a.address -as [ipaddress])) { throw "Dirección inválida en el adaptador '$($a.name)': $($a.address)" }
}
# El runner es una VM sin USB ni impresoras: que esas listas den cero no prueba
# nada. El control enumera con el mismo código los discos y todos los
# dispositivos, que en cualquier PC son más de cero: si dan cero, o las rutas
# no se leen, los structs de SetupDi están mal declarados.
if ($null -eq $datos.dispositivos_usb.total) { throw "El informe no trae la lista de dispositivos USB" }
$control = $datos.control_setupdi
Write-Host "Control SetupDi: $($control.interfaces_de_disco) discos ($($control.rutas_legibles) rutas legibles), $($control.dispositivos) dispositivos ($($control.con_hardware_id) con Id. de hardware)"
if ($control.interfaces_de_disco -lt 1 -or $control.rutas_legibles -lt $control.interfaces_de_disco) {
    throw "SetupDi no enumeró bien las interfaces de disco: el código de usbprint no es confiable"
}
if ($control.dispositivos -lt 1 -or $control.con_hardware_id -lt 1) {
    throw "SetupDi no enumeró bien los dispositivos: la detección de USB incompatibles no es confiable"
}
Write-Host "USB: $($datos.dispositivos_usb.total) dispositivos, usbprint: $(@($datos.usbprint).Count), COM: $(@($datos.puertos_com).Count)"

# ---------------------------------------------------------------------------
Paso "4. Actualización silenciosa con Fiscalberry abierto"
$arranquesAntes = ArranquesRegistrados
$logActualizacion = Join-Path $tmp "fiscalberry-update.log"
# Este mutex es el que tendría tomado un Fiscalberry abierto.
$abierto = New-Object System.Threading.Mutex($false, $mutexName)
try {
    $actualizacion = Start-Process $setupPath -PassThru -ArgumentList ($silencioso + @(
            "/CLOSEAPPLICATIONS", "/RELAUNCH=1", "/LOG=`"$logActualizacion`""))
    $null = $actualizacion.Handle
    Start-Sleep -Seconds 8
    if ($actualizacion.HasExited) {
        throw "El setup no esperó a que se cerrara Fiscalberry: terminó con código $($actualizacion.ExitCode)"
    }
    Write-Host "El setup está esperando que Fiscalberry se cierre (correcto)."
}
finally {
    # Fiscalberry se cierra: el mutex desaparece.
    $abierto.Dispose()
}
if (-not $actualizacion.WaitForExit(180000)) {
    throw "El setup no terminó en 3 minutos después de cerrarse Fiscalberry"
}
if ($actualizacion.ExitCode -ne 0) {
    Get-Content $logActualizacion -Tail 40 -ErrorAction SilentlyContinue
    throw "La actualización terminó con código $($actualizacion.ExitCode)"
}
if (-not (Test-Path $uninstaller)) { throw "La actualización borró unins000.exe" }
if (-not (Test-Path $exe)) { throw "La actualización dejó la instalación sin $exe" }

# ---------------------------------------------------------------------------
Paso "5. El setup volvió a abrir Fiscalberry"
Esperar { (ArranquesRegistrados) -gt $arranquesAntes } 90 `
    "El setup no volvió a abrir Fiscalberry después de actualizar (/RELAUNCH=1)"
Select-String -Path $logActualizacion -SimpleMatch "--minimized" -ErrorAction SilentlyContinue |
    ForEach-Object { Write-Host "log del setup: $($_.Line.Trim())" }
# Se lo cierra para poder desinstalar (el desinstalador también espera al mutex).
Get-Process -Name "fiscalberry-gui" -ErrorAction SilentlyContinue | Stop-Process -Force
Esperar { -not (MutexAbierto) } 30 "Fiscalberry no liberó el mutex después de cerrarlo"

# ---------------------------------------------------------------------------
Paso "6. Desinstalación"
$configs = @(CarpetasDeDatos | ForEach-Object {
        Get-ChildItem $_ -Recurse -Filter "config.ini" -ErrorAction SilentlyContinue
    })
if ($configs.Count -eq 0) { throw "No se encontró el config.ini que crea Fiscalberry al arrancar" }

$codigo = Ejecutar $uninstaller $silencioso
if ($codigo -ne 0) { throw "El desinstalador terminó con código $codigo" }
# El desinstalador de Inno corre en dos fases (se copia a %TEMP% y relanza la
# copia): se le da margen a la segunda para terminar.
Esperar { -not (Test-Path $exe) } 60 "La desinstalación no borró $exe"
Esperar { -not (ValorDeArranque) } 30 "La desinstalación dejó el arranque con la sesión"
foreach ($config in $configs) {
    if (-not (Test-Path $config.FullName)) {
        throw "La desinstalación borró $($config.FullName): se perdería la vinculación"
    }
}

Write-Host ""
Write-Host "INSTALADOR OK"
