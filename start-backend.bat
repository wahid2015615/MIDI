@echo off
cd /d "%~dp0backend"
call ..\.venv\Scripts\activate.bat
pip install -e . >nul 2>&1
python run.py
