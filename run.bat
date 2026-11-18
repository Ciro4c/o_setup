@echo off
cd /d "%~dp0"
python -m osetup gui || powershell -ExecutionPolicy Bypass -File "%~dp0install.ps1" gui
pause
