@echo off
cd /d "%~dp0.."
py -3 -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt -r requirements-dev.txt
echo OK. Run: scripts\run.bat
