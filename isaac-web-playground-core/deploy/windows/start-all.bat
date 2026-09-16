@echo off
REM Both halves. Put a shortcut to this in
REM   %APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
REM or register it as a Task Scheduler task with "At system startup" +
REM "Run whether user is logged on or not".
start "" "%~dp0web.bat"
timeout /t 3 /nobreak
start "" "%~dp0isaac.bat"
