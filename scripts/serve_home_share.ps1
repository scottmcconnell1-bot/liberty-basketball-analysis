# Serve the home-laptop file share on this machine's Tailscale address only.
# The public coach link stays a proxy to port 8080. This script does not turn on Funnel.
# The laptop has to stay on while Jason or Brad copies the folder.

$ErrorActionPreference = "Stop"

$ip = (& tailscale ip -4 | Select-Object -First 1).Trim()
if ($ip -notmatch "^100\.") {
    throw "No Tailscale address. Refusing to listen on every interface."
}

$root = Join-Path $env:USERPROFILE "LibertyData\jason-brad-share\for-drive"
if (-not (Test-Path -LiteralPath $root)) {
    throw "Share folder is not on this machine: $root"
}

$port = 8091
$python = Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    $python = "python"
}

Write-Output "Tailnet only: http://${ip}:${port}/"
Write-Output "Folder: $root"
Write-Output "The public coach link is not this folder."

& $python -m http.server $port --bind $ip --directory $root
