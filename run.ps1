$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (Test-Path $VenvPython) {
    & $VenvPython -m app.main
} else {
    python -m app.main
}
