@echo off
setlocal
title Isaac Sim - Stop Services
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0isaac-web-playground-core\deploy\windows\service-control.ps1" -Action Stop %*
set "serviceExit=%ERRORLEVEL%"
echo.
if not "%serviceExit%"=="0" echo Failed. Please read the message above.
pause
exit /b %serviceExit%
