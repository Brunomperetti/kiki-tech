# KIKI — revisión del archivo exportado en el equipo del operador.
# SOLO lectura local. No requiere Docker ni PostgreSQL; NO prueba pg_restore.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string] $BackupPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

try {
    $file = Get-Item -LiteralPath $BackupPath -ErrorAction Stop
    if ($file.PSIsContainer -or
        -not $file.Name.EndsWith('.dir.tar.gz', [StringComparison]::OrdinalIgnoreCase) -or
        $file.Length -le 1024) {
        throw 'Se requiere la exportacion real de Render con formato .dir.tar.gz.'
    }

    $tar = Get-Command 'tar.exe' -ErrorAction SilentlyContinue
    if (-not $tar) {
        $tar = Get-Command 'tar' -ErrorAction SilentlyContinue
    }
    if (-not $tar) {
        throw 'tar no esta disponible en este equipo; no se puede inspeccionar el archivo.'
    }

    $sha = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    Write-Host ('Archivo: ' + $file.Name)
    Write-Host ('Bytes: ' + $file.Length)
    Write-Host ('SHA-256: ' + $sha)

    # Enumerate archive entries only; never extract untrusted paths.
    $entries = @(& $tar.Source '-tzf' $file.FullName 2>&1)
    if ($LASTEXITCODE -ne 0 -or $entries.Count -lt 1) {
        throw 'El archivo tar/gzip no pudo enumerarse integramente: NO PASO.'
    }
    $toc = @()
    foreach ($raw in $entries) {
        $name = [string]$raw
        $normalized = $name.Replace('\', '/')
        if (
            $normalized -match '^/' -or
            $normalized -match '^[A-Za-z]:' -or
            $normalized -match '(^|/)\.\.(/|$)' -or
            $normalized -match '//'
        ) {
            throw ('Ruta insegura dentro del respaldo: ' + $name)
        }
        if ($normalized -match '(^|/)toc\.dat$') {
            $toc += $normalized
        }
    }
    if ($toc.Count -ne 1) {
        throw ('Se esperaba exactamente un toc.dat; encontrados: ' + $toc.Count)
    }

    Write-Host ('Entradas inspeccionadas: ' + $entries.Count)
    Write-Host ('TOC detectado: ' + $toc[0])
    Write-Host 'ESTRUCTURA APARENTE: PASO (tar/gzip + toc.dat).'
    Write-Host 'RESTAURACION POSTGRESQL 18: PENDIENTE. NO se valido pg_restore ni tablas.'
    Write-Host 'No se transmitio el respaldo a GitHub, Render ni otros servicios.'
    exit 0
} catch {
    Write-Error ('NO PASO: ' + $_.Exception.Message)
    exit 1
}
