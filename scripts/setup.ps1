# Setup (Windows PowerShell). If blocked: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
py -3 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-dev.txt
Write-Host "OK. Run: scripts\run.ps1   (tests: .venv\Scripts\python -m pytest -q)"
