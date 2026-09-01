$ErrorActionPreference = "Continue"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$routinePath = Join-Path $repositoryRoot "scripts\routines\daily_castle_maintenance.yaml"
$configPath = Join-Path $repositoryRoot "config\accounts.yaml"
$failed = $false

Push-Location $repositoryRoot
try {
    & py -m pnc_automation.app.entrypoints.cli run `
        --config $configPath `
        --account testing `
        --script $routinePath `
        --castle-ref main `
        --castle-ref hopeful_npc_k323
    if ($LASTEXITCODE -ne 0) {
        $failed = $true
    }

    & py -m pnc_automation.app.entrypoints.cli run `
        --config $configPath `
        --account serious_stuff `
        --script $routinePath `
        --castle-ref main
    if ($LASTEXITCODE -ne 0) {
        $failed = $true
    }
}
finally {
    Pop-Location
}

if ($failed) {
    exit 1
}
exit 0
