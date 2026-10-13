@echo off
setlocal
cd /d "%~dp0"
title Bilibili Danmaku + DG-Lab Controller
echo.
echo  ================================================
echo    Bilibili Live Danmaku   and   DG-Lab Coyote
echo  ================================================
echo.
set "PY=python"
where python >nul 2>nul
if not errorlevel 1 goto run
set "PY=py"
where py >nul 2>nul
if not errorlevel 1 goto run
echo  [ERROR] Python not found.
echo          Install Python 3.9+ and tick "Add python.exe to PATH".
echo          https://www.python.org/downloads/
echo.
pause
exit /b 1
:run
echo  [1/2] Checking dependencies (first run may take a minute)...
echo.
%PY% -m pip install -r requirements.txt
if errorlevel 1 goto pipfail
echo.
echo  [2/2] Starting... close this window to exit the program.
echo  -------------------------------------------------
echo.
%PY% main.py
echo.
echo  Program exited.
pause
exit /b 0
:pipfail
echo.
echo  [ERROR] Dependency install failed. Run this manually to see why:
echo          %PY% -m pip install -r requirements.txt
echo.
pause
exit /b 1
