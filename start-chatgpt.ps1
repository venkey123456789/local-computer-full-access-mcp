$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    throw "Not installed yet. Run INSTALL_WINDOWS.bat first."
}
if (-not (Test-Path ".env")) {
    throw ".env is missing. Run INSTALL_WINDOWS.bat first."
}

# Load .env into this process.
Get-Content ".env" | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith('#') -and $line.Contains('=')) {
        $parts = $line.Split('=', 2)
        [Environment]::SetEnvironmentVariable($parts[0].Trim(), $parts[1].Trim(), 'Process')
    }
}

$env:PC_MCP_TRANSPORT = "streamable-http"
$hostName = if ($env:PC_MCP_HOST) { $env:PC_MCP_HOST } else { "127.0.0.1" }
$port = if ($env:PC_MCP_PORT) { $env:PC_MCP_PORT } else { "8765" }
$secret = $env:PC_MCP_ENDPOINT_SECRET
if (-not $secret) { throw "PC_MCP_ENDPOINT_SECRET is missing from .env" }

$cloudflared = (Get-Command cloudflared -ErrorAction SilentlyContinue).Source
if (-not $cloudflared) {
    $candidates = @(
        "$env:ProgramFiles\cloudflared\cloudflared.exe",
        "$env:LOCALAPPDATA\Microsoft\WinGet\Links\cloudflared.exe"
    )
    $cloudflared = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
}
if (-not $cloudflared) {
    throw "cloudflared was not found. Re-run INSTALL_WINDOWS.bat or install Cloudflare cloudflared."
}

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$stdoutLog = Join-Path $PSScriptRoot ".data\server-stdout.log"
$stderrLog = Join-Path $PSScriptRoot ".data\server-stderr.log"
$serverPidFile = Join-Path $PSScriptRoot ".data\server.pid"
$tunnelPidFile = Join-Path $PSScriptRoot ".data\tunnel.pid"
New-Item -ItemType Directory -Force -Path (Split-Path $stdoutLog) | Out-Null
Remove-Item $serverPidFile, $tunnelPidFile -Force -ErrorAction SilentlyContinue

$server = Start-Process -FilePath $python -ArgumentList "-m", "pc_mcp.server" -WorkingDirectory $PSScriptRoot -RedirectStandardOutput $stdoutLog -RedirectStandardError $stderrLog -PassThru
Start-Sleep -Seconds 2
if ($server.HasExited) {
    Get-Content $stderrLog -ErrorAction SilentlyContinue
    throw "The MCP server exited during startup."
}

Set-Content -Path $serverPidFile -Value $server.Id -Encoding Ascii
Write-Host "Local MCP server PID: $($server.Id)"
Write-Host "Local endpoint: http://${hostName}:$port/mcp/$secret"
Write-Host "Starting a free HTTPS test tunnel. Keep this window open."
Write-Host ""

$printedEndpoint = $false
$previousErrorActionPreference = $ErrorActionPreference
try {
    # Windows PowerShell 5.1 converts native stderr output into ErrorRecords.
    # cloudflared writes normal INF logs to stderr, so Stop would abort startup.
    $ErrorActionPreference = "Continue"

    # The MCP SDK validates the Host header for DNS-rebinding protection.
    # Rewrite Cloudflare's public Host header to the loopback origin.
    & $cloudflared tunnel --no-autoupdate --url "http://${hostName}:$port" --http-host-header "${hostName}:$port" 2>&1 | ForEach-Object {
        $line = $_.ToString()
        Write-Host $line
        if (-not $printedEndpoint -and $line -match 'https://[a-zA-Z0-9-]+\.trycloudflare\.com') {
            $baseUrl = $Matches[0]
            Write-Host ""
            Write-Host "==============================================================="
            Write-Host "CHATGPT MCP ENDPOINT:"
            Write-Host "$baseUrl/mcp/$secret"
            Write-Host "==============================================================="
            Write-Host "Use No authentication when ChatGPT asks for the auth method."
            Write-Host "Do not share this endpoint. It controls your computer."
            Write-Host ""
            $printedEndpoint = $true
        }
    }
}
finally {
    $ErrorActionPreference = $previousErrorActionPreference
    if ($server -and -not $server.HasExited) {
        Stop-Process -Id $server.Id -Force -ErrorAction SilentlyContinue
    }
    Remove-Item $serverPidFile, $tunnelPidFile -Force -ErrorAction SilentlyContinue
}
