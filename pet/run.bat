@echo off
REM Launch the pet with no console window. Quit it from the tray icon.
cd /d "%~dp0"
start "" pythonw main.py
