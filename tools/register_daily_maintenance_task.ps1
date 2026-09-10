param(
    [string]$TaskName = "PNC Daily Castle Maintenance",
    [string]$DailyConfigPath = "config\daily_maintenance.yaml",
    [Parameter(Mandatory = $true)]
    [string]$AcknowledgementPath,
    [int]$ExecutionTimeLimitHours = 4
)

$ErrorActionPreference = "Stop"
if ((Get-TimeZone).Id -ne "Eastern Standard Time") {
    throw "Task registration requires Windows timezone 'Eastern Standard Time'."
}
if ($ExecutionTimeLimitHours -le 0) {
    throw "ExecutionTimeLimitHours must be positive."
}

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$wrapperPath = Join-Path $PSScriptRoot "run_daily_maintenance.ps1"
$resolvedDailyConfig = (Resolve-Path -LiteralPath $DailyConfigPath).Path
$resolvedAcknowledgement = (Resolve-Path -LiteralPath $AcknowledgementPath).Path
$credential = Get-Credential -Message "Windows account used for background PNC maintenance"
$quotedWrapper = '"' + $wrapperPath + '"'
$quotedDailyConfig = '"' + $resolvedDailyConfig + '"'
$quotedAcknowledgement = '"' + $resolvedAcknowledgement + '"'
$actionArguments = (
    "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File $quotedWrapper " +
    "-DailyConfigPath $quotedDailyConfig -AcknowledgementPath $quotedAcknowledgement"
)
$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument $actionArguments `
    -WorkingDirectory $repositoryRoot
$trigger = New-ScheduledTaskTrigger -Daily -At "02:00"
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable:$false `
    -WakeToRun:$false `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours $ExecutionTimeLimitHours)
$principal = New-ScheduledTaskPrincipal `
    -UserId $credential.UserName `
    -LogonType Password `
    -RunLevel Limited
$task = New-ScheduledTask -Action $action -Trigger $trigger -Settings $settings -Principal $principal
Register-ScheduledTask `
    -TaskName $TaskName `
    -InputObject $task `
    -User $credential.UserName `
    -Password $credential.GetNetworkCredential().Password `
    -Force | Out-Null
Disable-ScheduledTask -TaskName $TaskName | Out-Null

$registered = Get-ScheduledTask -TaskName $TaskName
if ($registered.State -ne "Disabled") {
    throw "The daily-maintenance task was not left disabled."
}
Write-Output "Registered '$TaskName' disabled with a local 02:00 boundary and no catch-up/wake/overlap."
