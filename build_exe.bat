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

if errorlevel 1 goto build_failed

echo Compiling Windows Standalone Executable with PyInstaller...
.venv\Scripts\pyinstaller.exe --noconfirm FileTransferAutomationSystem.spec
if errorlevel 1 goto build_failed

if not exist "dist\FileTransferAutomationSystem\templates" mkdir "dist\FileTransferAutomationSystem\templates"
if not exist "dist\FileTransferAutomationSystem\reports" mkdir "dist\FileTransferAutomationSystem\reports"
if not exist "dist\FileTransferAutomationSystem\config" mkdir "dist\FileTransferAutomationSystem\config"
if not exist "dist\FileTransferAutomationSystem\assets" mkdir "dist\FileTransferAutomationSystem\assets"
copy /y "templates\*.*" "dist\FileTransferAutomationSystem\templates\" >nul 2>&1
if not exist "dist\FileTransferAutomationSystem\docs" mkdir "dist\FileTransferAutomationSystem\docs"
copy /y "docs\*.md" "dist\FileTransferAutomationSystem\docs\" >nul 2>&1
copy /y "assets\*.*" "dist\FileTransferAutomationSystem\assets\" >nul 2>&1
if exist "INSTALLATION_GUIDE.txt" copy /y "INSTALLATION_GUIDE.txt" "dist\FileTransferAutomationSystem\" >nul 2>&1
if not exist "dist\FileTransferAutomationSystem\TestTools" mkdir "dist\FileTransferAutomationSystem\TestTools"
copy /y "CREATE_DEMO.bat" "dist\FileTransferAutomationSystem\TestTools\" >nul 2>&1
copy /y "TEST_PERFORMANCE.bat" "dist\FileTransferAutomationSystem\TestTools\" >nul 2>&1
copy /y "OPEN_FINAL_TEST.bat" "dist\FileTransferAutomationSystem\TestTools\" >nul 2>&1

echo.
echo ========================================================
echo  Build Completed!
echo  Location: dist\FileTransferAutomationSystem\FileTransferAutomationSystem.exe
echo ========================================================
echo.
pause

exit /b 0

:build_failed
echo [ERROR] Build failed. Do not deploy an older executable as this release.
pause
exit /b 1
