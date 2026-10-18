@echo off
title CS.RIN.RU Discord Auto-Poster
cd /d "%~dp0"

echo ========================================================
echo       CS.RIN.RU Discord Auto-Poster Bot
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

echo Starting CS.RIN.RU Discord Monitor...
echo.
.\.venv\Scripts\python.exe main.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Bot stopped with code %ERRORLEVEL%.
    pause
)
