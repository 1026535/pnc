@echo off
setlocal EnableExtensions

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "REPO_ROOT=%%~fI"
set "OUTPUT_DIR=%REPO_ROOT%\selector_discovery_output"
set "AUTO_APPLY=0"
set "DISCOVERY_ARGS="

if /I "%~1"=="--apply" (
    set "AUTO_APPLY=1"
    shift
)

:collect_args
if "%~1"=="" goto args_ready
set "DISCOVERY_ARGS=%DISCOVERY_ARGS% "%~1""
shift
goto collect_args

:args_ready
if not defined DISCOVERY_ARGS (
    echo Usage:
    echo   %~nx0 [--apply] ^<discover args...^>
    echo Example:
    echo   %~nx0 --account "BlueStacks App Player 1" --settle-home-city --probe-selector PNC_BOTTOM_NAV_BAG
    echo   %~nx0 --apply --account "BlueStacks App Player 1" --settle-home-city --probe-selector PNC_BOTTOM_NAV_BAG
    exit /b 1
)

echo [1/3] Running selector discovery...
py -3 "%SCRIPT_DIR%discover_selector_registry.py" --output-dir "%OUTPUT_DIR%" %DISCOVERY_ARGS%
if errorlevel 1 exit /b %errorlevel%

for /f "usebackq delims=" %%I in (`powershell -NoProfile -Command "(Get-ChildItem -Path '%OUTPUT_DIR%' -Filter '*_report.yaml' | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1 -ExpandProperty FullName)"`) do set "LATEST_REPORT=%%I"
for /f "usebackq delims=" %%I in (`powershell -NoProfile -Command "(Get-ChildItem -Path '%OUTPUT_DIR%' -Filter '*_spec.yaml' | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1 -ExpandProperty FullName)"`) do set "LATEST_SPEC=%%I"

if not defined LATEST_REPORT (
    echo Failed to resolve the latest discovery report.
    exit /b 1
)
if not defined LATEST_SPEC (
    echo Failed to resolve the latest discovery spec.
    exit /b 1
)

echo report=%LATEST_REPORT%
echo spec=%LATEST_SPEC%

echo [2/3] Validating the generated spec with the offline updater...
py -3 "%SCRIPT_DIR%update_selector_registry.py" --spec "%LATEST_SPEC%" --dry-run
if errorlevel 1 exit /b %errorlevel%

if "%AUTO_APPLY%"=="0" (
    echo [3/3] Apply step skipped. Re-run with --apply after reviewing the report/spec.
    exit /b 0
)

echo [3/3] Applying the reviewed spec...
py -3 "%SCRIPT_DIR%update_selector_registry.py" --spec "%LATEST_SPEC%"
exit /b %errorlevel%
