$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (Test-Path $VenvPython) {
    & $VenvPython -m app.auth_server
} else {
    python -m app.auth_server
}
