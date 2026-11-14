<#
.SYNOPSIS
    Starts the isolated CityLab Diagnostics Docker public-demo stack on http://127.0.0.1:8080.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot

Push-Location $repoRoot
try {
    $dockerCmd = Get-Command docker -ErrorAction SilentlyContinue
    if (-not $dockerCmd) {
        Write-Error (
            "Docker CLI was not found on PATH. Install Docker Desktop (with WSL 2 enabled), " +
            "launch Docker Desktop until the engine is Ready, and retry."
        )
        exit 1
    }

    & docker info *> $null
    if ($LASTEXITCODE -ne 0) {
        Write-Error (
            "Docker engine is not running or not accessible. Start Docker Desktop, wait until " +
            "it shows 'Engine running', and retry."
        )
        exit 1
    }

    Write-Host 'Validating docker-compose.yml...'
    & docker compose config --quiet
    if ($LASTEXITCODE -ne 0) {
        Write-Error 'docker compose config validation failed.'
        exit 1
    }

    Write-Host 'Building and starting isolated CityLab Docker demo containers (port 8080)...'
    & docker compose up -d --build
    if ($LASTEXITCODE -ne 0) {
        Write-Error 'docker compose up failed.'
        exit 1
    }

    $healthUrl = 'http://127.0.0.1:8080/api/health'
    Write-Host "Waiting for $healthUrl..."
    $healthy = $false
    for ($i = 0; $i -lt 30; $i++) {
        try {
            $resp = Invoke-RestMethod -Uri $healthUrl -Method Get -TimeoutSec 3
            if ($resp.status -eq 'ok') {
                $healthy = $true
                Write-Host "CityLab Docker demo ready at http://127.0.0.1:8080 (public_demo=$($resp.public_demo), llm=$($resp.llm_provider))"
                break
            }
        } catch {
            Start-Sleep -Milliseconds 1500
        }
    }

    if (-not $healthy) {
        Write-Error "CityLab Docker demo did not become healthy at $healthUrl within 45 seconds. Check 'docker compose logs'."
        exit 1
    }
} finally {
    Pop-Location
}
