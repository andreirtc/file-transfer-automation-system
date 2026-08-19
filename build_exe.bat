@echo off
cd /d "%~dp0"
echo ========================================================
echo  Building Standalone Windows Executable (.exe)
echo ========================================================
echo.

if not exist ".venv\Scripts\pyinstaller.exe" (
    echo [INFO] Installing PyInstaller and Pillow...
    .venv\Scripts\pip.exe install pyinstaller pillow
)

echo Compiling Windows Standalone Executable with PyInstaller...
.venv\Scripts\pyinstaller.exe --noconfirm --onedir --windowed --icon "assets/app_icon.ico" --add-data "assets;assets" --add-data "config;config" --hidden-import "pyminizip" --hidden-import "watchdog" --hidden-import "qfluentwidgets" --hidden-import "core.compression_worker" --name "FileTransferAutomationSystem" app.py

echo.
echo ========================================================
echo  Build Completed!
echo  Location: dist\FileTransferAutomationSystem\FileTransferAutomationSystem.exe
echo ========================================================
echo.
pause
