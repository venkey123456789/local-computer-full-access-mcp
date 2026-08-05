$ErrorActionPreference = "Continue"
Set-Location $PSScriptRoot

$stopped = @()
foreach ($name in @("server.pid", "tunnel.pid")) {
    $pidFile = Join-Path $PSScriptRoot ".data\$name"
    if (-not (Test-Path $pidFile)) { continue }
    $savedPid = (Get-Content $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
    if ($savedPid -match '^\d+$') {
        $process = Get-Process -Id ([int]$savedPid) -ErrorAction SilentlyContinue
        if ($process) {
            Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
            $stopped += $process.Id
        }
    }
    Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
}

# Also stop cloudflared processes whose command line points at this package's port.
try {
    $port = "8765"
    if (Test-Path ".env") {
        $line = Get-Content ".env" | Where-Object { $_ -match '^PC_MCP_PORT=' } | Select-Object -First 1
        if ($line) { $port = $line.Split('=', 2)[1].Trim() }
    }
    Get-CimInstance Win32_Process -Filter "Name='cloudflared.exe'" | Where-Object {
        $_.CommandLine -like "*--url*127.0.0.1:$port*" -or $_.CommandLine -like "*--url*localhost:$port*"
    } | ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        $stopped += $_.ProcessId
    }
} catch {}

if ($stopped.Count -gt 0) {
    Write-Host "Stopped MCP/tunnel process IDs: $($stopped -join ', ')"
} else {
    Write-Host "No running MCP/tunnel process from this package was found."
}
