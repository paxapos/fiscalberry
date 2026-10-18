<#
.SYNOPSIS
  Deja Windows configurado para que una impresora USB no "cambie de puerto" y,
  si igual pasa, Fiscalberry lo pueda corregir solo.

.DESCRIPTION
  Pensado para comercios donde la impresora USB (ej. Hasar) deja de imprimir
  cada tanto porque Windows le asigna otro puerto virtual (USB001 -> USB002)
  sin que nadie toque el cable.

  Hace, en este orden:
    1. Apaga la suspensión selectiva de USB (ahorro de energía) en el plan
       activo y a nivel del sistema.
    2. Impide que Windows apague los dispositivos USB para ahorrar energía.
    3. Evita que Windows Update reemplace los drivers de dispositivos.
    4. Le da a los usuarios del equipo permiso de "Administrar esta impresora"
       sobre la cola indicada. Con eso Fiscalberry puede mover la cola al
       puerto nuevo por su cuenta cuando Windows la cambia.
    5. Muestra los puertos USB de impresora que conoce Windows y en cuál está
       la cola.

  Correr UNA vez, como Administrador:
    powershell -ExecutionPolicy Bypass -File configurar_impresora_usb.ps1 -Impresora "Nombre de la cola"

  Si no se pasa -Impresora, se listan las impresoras instaladas para elegir.
  Algunos cambios de energía requieren reiniciar la PC para aplicarse.
#>
param(
    [string]$Impresora
)

$ErrorActionPreference = "Stop"

function Paso($texto) { Write-Host ""; Write-Host "==> $texto" -ForegroundColor Cyan }
function Ok($texto)   { Write-Host "    OK  $texto" -ForegroundColor Green }
function Aviso($texto){ Write-Host "    !!  $texto" -ForegroundColor Yellow }
# Ojo: New-Item -Force sobre una clave de registro existente la recrea y borra
# sus valores. Solo se crea si falta.
function AsegurarClave($ruta) { if (-not (Test-Path $ruta)) { New-Item -Path $ruta -Force | Out-Null } }

$esAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
           ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $esAdmin) {
    Write-Host "Este script tiene que correrse como Administrador (clic derecho > Ejecutar como administrador)." -ForegroundColor Red
    exit 1
}

if (-not $Impresora) {
    Write-Host "Impresoras instaladas:"
    Get-Printer | Sort-Object Name | ForEach-Object { Write-Host ("  - {0}  [{1}]" -f $_.Name, $_.PortName) }
    $Impresora = Read-Host "Nombre exacto de la impresora que usa Fiscalberry"
}
$cola = Get-Printer -Name $Impresora -ErrorAction SilentlyContinue
if (-not $cola) {
    Write-Host "No existe una impresora llamada '$Impresora'." -ForegroundColor Red
    exit 1
}

# 1. Suspensión selectiva de USB -------------------------------------------
Paso "Apagando la suspensión selectiva de USB"
$SUB_USB = "2a737441-1930-4402-8d77-b2bebba308a3"
$SET_SUSPENSION = "48e6b7a6-50f5-4782-a5d4-53bb8f07e226"
try {
    powercfg /SETACVALUEINDEX SCHEME_CURRENT $SUB_USB $SET_SUSPENSION 0 | Out-Null
    powercfg /SETDCVALUEINDEX SCHEME_CURRENT $SUB_USB $SET_SUSPENSION 0 | Out-Null
    powercfg /SETACTIVE SCHEME_CURRENT | Out-Null
    Ok "Plan de energía activo: suspensión selectiva de USB deshabilitada"
} catch { Aviso "No se pudo cambiar el plan de energía: $_" }
try {
    AsegurarClave "HKLM:\SYSTEM\CurrentControlSet\Services\USB"
    Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Services\USB" -Name "DisableSelectiveSuspend" -Value 1 -Type DWord
    Ok "Suspensión selectiva deshabilitada a nivel sistema"
} catch { Aviso "No se pudo deshabilitar a nivel sistema: $_" }

