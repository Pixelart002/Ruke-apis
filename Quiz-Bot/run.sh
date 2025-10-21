#!/bin/bash
# Quiz Bot Manager - Unix/Linux/macOS/Termux Launcher

echo "Quiz Bot Manager - Starting..."
echo "================================"

# Detect platform
if [ -n "$TERMUX_VERSION" ] || [ -d "/data/data/com.termux" ]; then
    echo "Platform: Termux detected"
    # Termux specific setup
    export PYTHONIOENCODING=utf-8
elif [ "$(uname)" == "Darwin" ]; then
    echo "Platform: macOS detected"
elif [ "$(uname)" == "Linux" ]; then
    echo "Platform: Linux/VPS detected"
fi

# Check if Python is installed
if command -v python3 &> /dev/null; then
    echo "Using python3..."
    python3 main.py
elif command -v python &> /dev/null; then
    echo "Using python..."
    python main.py
else
    echo "Error: Python is not installed!"
    echo "Please install Python first:"
    if [ -n "$TERMUX_VERSION" ]; then
        echo "  pkg install python"
    elif [ "$(uname)" == "Darwin" ]; then
        echo "  brew install python3"
    else
        echo "  sudo apt-get install python3"
    fi
    exit 1
fi