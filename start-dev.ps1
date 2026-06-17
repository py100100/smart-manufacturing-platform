param(
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

function Quote-LiteralPath {
    param([string]$Path)
    return "'" + ($Path -replace "'", "''") + "'"
}

function Test-PortAvailable {
    param([int]$Port)

    $listener = $null
    try {
        $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Parse("127.0.0.1"), $Port)
        $listener.Start()
        return $true
    }
    catch {
        return $false
    }
    finally {
        if ($null -ne $listener) {
            $listener.Stop()
        }
    }
}

function Get-AvailablePort {
    param([int[]]$Candidates)

    foreach ($port in $Candidates) {
        if (Test-PortAvailable -Port $port) {
            return $port
        }
    }

    throw "No available frontend port found. Tried: $($Candidates -join ', ')"
}

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Frontend = Join-Path $Root "frontend"
$FrontendPackage = Join-Path $Frontend "package.json"
$NodeModules = Join-Path $Frontend "node_modules"
$BackendPort = Get-AvailablePort -Candidates @(8000, 8001, 8002, 8003, 8004, 8005)
$FrontendPort = Get-AvailablePort -Candidates @(3000, 3001, 3002, 3003, 3004, 3005)
$FrontendUrl = "http://127.0.0.1:$FrontendPort"
$BackendUrl = "http://127.0.0.1:$BackendPort"

if (-not (Test-Path -LiteralPath $FrontendPackage)) {
    throw "frontend/package.json was not found. Run this script from the project root."
}

if (-not (Test-Path -LiteralPath $NodeModules)) {
    Write-Host "Notice: frontend/node_modules does not exist. For the first run, execute: cd frontend; npm install" -ForegroundColor Yellow
}

$RootQuoted = Quote-LiteralPath $Root
$FrontendQuoted = Quote-LiteralPath $Frontend
$BackendCommand = "Set-Location -LiteralPath $RootQuoted; python -m uvicorn app.main:app --host 127.0.0.1 --port $BackendPort --reload"
$FrontendCommand = "Set-Location -LiteralPath $FrontendQuoted; `$env:VITE_BACKEND_URL='$BackendUrl'; npm run dev -- --host 127.0.0.1 --port $FrontendPort --strictPort"

Write-Host "Smart Manufacturing Platform Dev Launcher" -ForegroundColor Cyan
Write-Host "Backend: $BackendUrl"
Write-Host "Frontend: $FrontendUrl"
Write-Host ""

if ($DryRun) {
    Write-Host "[DryRun] Backend command:"
    Write-Host $BackendCommand
    Write-Host "[DryRun] Frontend command:"
    Write-Host $FrontendCommand
    exit 0
}

Start-Process -FilePath "powershell" -ArgumentList @(
    "-NoExit",
    "-ExecutionPolicy",
    "Bypass",
    "-Command",
    $BackendCommand
)

Start-Sleep -Seconds 2

Start-Process -FilePath "powershell" -ArgumentList @(
    "-NoExit",
    "-ExecutionPolicy",
    "Bypass",
    "-Command",
    $FrontendCommand
)

Write-Host "Backend and frontend service windows have been opened. Keep them running." -ForegroundColor Green
Write-Host "Open in browser: $FrontendUrl"
