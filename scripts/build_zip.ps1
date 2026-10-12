<#
.SYNOPSIS
    Genera el bundle para "Upload and deploy" de Elastic Beanstalk.

.DESCRIPTION
    Lee la version de src/version.py y empaqueta el ultimo commit con
    git archive en ..\listanegra-v<version>.zip (fuera del repo). git archive
    solo incluye lo commiteado, por eso avisa si hay cambios sin commit.

.EXAMPLE
    .\scripts\build_zip.ps1
#>
$ErrorActionPreference = "Stop"

$repo = Split-Path -Parent $PSScriptRoot
Push-Location $repo
try {
    $match = Select-String -Path "src\version.py" -Pattern 'APP_VERSION\s*=\s*"([^"]+)"'
    if (-not $match) { throw "No se encontro APP_VERSION en src\version.py" }
    $version = $match.Matches[0].Groups[1].Value

    $pending = git status --porcelain
    if ($pending) {
        Write-Host "ATENCION: hay cambios sin commit. git archive solo empaqueta HEAD:" -ForegroundColor Yellow
        $pending | ForEach-Object { Write-Host "  $_" -ForegroundColor Yellow }
    }

    $ErrorActionPreference = "Continue"
    $headContent = git show HEAD:src/version.py 2>&1
    $found = ($LASTEXITCODE -eq 0)
    $ErrorActionPreference = "Stop"
    if (-not $found) { throw "src\version.py no esta en el commit HEAD: haga commit antes de empaquetar." }

    $headVersion = $headContent | Select-String -Pattern 'APP_VERSION\s*=\s*"([^"]+)"'
    if (-not $headVersion -or $headVersion.Matches[0].Groups[1].Value -ne $version) {
        throw ("src\version.py dice {0} pero el commit HEAD tiene otra version. Haga commit antes de empaquetar." -f $version)
    }

    $output = Join-Path (Split-Path -Parent $repo) "listanegra-v$version.zip"
    git archive --format=zip --output "$output" HEAD
    if ($LASTEXITCODE -ne 0) { throw "git archive fallo" }

    $commit = git rev-parse --short HEAD
    Write-Host ("Bundle: {0}" -f $output) -ForegroundColor Green
    Write-Host ("Version: {0}  Commit: {1}" -f $version, $commit) -ForegroundColor Green
    Write-Host ("Version label sugerido en Beanstalk: v{0}-<estrategia>" -f $version)
} finally {
    Pop-Location
}
