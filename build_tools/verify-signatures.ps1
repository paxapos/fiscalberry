<#
Verifica la firma Authenticode de los binarios de Windows (#176).

Para cada archivo exige:
  - firma válida (WinVerifyTrust: cadena hasta una raíz de confianza y archivo
    sin modificar);
  - el editor esperado (subject del certificado) y, si se indica, la huella
    (thumbprint) exacta del certificado;
  - sello de tiempo (timestamp): sin él, la firma deja de ser válida el día
    que vence el certificado, y los certificados de firma de código duran
    como mucho 458 días desde marzo de 2026;
  - que la cadena se pueda construir de punta a punta.

Falla (exit 1) ante el primer archivo que no cumpla. No imprime nada secreto:
el certificado público y su huella no lo son.

Uso:
  .\build_tools\verify-signatures.ps1 -Files a.exe,b.exe -ExpectedSubject "Plus Abstracta" [-ExpectedThumbprint ABC...]
#>
param(
    [Parameter(Mandatory = $true)][string[]]$Files,
    [Parameter(Mandatory = $true)][string]$ExpectedSubject,
    [string]$ExpectedThumbprint = ""
)

$ErrorActionPreference = "Stop"
$fallas = @()

foreach ($archivo in $Files) {
    if (-not (Test-Path $archivo)) {
        $fallas += "${archivo}: no existe"
        continue
    }
    $firma = Get-AuthenticodeSignature -FilePath $archivo
    $cert = $firma.SignerCertificate

    if ($firma.Status -ne "Valid") {
        $fallas += "${archivo}: firma $($firma.Status) ($($firma.StatusMessage))"
        continue
    }
    if ($cert.Subject -notlike "*$ExpectedSubject*") {
        $fallas += "${archivo}: firmado por '$($cert.Subject)', se esperaba '$ExpectedSubject'"
    }
    if ($ExpectedThumbprint -and ($cert.Thumbprint -ne $ExpectedThumbprint.Replace(" ", "").ToUpper())) {
        $fallas += "${archivo}: huella $($cert.Thumbprint), se esperaba $ExpectedThumbprint"
    }
    if (-not $firma.TimeStamperCertificate) {
        $fallas += "${archivo}: la firma no tiene sello de tiempo"
    }

    $cadena = New-Object System.Security.Cryptography.X509Certificates.X509Chain
    $cadena.ChainPolicy.RevocationMode = [System.Security.Cryptography.X509Certificates.X509RevocationMode]::Online
    $cadena.ChainPolicy.RevocationFlag = [System.Security.Cryptography.X509Certificates.X509RevocationFlag]::ExcludeRoot
    if (-not $cadena.Build($cert)) {
        $estados = ($cadena.ChainStatus | ForEach-Object { $_.Status }) -join ", "
        $fallas += "${archivo}: la cadena del certificado no se pudo construir ($estados)"
    }

    Write-Host ("{0}: {1} | {2} | timestamp {3}" -f $archivo, $cert.Subject, $cert.Thumbprint,
        $(if ($firma.TimeStamperCertificate) { $firma.TimeStamperCertificate.Subject } else { "NO" }))
}

if ($fallas.Count -gt 0) {
    $fallas | ForEach-Object { Write-Host "::error::$_" }
    exit 1
}
Write-Host "Firmas verificadas: $($Files.Count) archivo(s)."
