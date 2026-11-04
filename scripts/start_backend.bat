@echo off
echo ===================================================
echo   Starting SUTRA Backend with MongoDB & FastAPI
echo ===================================================
cd /d "%~dp0\.."
python scripts\run_backend.py --port 8000 --reload
pause
