# Run the dashboard (Windows PowerShell). Paper trading only.
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
if (-not (Test-Path .\.venv\Scripts\python.exe)) { & (Join-Path $PSScriptRoot "setup.ps1") }
& .\.venv\Scripts\python.exe -m streamlit run app.py @args
