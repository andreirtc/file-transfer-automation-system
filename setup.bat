@echo off
echo ========================================================
echo  File Transfer Automation System - Environment Setup
echo ========================================================
echo.

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not detected in PATH.
    echo Please install Python (version 3.10 or higher) and check 'Add Python to PATH'.
    echo Download: https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

echo [1/3] Creating virtual environment (.venv)...
python -m venv .venv

echo [2/3] Installing system dependencies...
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\pip.exe install -r requirements.txt

echo.
echo [3/3] Setup complete!
echo You can now launch the app anytime by double-clicking 'run_app.bat'.
echo.
pause
