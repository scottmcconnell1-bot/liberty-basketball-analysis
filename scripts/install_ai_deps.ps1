# Install PyTorch + OpenCV + Ultralytics for Liberty AI analysis on Windows.
# Run from the repo root in PowerShell:
#   .\scripts\install_ai_deps.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

function Write-Step([string]$Message) {
    Write-Host "[liberty-ai] $Message" -ForegroundColor Cyan
}

function Find-Python312 {
    $candidates = @(
        @("py", "-3.12"),
        @("py", "-3.13"),
        @("$Root\.venv\Scripts\python.exe"),
        @("python")
    )
    foreach ($cmd in $candidates) {
        if ($cmd[0] -ne "$Root\.venv\Scripts\python.exe" -and -not (Get-Command $cmd[0] -ErrorAction SilentlyContinue)) {
            continue
        }
        if ($cmd[0] -eq "$Root\.venv\Scripts\python.exe" -and -not (Test-Path $cmd[0])) {
            continue
        }
        try {
            $versionText = & $cmd[0] @($cmd[1..($cmd.Length - 1)]) -c "import sys; print('.'.join(map(str, sys.version_info[:3])))"
            if ($LASTEXITCODE -ne 0) { continue }
            $parts = $versionText.Trim().Split(".") | ForEach-Object { [int]$_ }
            $major, $minor = $parts[0], $parts[1]
            if ($major -eq 3 -and $minor -in 12, 13) {
                return ,$cmd
            }
            Write-Host "[liberty-ai] Skipping Python $versionText (need 3.12 or 3.13)" -ForegroundColor DarkYellow
        } catch {
            continue
        }
    }
    return $null
}

Write-Step "Checking Python version (must be 3.12 or 3.13, 64-bit)..."
$pythonCmd = Find-Python312
if (-not $pythonCmd) {
    Write-Host ""
    Write-Host "No compatible Python found." -ForegroundColor Red
    Write-Host "Install Python 3.12, then recreate the venv:" -ForegroundColor Yellow
    Write-Host "  winget install Python.Python.3.12"
    Write-Host "  py -3.12 -m venv .venv"
    Write-Host "  .\.venv\Scripts\Activate.ps1"
    Write-Host "  .\scripts\install_ai_deps.ps1"
    exit 1
}

$pythonLabel = ($pythonCmd -join " ")
Write-Step "Using $pythonLabel"

& $pythonCmd[0] @($pythonCmd[1..($pythonCmd.Length - 1)]) -c "import struct; assert struct.calcsize('P') == 8, '64-bit Python required'"
if ($LASTEXITCODE -ne 0) {
    Write-Host "64-bit Python is required for PyTorch." -ForegroundColor Red
    exit 1
}

Write-Step "Upgrading pip..."
& $pythonCmd[0] @($pythonCmd[1..($pythonCmd.Length - 1)]) -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Step "Installing PyTorch CPU wheels..."
& $pythonCmd[0] @($pythonCmd[1..($pythonCmd.Length - 1)]) -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
if ($LASTEXITCODE -ne 0) {
    Write-Host "[liberty-ai] CPU index install failed; trying default PyPI..." -ForegroundColor Yellow
    & $pythonCmd[0] @($pythonCmd[1..($pythonCmd.Length - 1)]) -m pip install torch torchvision
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

Write-Step "Installing OpenCV, Ultralytics, and container AI deps..."
& $pythonCmd[0] @($pythonCmd[1..($pythonCmd.Length - 1)]) -m pip install -r requirements.docker.txt
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Step "Verifying imports..."
& $pythonCmd[0] @($pythonCmd[1..($pythonCmd.Length - 1)]) -c "import cv2; import ultralytics; import torch; print('OK: torch', torch.__version__, 'cv2', cv2.__version__)"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "AI packages installed. Restart the Liberty app, then check Settings -> Runtime." -ForegroundColor Green
