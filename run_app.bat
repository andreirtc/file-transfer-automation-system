@echo off
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [INFO] Virtual environment not detected. Running initial setup first...
    call setup.bat
)

echo Starting File Transfer Automation System...
start "" ".venv\Scripts\pythonw.exe" app.py
