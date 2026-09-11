param(
    [string]$ConfigPath = "config\accounts.yaml"
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$mutex = [System.Threading.Mutex]::new($false, "Local\PNC-BlueStacks-Memory-Monitor")
$ownsMutex = $false

try {
    $ownsMutex = $mutex.WaitOne(0)
    if (-not $ownsMutex) {
        Write-Error "Another BlueStacks memory-monitor process already owns the process lock."
        exit 2
    }
    Push-Location $repositoryRoot
    try {
        & py -m pnc_automation.bluestacks_management monitor --config $ConfigPath --watch
        exit $LASTEXITCODE
    }
    finally {
        Pop-Location
    }
}
finally {
    if ($ownsMutex) {
        $mutex.ReleaseMutex()
    }
    $mutex.Dispose()
}
