@echo off
rem Start Cheese Heist. Extra arguments go to main.py (e.g. --seed 5 --size 27).
cd /d "%~dp0"
if exist .venv\Scripts\python.exe (
    .venv\Scripts\python.exe main.py %*
) else (
    python main.py %*
)
