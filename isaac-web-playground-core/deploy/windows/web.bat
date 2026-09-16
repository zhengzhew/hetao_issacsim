@echo off
REM The web server runs inside WSL. `bash -lc` does NOT load nvm, so calling
REM node directly fails with "command not found"; start-web.sh sources it.
title Playground Web

REM Machine-specific values belong in local.bat (copy local.example.bat).
if exist "%~dp0local.bat" call "%~dp0local.bat"
if not defined WSL_USER set WSL_USER=%USERNAME%

:loop
wsl -u %WSL_USER% -- bash -lc "~/start-web.sh"
echo.
echo Web server exited. Restarting in 5 seconds... (close this window to stop)
timeout /t 5 /nobreak
goto loop
