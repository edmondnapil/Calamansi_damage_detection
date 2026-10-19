# One-time setup on a new computer (Windows).
#   1. finds Python 3.12 (TensorFlow 2.19 does not support 3.13+)
#   2. creates backend\.venv and installs the exact tested package versions
#   3. installs frontend packages and builds the web interface
#   4. checks that the trained models and the .env file are present
#
# Run by double-clicking setup.bat, or:
#   powershell -ExecutionPolicy Bypass -File .\setup.ps1

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"

function Step($msg) { Write-Host ""; Write-Host "== $msg" -ForegroundColor Cyan }
function Fail($msg) { Write-Host ""; Write-Host "SETUP FAILED: $msg" -ForegroundColor Red; exit 1 }

# ---------------------------------------------------------------- folder path length
# Windows limits most paths to 260 characters. Frontend packages need up to ~105
# characters below this folder, and TensorFlow up to ~190 (which only works when
# Windows "long paths" are enabled; they are off by default on many computers).
Step "Checking the folder location"
$longPaths = $false
try {
    $longPaths = (Get-ItemProperty "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" -Name LongPathsEnabled -ErrorAction Stop).LongPathsEnabled -eq 1
} catch {}
$short = "C:\Calamansi-Leaf-Detection"
if ($root.Length -gt 150) {
    Fail ("This folder's path is too long ($($root.Length) characters):`n    $root`n" +
          "Move the Calamansi-Leaf-Detection folder to a short location such as $short and run setup again.")
}
if (-not $longPaths -and $root.Length -gt 68) {
    Fail ("Windows long paths are disabled and this folder's path is $($root.Length) characters long, so TensorFlow cannot be installed here.`n" +
          "Either move the folder to a short location such as $short (recommended), or enable long paths once by running`n" +
          "PowerShell as Administrator:`n" +
          "    New-ItemProperty -Path HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem -Name LongPathsEnabled -Value 1 -PropertyType DWORD -Force`n" +
          "then run setup again.")
}
Write-Host "Folder OK ($($root.Length) characters; Windows long paths $(if ($longPaths) {'enabled'} else {'disabled'}))"

# ---------------------------------------------------------------- Python 3.12
Step "Looking for Python 3.12"
$python = $null
$candidates = @(
    (Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"),
    "C:\Program Files\Python312\python.exe"
)
foreach ($c in $candidates) { if (Test-Path $c) { $python = $c; break } }
if (-not $python -and (Get-Command py -ErrorAction SilentlyContinue)) {
    try {
        $p = & py -3.12 -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $p) { $python = $p.Trim() }
    } catch {}
}
if (-not $python) {
    Fail ("Python 3.12 was not found. Install it with:`n" +
          "    winget install --id Python.Python.3.12 -e --scope user`n" +
          "or from https://www.python.org/downloads/release/python-31210/ , then run setup again.")
}
Write-Host "Using $python ($(& $python --version))"

# ---------------------------------------------------------------- Node.js
Step "Looking for Node.js"
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    Fail "Node.js was not found. Install the LTS version from https://nodejs.org (or: winget install OpenJS.NodeJS.LTS), then run setup again."
}
Write-Host "Node $(node --version), npm $(npm --version)"

# ---------------------------------------------------------------- backend
Step "Creating the Python virtual environment (backend\.venv)"
$venvPy = Join-Path $backend ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
    & $python -m venv (Join-Path $backend ".venv")
    if ($LASTEXITCODE -ne 0) { Fail "Could not create the virtual environment." }
}

Step "Installing Python packages (TensorFlow is large; this can take 5-15 minutes)"
& $venvPy -m pip install --upgrade pip --quiet
& $venvPy -m pip install -r (Join-Path $backend "requirements-lock.txt")
if ($LASTEXITCODE -ne 0) { Fail "pip install failed. Check your internet connection and run setup again." }

# ---------------------------------------------------------------- frontend
Step "Installing frontend packages and building the web interface"
Push-Location $frontend
try {
    npm ci --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) { Fail "npm ci failed." }
    npm run build
    if ($LASTEXITCODE -ne 0) { Fail "npm run build failed." }
} finally {
    Pop-Location
}

# ---------------------------------------------------------------- checks
Step "Checking trained models"
$models = @("calamansi_mobilenetv2.keras", "model_metadata.json", "leaf_gate.npz",
            "leaf_gate_cnn.keras", "leaf_gate_extractor.keras")
$missing = $models | Where-Object { -not (Test-Path (Join-Path $backend "models\$_")) }
if ($missing) {
    Write-Host "Missing model files: $($missing -join ', ')" -ForegroundColor Yellow
    Write-Host "Copy the backend\models folder from the original computer, or retrain (see README section 4.3)." -ForegroundColor Yellow
} else {
    Push-Location $backend
    try {
        & $venvPy -c "from predict import Predictor; p = Predictor(); print('Models load OK:', p.version)"
        if ($LASTEXITCODE -ne 0) { Fail "The model files exist but could not be loaded." }
    } finally {
        Pop-Location
    }
}

Step "Checking backend\.env (Supabase settings)"
$envFile = Join-Path $backend ".env"
if (-not (Test-Path $envFile)) {
    Copy-Item (Join-Path $backend ".env.example") $envFile
    Write-Host "No backend\.env was found, so a blank one was created." -ForegroundColor Yellow
    Write-Host "Until you copy the real .env from the original computer (or fill in SUPABASE_URL and" -ForegroundColor Yellow
    Write-Host "SUPABASE_SERVICE_ROLE_KEY), results are saved only on this computer (local SQLite)." -ForegroundColor Yellow
} else {
    Write-Host "backend\.env found."
}

Write-Host ""
Write-Host "Setup complete. Double-click start.bat to run the app." -ForegroundColor Green
