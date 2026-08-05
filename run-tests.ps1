$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (-not (Test-Path ".venv\Scripts\python.exe")) { throw "Run INSTALL_WINDOWS.bat first." }
& ".venv\Scripts\python.exe" -m pytest -q
