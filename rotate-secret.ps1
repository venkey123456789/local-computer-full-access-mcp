$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".env")) {
    throw ".env is missing. Run INSTALL_WINDOWS.bat first."
}

$bytes = New-Object byte[] 32
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
try {
    $rng.GetBytes($bytes)
} finally {
    if ($null -ne $rng) { $rng.Dispose() }
}
$secret = [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+','-').Replace('/','_')

$lines = Get-Content ".env"
$found = $false
$updated = foreach ($line in $lines) {
    if ($line -match '^PC_MCP_ENDPOINT_SECRET=') {
        $found = $true
        "PC_MCP_ENDPOINT_SECRET=$secret"
    } else {
        $line
    }
}
if (-not $found) {
    $updated += "PC_MCP_ENDPOINT_SECRET=$secret"
}
$updated | Set-Content -Path ".env" -Encoding UTF8
Write-Host "Endpoint secret rotated successfully."
Write-Host "Run START_CHATGPT.bat again."
