@echo off
cd /d "%~dp0"

rem Find Python: try "python" first, then "py"
set PY=python
where python >nul 2>nul
if errorlevel 1 set PY=py

%PY% build.py
pause
