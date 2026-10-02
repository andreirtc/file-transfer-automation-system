@echo off
cd /d "%~dp0"
if exist "..\FileTransferAutomationSystem.exe" cd /d ".."
if exist "FileTransferAutomationSystem.exe" goto portable
if not exist "dist\FileTransferAutomationSystem\FileTransferAutomationSystem.exe" goto missing
cd /d "dist\FileTransferAutomationSystem"
:portable
for /f "delims=" %%D in ('dir /b /ad /o-n "DemoLab\Final-Test-*" 2^>nul') do (
  if exist "DemoLab\%%D\FINAL_TEST_MENU.bat" (
    call "DemoLab\%%D\FINAL_TEST_MENU.bat"
    exit /b
  )
)
:missing
echo No prepared final-test session found. See docs\FINAL_ACCEPTANCE_GUIDE.md.
pause
exit /b 1