# 2. "Permitir que el equipo apague este dispositivo" ------------------------
Paso "Impidiendo que Windows apague los dispositivos USB"
try {
    $n = 0
    Get-CimInstance -Namespace root\wmi -ClassName MSPower_DeviceEnable -ErrorAction Stop |
        Where-Object { $_.InstanceName -like "USB*" -and $_.Enable } |
        ForEach-Object { Set-CimInstance -InputObject $_ -Property @{ Enable = $false }; $n++ }
    Ok "$n dispositivo(s) USB ya no se apagan para ahorrar energía"
} catch { Aviso "No se pudo cambiar la administración de energía de los USB: $_" }

# 3. Windows Update no reemplaza drivers ------------------------------------
Paso "Evitando que Windows Update cambie los drivers"
try {
    AsegurarClave "HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate"
    Set-ItemProperty -Path "HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate" -Name "ExcludeWUDriversInQualityUpdate" -Value 1 -Type DWord
    AsegurarClave "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\DriverSearching"
    Set-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\DriverSearching" -Name "SearchOrderConfig" -Value 0 -Type DWord
    Ok "Windows Update ya no instala drivers de dispositivos"
} catch { Aviso "No se pudo cambiar la política de drivers: $_" }

# 4. Permiso para que Fiscalberry corrija el puerto -------------------------
Paso "Dando permiso para que Fiscalberry corrija el puerto de '$Impresora'"
try {
    $sddl = (Get-Printer -Name $Impresora -Full).PermissionSDDL
    # "Administrar esta impresora" para Usuarios (BU). Sin esto, Fiscalberry
    # detecta el cambio de puerto pero no puede mover la cola.
    $ace = "(A;;LCSWSDRCWDWO;;;BU)"
    if ($sddl -like "*$ace*") {
        Ok "Ya tenía el permiso"
    } else {
        # El ACE va al final de la DACL, antes de la SACL ("S:") si la hay.
        $i = $sddl.IndexOf(")S:")
        if ($i -ge 0) { $nuevo = $sddl.Insert($i + 1, $ace) } else { $nuevo = $sddl + $ace }
        Set-Printer -Name $Impresora -PermissionSDDL $nuevo
        Ok "Los usuarios del equipo pueden administrar '$Impresora'"
    }
} catch { Aviso "No se pudo cambiar el permiso de la impresora: $_" }

# 5. Diagnóstico de puertos -------------------------------------------------
Paso "Puertos USB de impresora que conoce Windows"
$clase = "HKLM:\SYSTEM\CurrentControlSet\Control\DeviceClasses\{28d78fad-5a12-11d1-ae5b-0000f803a8c2}"
$puertoCola = (Get-Printer -Name $Impresora).PortName
if (Test-Path $clase) {
    Get-ChildItem $clase | ForEach-Object {
        $dp = Join-Path $_.PSPath "#\Device Parameters"
        if (Test-Path $dp) {
            $p = Get-ItemProperty $dp
            $nombre = "{0}{1:000}" -f ($(if ($p."Base Name") { $p."Base Name" } else { "USB" })), $p."Port Number"
            $ctl = Join-Path $_.PSPath "#\Control"
            $vivo = (Test-Path $ctl) -and ((Get-ItemProperty $ctl -ErrorAction SilentlyContinue).Linked -eq 1)
            $estado = if ($vivo) { "CONECTADA" } else { "desconectada" }
            $marca = if ($puertoCola -split "," -contains $nombre) { "  <- la cola '$Impresora' está acá" } else { "" }
            Write-Host ("    {0}  {1,-13} {2}{3}" -f $nombre, $estado, $p."Port Description", $marca)
        }
    }
} else {
    Aviso "No hay puertos USB de impresora registrados"
}

Write-Host ""
Write-Host "Listo. Recomendaciones:" -ForegroundColor Cyan
Write-Host "  - Enchufar la impresora SIEMPRE en el mismo puerto, atrás de la PC (no al frente ni a un hub/alargue)."
Write-Host "  - Usar un cable USB corto y en buen estado."
Write-Host "  - Si aparecen muchos puertos 'desconectada' de la misma impresora, Windows la está re-detectando:"
Write-Host "    revisar cable, puerto y la fuente de la impresora."
Write-Host "  - Reiniciar la PC para que se apliquen los cambios de energía."
