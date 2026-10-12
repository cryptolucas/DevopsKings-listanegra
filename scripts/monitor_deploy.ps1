<#
.SYNOPSIS
    Monitorea /health cada segundo durante un despliegue en Elastic Beanstalk.

.DESCRIPTION
    Imprime por cada solicitud: hora, segundos transcurridos, codigo HTTP,
    version y host (instancia EC2) que respondio. Termina solo cuando lleva
    -StopAfter respuestas seguidas con la version -Target, o con Ctrl+C.
    Al final imprime un resumen con los datos de los literales b, c y d del
    documento, y guarda todo en evidencias/<Target>-<fecha>.log.

.EXAMPLE
    .\scripts\monitor_deploy.ps1 -Url http://listanegra-env.eba-xxxx.us-east-1.elasticbeanstalk.com -Target 1.0.1
#>
param(
    [Parameter(Mandatory = $true)][string]$Url,
    [Parameter(Mandatory = $true)][string]$Target,
    [int]$StopAfter = 30
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$healthUrl = $Url.TrimEnd("/")
if (-not $healthUrl.EndsWith("/health")) { $healthUrl = "$healthUrl/health" }

$evidenceDir = Join-Path (Split-Path -Parent $PSScriptRoot) "evidencias"
New-Item -ItemType Directory -Force -Path $evidenceDir | Out-Null
$logFile = Join-Path $evidenceDir ("{0}-{1}.log" -f $Target, (Get-Date -Format "yyyyMMdd-HHmmss"))

function Write-Log([string]$Text, [string]$Color = "Gray") {
    Write-Host $Text -ForegroundColor $Color
    Add-Content -Path $logFile -Value $Text -Encoding UTF8
}

function Format-Duration([double]$Seconds) {
    $ts = [TimeSpan]::FromSeconds([math]::Round($Seconds))
    return "{0} min {1} s ({2:N0} s)" -f [math]::Floor($ts.TotalMinutes), $ts.Seconds, $Seconds
}

$byVersion = @{}
$byHost = @{}
$hostsOld = @{}
$hostsNew = @{}
$total = 0
$failures = 0
$failStreak = 0
$maxFailStreak = 0
$firstFailure = $null
$lastFailure = $null
$firstTarget = $null
$lastNonTarget = $null
$streak = 0
$start = Get-Date

Write-Log ("Monitor de despliegue - {0}" -f $start.ToString("yyyy-MM-dd HH:mm:ss"))
Write-Log ("URL: {0} | version objetivo: {1} | fin tras {2} respuestas seguidas" -f $healthUrl, $Target, $StopAfter)
Write-Log ("Log: {0}" -f $logFile)
Write-Log ""

try {
    while ($streak -lt $StopAfter) {
        $tick = Get-Date
        $elapsed = ($tick - $start).TotalSeconds
        $code = 0
        $version = "-"
        $hostName = "-"

        try {
            $response = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 3
            $code = [int]$response.StatusCode
            $body = $response.Content | ConvertFrom-Json
            if ($body.version) { $version = $body.version }
            if ($body.host) { $hostName = $body.host }
        } catch {
            $webResponse = $_.Exception.Response
            if ($webResponse) { $code = [int]$webResponse.StatusCode }
        }

        $total++
        $ok = ($code -eq 200)
        $line = "{0}  t={1,5:N0}s  HTTP {2,3}  version={3,-8} host={4}" -f $tick.ToString("HH:mm:ss"), $elapsed, $(if ($code) { $code } else { "ERR" }), $version, $hostName

        if (-not $ok) {
            $failures++
            $failStreak++
            if ($failStreak -gt $maxFailStreak) { $maxFailStreak = $failStreak }
            if ($null -eq $firstFailure) { $firstFailure = $elapsed }
            $lastFailure = $elapsed
            $lastNonTarget = $elapsed
            $streak = 0
            Write-Log $line "Red"
        } else {
            $failStreak = 0
            $byVersion[$version] = 1 + [int]$byVersion[$version]
            $byHost[$hostName] = 1 + [int]$byHost[$hostName]
            if ($version -eq $Target) {
                if ($null -eq $firstTarget) { $firstTarget = $elapsed }
                $hostsNew[$hostName] = $true
                $streak++
                Write-Log $line "Green"
            } else {
                $hostsOld[$hostName] = $true
                $lastNonTarget = $elapsed
                $streak = 0
                Write-Log $line "Yellow"
            }
        }

        $wait = 1000 - [int]((Get-Date) - $tick).TotalMilliseconds
        if ($wait -gt 0) { Start-Sleep -Milliseconds $wait }
    }
} finally {
    $end = Get-Date
    Write-Log ""
    Write-Log "================ RESUMEN ================" "Cyan"
    Write-Log ("Inicio: {0}   Fin: {1}" -f $start.ToString("HH:mm:ss"), $end.ToString("HH:mm:ss"))
    Write-Log ("Duracion del monitoreo: {0}" -f (Format-Duration ($end - $start).TotalSeconds))
    Write-Log ("Solicitudes: {0}   Exitosas: {1}   Fallidas: {2}" -f $total, ($total - $failures), $failures)

    if ($null -ne $firstTarget) {
        Write-Log ("Primera respuesta con {0}: t={1:N0}s" -f $Target, $firstTarget)
    } else {
        Write-Log ("Nunca respondio la version {0}" -f $Target) "Red"
    }
    if ($streak -ge $StopAfter) {
        $full = if ($null -ne $lastNonTarget) { $lastNonTarget } else { 0 }
        Write-Log ("100% en {0} desde: t={1:N0}s -> {2}" -f $Target, $full, (Format-Duration $full))
    } else {
        Write-Log "Monitoreo detenido antes de confirmar 100% de la nueva version." "Yellow"
    }

    if ($failures -gt 0) {
        Write-Log ("Downtime observado: {0} solicitudes fallidas entre t={1:N0}s y t={2:N0}s (ventana de {3:N0} s, racha maxima de {4} fallos seguidos)" -f $failures, $firstFailure, $lastFailure, ($lastFailure - $firstFailure + 1), $maxFailStreak) "Red"
    } else {
        Write-Log "Downtime observado: ninguno (0 fallos)" "Green"
    }

    Write-Log "Respuestas por version:"
    foreach ($k in ($byVersion.Keys | Sort-Object)) { Write-Log ("  {0,-10} {1}" -f $k, $byVersion[$k]) }
    Write-Log "Respuestas por host:"
    foreach ($k in ($byHost.Keys | Sort-Object)) { Write-Log ("  {0,-20} {1}" -f $k, $byHost[$k]) }

    $old = @($hostsOld.Keys | Sort-Object)
    $new = @($hostsNew.Keys | Sort-Object)
    $reused = @($new | Where-Object { $hostsOld.ContainsKey($_) })
    Write-Log ("Hosts con version anterior: {0}" -f ($(if ($old.Count) { $old -join ", " } else { "-" })))
    Write-Log ("Hosts con version {0}: {1}" -f $Target, ($(if ($new.Count) { $new -join ", " } else { "-" })))
    if ($new.Count -gt 0) {
        if ($old.Count -eq 0) {
            Write-Log "Literal d: no se vieron hosts con la version anterior; no se puede comparar."
        } elseif ($reused.Count -eq $new.Count) {
            Write-Log "Literal d: la nueva version corre sobre las MISMAS instancias iniciales."
        } elseif ($reused.Count -eq 0) {
            Write-Log "Literal d: la nueva version corre sobre instancias NUEVAS."
        } else {
            Write-Log ("Literal d: mezcla - reutilizadas: {0}; nuevas: {1}" -f ($reused -join ", "), (@($new | Where-Object { -not $hostsOld.ContainsKey($_) }) -join ", "))
        }
    }
    Write-Log "El tiempo oficial (literal c) es el de la pestana Events: 'Environment update is starting' -> 'completed successfully'."
    Write-Log ("Log guardado en {0}" -f $logFile) "Cyan"
}
