# Starts the app (backend + built web interface) on http://localhost:8000
# and opens it in the browser. Keep this window open while using the app;
# press Ctrl+C (or close the window) to stop it.
#
# Run by double-clicking start.bat, or:
#   powershell -ExecutionPolicy Bypass -File .\start.ps1

$root = $PSScriptRoot
$backend = Join-Path $root "backend"
$venvPy = Join-Path $backend ".venv\Scripts\python.exe"
$url = "http://localhost:8000"

if (-not (Test-Path $venvPy)) {
    Write-Host "The app is not set up on this computer yet. Double-click setup.bat first." -ForegroundColor Red
    Read-Host "Press Enter to close"
    exit 1
}
if (-not (Test-Path (Join-Path $root "frontend\dist\index.html"))) {
    Write-Host "The web interface is not built yet. Run setup.bat (or: cd frontend; npm run build)." -ForegroundColor Red
    Read-Host "Press Enter to close"
    exit 1
}
$busy = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if ($busy) {
    Write-Host "Port 8000 is already in use (the app may already be running). Opening $url" -ForegroundColor Yellow
    Start-Process $url
    exit 0
}

# Open the browser as soon as the server answers (loading the models takes ~10-30 s).
# The check uses 127.0.0.1: "localhost" resolves to IPv6 (::1) first, where the server does not listen,
# so every check would hang until its timeout and the browser might never be opened.
Start-Job -ArgumentList $url -ScriptBlock {
    param($u)
    for ($i = 0; $i -lt 120; $i++) {
        try { Invoke-WebRequest "http://127.0.0.1:8000/api/health" -UseBasicParsing -TimeoutSec 3 | Out-Null; Start-Process $u; return }
        catch { Start-Sleep -Seconds 1 }
    }
} | Out-Null

Write-Host "Starting the Calamansi Leaf Damage Detection app..." -ForegroundColor Green
Write-Host "It opens in your browser at $url when ready (about 10-30 seconds)."
Write-Host "Keep this window open while using the app; press Ctrl+C or close it to stop."
Write-Host ""
Set-Location $backend
$env:TF_CPP_MIN_LOG_LEVEL = "2"   # hide TensorFlow start-up information messages (errors still show)
# --no-use-colors: the classic console window shows colour codes as "<-[32m" garbage
& $venvPy -m uvicorn main:app --port 8000 --no-use-colors
