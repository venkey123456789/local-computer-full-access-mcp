$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (Get-Command py -ErrorAction SilentlyContinue) {
    $pythonCommand = "py"
    $pythonPrefix = @("-3")
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $pythonCommand = "python"
    $pythonPrefix = @()
} else {
    throw "Python 3.10 or newer is required. Install Python, then run INSTALL_WINDOWS.bat again."
}

Write-Host "Creating the virtual environment..."
& $pythonCommand @pythonPrefix -c "import sys; assert sys.version_info >= (3,10), sys.version" 2>$null
if ($LASTEXITCODE -ne 0) { throw "Python 3.10 or newer is required." }

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    & $pythonCommand @pythonPrefix -m venv .venv
}

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install "mcp[cli]>=2,<3" "psutil>=6.1,<8" pytest
if ($LASTEXITCODE -ne 0) { throw "Python dependency installation failed." }

if (-not (Test-Path ".env")) {
    $bytes = New-Object byte[] 32
    # Windows PowerShell 5.1 runs on .NET Framework, where the newer static Fill() API
    # is not available. Create() + instance GetBytes() works on both Windows
    # PowerShell 5.1 and PowerShell 7+.
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $rng.GetBytes($bytes)
    } finally {
        if ($null -ne $rng) { $rng.Dispose() }
    }
    $secret = [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+','-').Replace('/','_')
    @"
PC_MCP_FULL_ACCESS=1
PC_MCP_TRANSPORT=streamable-http
PC_MCP_HOST=127.0.0.1
PC_MCP_PORT=8765
PC_MCP_ENDPOINT_SECRET=$secret
PC_MCP_ALLOWED_ROOTS=$env:USERPROFILE
PC_MCP_MAX_READ_BYTES=2000000
PC_MCP_MAX_WRITE_BYTES=10000000
PC_MCP_MAX_COMMAND_OUTPUT_CHARS=120000
PC_MCP_MAX_COMMAND_TIMEOUT_SECONDS=900
PC_MCP_ALLOW_NETWORK_BIND=0
"@ | Set-Content -Path ".env" -Encoding UTF8
    Write-Host "Created .env with full access enabled and a random secret endpoint."
} else {
    Write-Host ".env already exists; it was not changed."
}

if (-not (Get-Command cloudflared -ErrorAction SilentlyContinue)) {
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Host "Installing cloudflared for the HTTPS tunnel..."
        winget install --id Cloudflare.cloudflared --exact --accept-package-agreements --accept-source-agreements
    } else {
        Write-Warning "cloudflared was not found and winget is unavailable. Install cloudflared manually before using START_CHATGPT.bat."
    }
}

Write-Host "Checking MCP SDK integration..."
& $venvPython -c "from mcp.server import MCPServer; from mcp.server.transport_security import TransportSecuritySettings; import pc_mcp.server; print('MCP SDK integration import OK')"
if ($LASTEXITCODE -ne 0) { throw "The installed MCP SDK is incompatible with this server." }

Write-Host "Running tests..."
& $venvPython -m pytest -q
if ($LASTEXITCODE -ne 0) { throw "Tests failed." }

Write-Host ""
Write-Host "Installation complete."
Write-Host "For ChatGPT: run START_CHATGPT.bat"
Write-Host "For a local stdio MCP host: run START_STDIO.bat"
