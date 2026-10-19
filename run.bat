@echo off
title Game Release Discord Auto-Poster
cd /d "%~dp0"

echo ========================================================
echo       Game Release Discord Auto-Poster Bot
echo ========================================================
echo.

IF NOT EXIST ".venv\Scripts\python.exe" (
    echo [INFO] Virtual environment not found. Setting up .venv...
    python -m venv .venv
    echo [INFO] Installing required dependencies...
    .\.venv\Scripts\pip.exe install -r requirements.txt
    echo [INFO] Setup complete!
    echo.
)

echo Starting Discord Monitor (SteamRIP, FitGirl, DODI, CrackWatch)...
echo.
.\.venv\Scripts\python.exe main.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Bot stopped with code %ERRORLEVEL%.
    pause
)
