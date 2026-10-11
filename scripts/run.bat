@echo off
cd /d "%~dp0.."
if not exist .venv\Scripts\python.exe call scripts\setup.bat
.venv\Scripts\python.exe -m streamlit run app.py %*
