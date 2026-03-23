@echo off
setlocal
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
echo Startup Edu Agent launcher
echo Delegating to start.ps1 ...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1"
