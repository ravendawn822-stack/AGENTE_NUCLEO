@echo off
cd /d "%~dp0"
python panel.py
if errorlevel 1 pause
