param(
    [switch]$DryRun
)

$ErrorActionPreference = "Continue"

function Stop-ProcessTree {
    param([int]$ProcessId)

    if ($ProcessId -le 0) {
        return
    }

    $children = @()
    try {
        $children = Get-CimInstance Win32_Process -Filter "ParentProcessId = $ProcessId" -ErrorAction Stop
    }
    catch {
        $children = @()
    }

    foreach ($child in $children) {
        Stop-ProcessTree -ProcessId ([int]$child.ProcessId)
    }

    if (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue) {
        if ($DryRun) {
            Write-Host "[DryRun] Would stop PID $ProcessId"
        }
        else {
            Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
            Write-Host "Stopped PID $ProcessId"
        }
    }
}

function Stop-ProjectListener {
    param(
        [int]$Port,
        [string]$Root
    )

    if ($Port -le 0) {
        return
    }

    $listeners = @()
    try {
        $listeners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    }
    catch {
        $listeners = @()
    }

    foreach ($listener in $listeners) {
        $ownerPid = [int]$listener.OwningProcess
        $commandLine = ""
        try {
            $proc = Get-CimInstance Win32_Process -Filter "ProcessId = $ownerPid" -ErrorAction Stop
            $commandLine = [string]$proc.CommandLine
        }
        catch {
            $commandLine = ""
        }

        if ($commandLine -and $commandLine.Contains($Root)) {
            Stop-ProcessTree -ProcessId $ownerPid
        }
    }
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $ScriptDir
$RunDir = Join-Path $Root ".runlogs"
$StateFile = Join-Path $RunDir "dev-services.json"

Write-Host "Smart Manufacturing Platform Stopper" -ForegroundColor Cyan

if (-not (Test-Path -LiteralPath $StateFile)) {
    Write-Host "No run state found. Nothing to stop." -ForegroundColor Yellow
    exit 0
}

$State = Get-Content -LiteralPath $StateFile -Raw | ConvertFrom-Json
$StateRoot = if ($State.root) { [string]$State.root } else { $Root }

Stop-ProcessTree -ProcessId ([int]$State.frontend.pid)
Stop-ProcessTree -ProcessId ([int]$State.backend.pid)
Stop-ProjectListener -Port ([int]$State.frontend.port) -Root $StateRoot
Stop-ProjectListener -Port ([int]$State.backend.port) -Root $StateRoot

if (-not $DryRun) {
    Remove-Item -LiteralPath $StateFile -Force -ErrorAction SilentlyContinue
}

Write-Host "Stop completed." -ForegroundColor Green
