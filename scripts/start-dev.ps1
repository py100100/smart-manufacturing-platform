param(
    [switch]$DryRun,
    [switch]$NoBrowser
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

function Wait-HttpReady {
    param(
        [string]$Url,
        [int]$TimeoutSeconds = 45
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2 | Out-Null
            return $true
        }
        catch {
            Start-Sleep -Seconds 1
        }
    }

    return $false
}

function Open-Browser {
    param([string]$Url)

    try {
        Start-Process $Url | Out-Null
        return $true
    }
    catch {
        Write-Host "Could not open browser automatically: $($_.Exception.Message)" -ForegroundColor Yellow
        return $false
    }
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $ScriptDir
$Frontend = Join-Path $Root "frontend"
$FrontendPackage = Join-Path $Frontend "package.json"
$NodeModules = Join-Path $Frontend "node_modules"
$RunDir = Join-Path $Root ".runlogs"
$StateFile = Join-Path $RunDir "dev-services.json"
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

if (-not (Test-Path -LiteralPath $RunDir)) {
    New-Item -ItemType Directory -Path $RunDir | Out-Null
}

$RootQuoted = Quote-LiteralPath $Root
$FrontendQuoted = Quote-LiteralPath $Frontend
$BackendCommand = "`$Host.UI.RawUI.WindowTitle = 'Smart Manufacturing Backend'; Set-Location -LiteralPath $RootQuoted; python -m uvicorn app.main:app --host 127.0.0.1 --port $BackendPort --reload"
$FrontendCommand = "`$Host.UI.RawUI.WindowTitle = 'Smart Manufacturing Frontend'; Set-Location -LiteralPath $FrontendQuoted; `$env:VITE_BACKEND_URL='$BackendUrl'; npm run dev -- --host 127.0.0.1 --port $FrontendPort --strictPort"

Write-Host "Smart Manufacturing Platform Dev Launcher" -ForegroundColor Cyan
Write-Host "Backend: $BackendUrl"
Write-Host "Frontend: $FrontendUrl"
Write-Host "Run state: $StateFile"
Write-Host ""

if ($DryRun) {
    Write-Host "[DryRun] Backend command:"
    Write-Host $BackendCommand
    Write-Host "[DryRun] Frontend command:"
    Write-Host $FrontendCommand
    if (-not $NoBrowser) {
        Write-Host "[DryRun] Browser will open: $FrontendUrl"
    }
    exit 0
}

$BackendProcess = Start-Process -FilePath "powershell" -ArgumentList @(
    "-NoExit",
    "-ExecutionPolicy",
    "Bypass",
    "-Command",
    $BackendCommand
) -PassThru

Start-Sleep -Seconds 2

$FrontendProcess = Start-Process -FilePath "powershell" -ArgumentList @(
    "-NoExit",
    "-ExecutionPolicy",
    "Bypass",
    "-Command",
    $FrontendCommand
) -PassThru

$State = [ordered]@{
    root = $Root
    backend = [ordered]@{
        pid = $BackendProcess.Id
        port = $BackendPort
        url = $BackendUrl
    }
    frontend = [ordered]@{
        pid = $FrontendProcess.Id
        port = $FrontendPort
        url = $FrontendUrl
    }
    started_at = (Get-Date).ToString("o")
}
$State | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $StateFile -Encoding UTF8

Write-Host "Backend and frontend service windows have been opened. Keep them running." -ForegroundColor Green
Write-Host "Open in browser: $FrontendUrl"

if (-not $NoBrowser) {
    Write-Host "Waiting for frontend before opening browser..."
    if (Wait-HttpReady -Url $FrontendUrl) {
        if (Open-Browser -Url $FrontendUrl) {
            Write-Host "Browser opened: $FrontendUrl" -ForegroundColor Green
        }
    }
    else {
        Write-Host "Frontend is still starting. Open manually when ready: $FrontendUrl" -ForegroundColor Yellow
    }
}
Write-Host "To stop: double-click 停止项目.bat in the project root."
