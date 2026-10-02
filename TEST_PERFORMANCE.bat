@echo off
cd /d "%~dp0"
if exist "..\FileTransferAutomationSystem.exe" cd /d ".."
if exist "FileTransferAutomationSystem.exe" goto portable
cd /d "dist\FileTransferAutomationSystem"
:portable
set "PERF_SESSION=%cd%\PerformanceLab\Session-%RANDOM%-%RANDOM%"
start "" /wait "FileTransferAutomationSystem.exe" --performance-setup "%PERF_SESSION%"
if errorlevel 1 goto failed
start "" /wait "FileTransferAutomationSystem.exe" --performance-configure "%PERF_SESSION%"
if errorlevel 2 exit /b 0
if errorlevel 1 goto failed
echo Running performance test. Wait until copying and full verification finish...
start "" /wait "FileTransferAutomationSystem.exe" --performance-run "%PERF_SESSION%"
if errorlevel 1 goto failed
start "" notepad.exe "%PERF_SESSION%\RESULT.txt"
exit /b 0
:failed
echo Test failed. Read PerformanceLab\PERFORMANCE_ERROR.txt. Completed test copies are retained.
pause
exit /b 1
