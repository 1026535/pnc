param(
    [string]$ConfigPath = "config\accounts.yaml",
    [string]$DailyConfigPath = "config\daily_maintenance.yaml",
    [Parameter(Mandatory = $true)]
    [string]$AcknowledgementPath
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$mutex = [System.Threading.Mutex]::new($false, "Local\PNC-Daily-Castle-Maintenance")
$ownsMutex = $false

try {
    $ownsMutex = $mutex.WaitOne(0)
    if (-not $ownsMutex) {
        Write-Error "Another daily-maintenance process already owns the process lock."
        exit 2
    }
    if ((Get-TimeZone).Id -ne "Eastern Standard Time") {
        Write-Error "Daily maintenance requires Windows timezone 'Eastern Standard Time'."
        exit 3
    }
    $resolvedAcknowledgementPath = (Resolve-Path -LiteralPath $AcknowledgementPath).Path
    $acknowledgements = @(Get-Content -LiteralPath $resolvedAcknowledgementPath -Raw | ConvertFrom-Json)
    if ($acknowledgements.Count -eq 0) {
        Write-Error "The acknowledgement file must contain a non-empty JSON array."
        exit 4
    }
    $arguments = @(
        "-m", "pnc_automation.app.entrypoints.cli", "daily-maintenance",
        "--config", $ConfigPath,
        "--daily-config", $DailyConfigPath
    )
    foreach ($acknowledgement in $acknowledgements) {
        $arguments += "--acknowledgement"
        $arguments += ($acknowledgement | ConvertTo-Json -Compress)
    }
    Push-Location $repositoryRoot
    try {
        & py @arguments
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
