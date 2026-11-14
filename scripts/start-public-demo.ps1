<#
.SYNOPSIS
    Starts the isolated CityLab Docker demo and exposes it via a temporary Cloudflare Quick Tunnel.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot

function Resolve-CloudflaredPath {
    param([string]$Root)
    $fromPath = Get-Command cloudflared -ErrorAction SilentlyContinue
    if ($fromPath) {
        return $fromPath.Source
    }
    $localAppDataExe = Join-Path $env:LOCALAPPDATA 'Programs\cloudflared\cloudflared.exe'
    if (Test-Path $localAppDataExe) {
        return $localAppDataExe
    }
    $repoLocalExe = Join-Path $Root '.tunnel\bin\cloudflared.exe'
    if (Test-Path $repoLocalExe) {
        return $repoLocalExe
    }
    return $null
}

Push-Location $repoRoot
try {
    & (Join-Path $PSScriptRoot 'start-docker-demo.ps1')
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }

    $cloudflared = Resolve-CloudflaredPath -Root $repoRoot
    if (-not $cloudflared) {
        Write-Error (
            "cloudflared binary was not found on PATH or at '$env:LOCALAPPDATA\Programs\cloudflared\cloudflared.exe'. " +
            "Install Cloudflare.cloudflared and retry."
        )
        exit 1
    }

    $tunnelDir = Join-Path $repoRoot '.tunnel'
    New-Item -ItemType Directory -Force -Path $tunnelDir | Out-Null

    $pidFile = Join-Path $tunnelDir 'tunnel.pid'
    $metaFile = Join-Path $tunnelDir 'tunnel.json'
    $logFile = Join-Path $tunnelDir 'cloudflared.log'
    $stdoutFile = Join-Path $tunnelDir 'cloudflared.stdout.log'
    $stderrFile = Join-Path $tunnelDir 'cloudflared.stderr.log'

    # Reuse existing tunnel process if still alive and responding
    if ((Test-Path $pidFile) -and (Test-Path $metaFile)) {
        $existingPidRaw = (Get-Content -Raw $pidFile).Trim()
        $existingPid = 0
        if ([int]::TryParse($existingPidRaw, [ref]$existingPid)) {
            $existingProc = Get-Process -Id $existingPid -ErrorAction SilentlyContinue
            if ($existingProc -and ($existingProc.ProcessName -like 'cloudflared*')) {
                try {
                    $meta = Get-Content -Raw $metaFile | ConvertFrom-Json
                    if ($meta.url) {
                        $probe = Invoke-RestMethod -Uri "$($meta.url)/api/health" -Method Get -TimeoutSec 5
                        if ($probe.status -eq 'ok') {
                            Write-Host "Existing Cloudflare Quick Tunnel is active (PID $existingPid):"
                            Write-Host "Temporary Public Demo URL: $($meta.url)"
                            return
                        }
                    }
                } catch {
                    # Existing tunnel is stale or unreachable; terminate cleanly and recreate
                }
                Stop-Process -Id $existingPid -Force -ErrorAction SilentlyContinue
            }
        }
        Remove-Item -Force -ErrorAction SilentlyContinue $pidFile, $metaFile
    }

    Remove-Item -Force -ErrorAction SilentlyContinue $logFile, $stdoutFile, $stderrFile

    Write-Host "Starting Cloudflare Quick Tunnel to http://127.0.0.1:8080..."
    $proc = Start-Process `
        -FilePath $cloudflared `
        -ArgumentList @('tunnel', '--no-autoupdate', '--logfile', $logFile, '--url', 'http://127.0.0.1:8080') `
        -WindowStyle Hidden `
        -RedirectStandardOutput $stdoutFile `
        -RedirectStandardError $stderrFile `
        -PassThru

    Set-Content -Path $pidFile -Value $proc.Id -Encoding ascii

    $publicUrl = $null
    $urlPattern = 'https://[a-z0-9-]+\.trycloudflare\.com'
    for ($i = 0; $i -lt 45; $i++) {
        Start-Sleep -Seconds 1
        foreach ($candidateLog in @($logFile, $stderrFile, $stdoutFile)) {
            if (Test-Path $candidateLog) {
                $content = Get-Content -Raw -ErrorAction SilentlyContinue $candidateLog
                if ($content -match $urlPattern) {
                    $publicUrl = $Matches[0]
                    break
                }
            }
        }
        if ($publicUrl) {
            break
        }
        $proc.Refresh()
        if ($proc.HasExited) {
            Write-Error "cloudflared exited unexpectedly with code $($proc.ExitCode). Inspect '$logFile' and '$stderrFile'."
            Remove-Item -Force -ErrorAction SilentlyContinue $pidFile
            exit 1
        }
    }

    if (-not $publicUrl) {
        Write-Error "Timed out waiting for trycloudflare.com URL. Inspect '$logFile' and '$stderrFile'."
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        Remove-Item -Force -ErrorAction SilentlyContinue $pidFile
        exit 1
    }

    Write-Host "Verifying public endpoint at $publicUrl/api/health..."
    $verified = $false
    for ($i = 0; $i -lt 20; $i++) {
        try {
            $resp = Invoke-RestMethod -Uri "$publicUrl/api/health" -Method Get -TimeoutSec 5
            if ($resp.status -eq 'ok') {
                $verified = $true
                break
            }
        } catch {
            Start-Sleep -Milliseconds 1500
        }
    }

    if (-not $verified) {
        Write-Error "Public tunnel URL '$publicUrl' failed health verification within 30 seconds."
        exit 1
    }

    $metadata = [ordered]@{
        url                    = $publicUrl
        local_url              = 'http://127.0.0.1:8080'
        pid                    = $proc.Id
        started_at_utc         = (Get-Date).ToUniversalTime().ToString('o')
        temporary_quick_tunnel = $true
    } | ConvertTo-Json -Depth 3
    Set-Content -Path $metaFile -Value $metadata -Encoding utf8

    Write-Host ''
    Write-Host "Public demo ready (temporary Cloudflare Quick Tunnel): $publicUrl"
    Write-Host 'Note: Keep this PC awake and running. Stopping the tunnel rotates the URL on the next start.'
    Write-Host 'To stop safely without deleting demo volume data: .\scripts\stop-public-demo.ps1'
} finally {
    Pop-Location
}
