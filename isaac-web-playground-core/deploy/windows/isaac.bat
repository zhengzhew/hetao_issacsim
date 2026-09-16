@echo off
REM Isaac Sim + playground bridge. Runs on Windows, in a desktop session --
REM a service or an SSH session has no window station and therefore no D3D
REM device, so RTX rendering fails there. Verified on this box.
title Isaac Sim + Bridge

REM Machine-specific values belong in local.bat (copy local.example.bat).
if exist "%~dp0local.bat" call "%~dp0local.bat"
if not defined PLAYGROUND set PLAYGROUND=C:\playground
if not defined ISAAC_PUBLIC_IP set ISAAC_PUBLIC_IP=127.0.0.1
if not defined ISAAC_BRIDGE_PORT set ISAAC_BRIDGE_PORT=8765

REM WebRTC is off: it needs UDP 47998 end to end and the VPN NATs clients, so
REM it has no consumer here and still costs an NVENC session. Add --livestream
REM (and set ISAAC_STREAM_RENDERER=native in start-web.sh) to turn it back on.
set LIVESTREAM_FLAG=--no-livestream

REM Multi-GPU vs single-GPU is an unresolved tradeoff on this box, not a
REM settled default -- 2026-08-27 measured single-GPU as fine, 2026-09-04
REM measured it at 3.2x slower (kit.update() 21.8ms -> 70ms, 43Hz -> 9.8Hz)
REM because the earlier measurement was pinned to the 12fps capture cap and
REM couldn't see slowdown below it. Multi-GPU is faster but costs ~2.8GB/33%%
REM of GPU0, which this machine also uses for training. Set GPU_FLAGS in
REM local.bat to choose; this is only the fallback if local.bat does not.
if not defined GPU_FLAGS set GPU_FLAGS=--multi-gpu

if not exist "%PLAYGROUND%\logs" mkdir "%PLAYGROUND%\logs"

cd /d C:\isaacsim

:loop
REM Keep one previous run so a crash loop does not erase the evidence, and so
REM the log is readable over SSH -- when this is started as a scheduled task
REM the window lives in a session nobody is connected to.
if exist "%PLAYGROUND%\logs\isaac.log" move /y "%PLAYGROUND%\logs\isaac.log" "%PLAYGROUND%\logs\isaac.prev.log" >nul
call python.bat "%PLAYGROUND%\bridge\isaac_playground.py" ^
  --host 0.0.0.0 --port %ISAAC_BRIDGE_PORT% ^
  --public-ip %ISAAC_PUBLIC_IP% ^
  --catalog-dir "%PLAYGROUND%\configs" ^
  --upload-dir "%PLAYGROUND%\uploads" ^
  --scene-id warehouse --robot-id carter-v1 ^
  %LIVESTREAM_FLAG% %GPU_FLAGS% > "%PLAYGROUND%\logs\isaac.log" 2>&1
echo.
echo Last 15 lines of %PLAYGROUND%\logs\isaac.log:
powershell -NoProfile -Command "Get-Content '%PLAYGROUND%\logs\isaac.log' -Tail 15"
echo Isaac exited. Restarting in 10 seconds... (close this window to stop)
timeout /t 10 /nobreak
goto loop
