@echo off
cd /d "%~dp0"
if exist "..\FileTransferAutomationSystem.exe" cd /d ".."
set "DEMO_SESSION=DemoLab\Session-%RANDOM%-%RANDOM%"
if exist "FileTransferAutomationSystem.exe" goto portable
if not exist "dist\FileTransferAutomationSystem\FileTransferAutomationSystem.exe" goto missing
cd /d "dist\FileTransferAutomationSystem"
:portable
echo Creating a separate demo app and timestamped sample files. Please wait...
start "" /wait "FileTransferAutomationSystem.exe" --demo-setup "%cd%\%DEMO_SESSION%"
if errorlevel 1 goto failed
if not exist "%DEMO_SESSION%\DEMO_MENU.bat" goto failed
start "" "%DEMO_SESSION%\START_HERE.html"
call "%DEMO_SESSION%\DEMO_MENU.bat"
exit /b 0
:missing
echo Build the portable application first using build_exe.bat.
pause
exit /b 1
:failed
echo Demo setup failed. Read DemoLab\DEMO_ERROR.txt for details.
pause
exit /b 1
