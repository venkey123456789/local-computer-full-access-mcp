$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (-not (Test-Path ".venv\Scripts\python.exe")) { throw "Run INSTALL_WINDOWS.bat first." }
$env:PC_MCP_TRANSPORT = "stdio"
& ".venv\Scripts\python.exe" -m pc_mcp.server
