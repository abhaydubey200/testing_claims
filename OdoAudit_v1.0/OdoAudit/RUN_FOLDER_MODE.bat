@echo off
title Odometer Photo Audit - folder mode
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" call SETUP.bat
echo Auditing every claim file in the data folder...
".venv\Scripts\python.exe" run_folder_mode.py
start "" "%~dp0data"
pause
