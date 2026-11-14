<#
.SYNOPSIS
    Stops the recorded Cloudflare Quick Tunnel and CityLab Docker demo containers cleanly without removing data volumes.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot

Push-Location $repoRoot
try {
    $tunnelDir = Join-Path $repoRoot '.tunnel'
    $pidFile = Join-Path $tunnelDir 'tunnel.pid'
    $metaFile = Join-Path $tunnelDir 'tunnel.json'

    if (Test-Path $pidFile) {
        $pidRaw = (Get-Content -Raw $pidFile).Trim()
        $targetPid = 0
        if ([int]::TryParse($pidRaw, [ref]$targetPid)) {
            $proc = Get-Process -Id $targetPid -ErrorAction SilentlyContinue
            if ($proc -and ($proc.ProcessName -like 'cloudflared*')) {
                Stop-Process -Id $proc.Id -Force
                Write-Host "Stopped cloudflared tunnel (PID $($proc.Id))."
            } else {
                Write-Host "No active cloudflared process found for recorded PID $pidRaw."
            }
        }
        Remove-Item -Force -ErrorAction SilentlyContinue $pidFile
    } else {
        Write-Host 'No recorded tunnel.pid file found.'
    }

    Remove-Item -Force -ErrorAction SilentlyContinue $metaFile

    $dockerCmd = Get-Command docker -ErrorAction SilentlyContinue
    if ($dockerCmd) {
        & docker info *> $null
        if ($LASTEXITCODE -eq 0) {
            Write-Host 'Stopping CityLab Docker demo containers (preserving citylab_public_demo_data volume)...'
            & docker compose stop
        } else {
            Write-Host 'Docker engine is not running; skipped docker compose stop.'
        }
    } else {
        Write-Host 'Docker CLI is not installed; skipped docker compose stop.'
    }
} finally {
    Pop-Location
}
