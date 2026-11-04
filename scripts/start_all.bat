@echo off
echo =============================================================
echo   Starting SUTRA Full Stack (Backend + AI Engine + MongoDB)
echo =============================================================
cd /d "%~dp0\.."
python scripts\run_all.py --mode synthetic --frames 180
pause
