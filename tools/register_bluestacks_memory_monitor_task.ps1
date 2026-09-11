param(
    [string]$TaskName = "PNC BlueStacks Memory Monitor",
    [string]$ConfigPath = "config\accounts.yaml"
)

$ErrorActionPreference = "Stop"

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$resolvedConfig = (Resolve-Path -LiteralPath $ConfigPath).Path
$quotedConfig = '"' + $resolvedConfig + '"'
$pythonExecutable = & py -c "import sys; print(sys.executable)"
if ($LASTEXITCODE -ne 0 -or -not $pythonExecutable) {
    throw "Could not resolve the Python interpreter for the monitor task."
}
$windowlessPython = Join-Path (Split-Path -Parent $pythonExecutable.Trim()) "pythonw.exe"
if (-not (Test-Path -LiteralPath $windowlessPython -PathType Leaf)) {
    throw "A windowless Python interpreter is required for the monitor task."
}
# Supervise Python itself. Stopping a task whose action is a PowerShell/py
# wrapper can leave the actual monitor orphaned after its parent exits.
$actionArguments = "-m pnc_automation.bluestacks_management monitor --config $quotedConfig --watch"
$action = New-ScheduledTaskAction `
    -Execute $windowlessPython `
    -Argument $actionArguments `
    -WorkingDirectory $repositoryRoot
$trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable:$false `
    -WakeToRun:$false `
    -MultipleInstances IgnoreNew `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero)
$principal = New-ScheduledTaskPrincipal `
    -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType Interactive `
    -RunLevel Limited
$task = New-ScheduledTask -Action $action -Trigger $trigger -Settings $settings -Principal $principal
Register-ScheduledTask -TaskName $TaskName -InputObject $task -Force | Out-Null
Write-Output "Registered '$TaskName' with startup supervision, no overlap, and bounded failure restart."
