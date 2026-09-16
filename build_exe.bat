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
.venv\Scripts\pyinstaller.exe --noconfirm --onedir --windowed --icon "assets/app_icon.ico" --add-data "assets;assets" --add-data "config;config" --add-data "templates;templates" --hidden-import "pyzipper" --hidden-import "pyminizip" --hidden-import "watchdog" --hidden-import "qfluentwidgets" --hidden-import "openpyxl" --hidden-import "core.compression_worker" --name "FileTransferAutomationSystem" app.py

if not exist "dist\FileTransferAutomationSystem\templates" mkdir "dist\FileTransferAutomationSystem\templates"
if not exist "dist\FileTransferAutomationSystem\reports" mkdir "dist\FileTransferAutomationSystem\reports"
if not exist "dist\FileTransferAutomationSystem\config" mkdir "dist\FileTransferAutomationSystem\config"
if not exist "dist\FileTransferAutomationSystem\assets" mkdir "dist\FileTransferAutomationSystem\assets"
copy /y "templates\*.*" "dist\FileTransferAutomationSystem\templates\" >nul 2>&1
copy /y "config\*.*" "dist\FileTransferAutomationSystem\config\" >nul 2>&1
copy /y "assets\*.*" "dist\FileTransferAutomationSystem\assets\" >nul 2>&1
if exist "INSTALLATION_GUIDE.txt" copy /y "INSTALLATION_GUIDE.txt" "dist\FileTransferAutomationSystem\" >nul 2>&1

echo.
echo ========================================================
echo  Build Completed!
echo  Location: dist\FileTransferAutomationSystem\FileTransferAutomationSystem.exe
echo ========================================================
echo.
pause
