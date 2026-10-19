@echo off
rem Double-click to set up the app on this computer (run once).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1"
pause
