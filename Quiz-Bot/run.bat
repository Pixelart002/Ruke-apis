@echo off
REM Quiz Bot Manager - Windows Launcher
REM Sets UTF-8 encoding and runs the bot

echo Setting UTF-8 encoding...
chcp 65001 > nul

echo Starting Quiz Bot Manager...
python main.py

if errorlevel 1 (
    echo.
    echo Error occurred. Trying with python3...
    python3 main.py
    
    if errorlevel 1 (
        echo.
        echo Failed to start. Please ensure Python is installed.
        echo You can install Python from: https://www.python.org/downloads/
        pause
    )
)

pause