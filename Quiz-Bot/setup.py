#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cross-platform setup script for Quiz Bot Manager
Automatically detects OS and installs requirements
"""

import os
import sys
import platform
import subprocess

def get_platform():
    """Detect the current platform"""
    system = platform.system().lower()
    is_termux = 'termux' in os.environ.get('PREFIX', '').lower() or os.path.exists('/data/data/com.termux')
    
    if is_termux:
        return 'termux'
    elif system == 'windows':
        return 'windows'
    elif system == 'darwin':
        return 'macos'
    elif system == 'linux':
        return 'linux'
    else:
        return 'unknown'

def install_requirements():
    """Install requirements based on platform"""
    platform_name = get_platform()
    
    print(f"Detected platform: {platform_name}")
    print("-" * 40)
    
    if platform_name == 'termux':
        print("Setting up for Termux...")
        commands = [
            ['pkg', 'update', '-y'],
            ['pkg', 'install', 'python', '-y'],
            ['pip', 'install', '--upgrade', 'pip'],
            ['pip', 'install', 'telethon==1.34.0']
        ]
    elif platform_name == 'windows':
        print("Setting up for Windows...")
        # Set UTF-8 mode for Windows
        os.system('chcp 65001')
        commands = [
            [sys.executable, '-m', 'pip', 'install', '--upgrade', 'pip'],
            [sys.executable, '-m', 'pip', 'install', 'telethon==1.34.0']
        ]
    else:
        print(f"Setting up for {platform_name.upper()}...")
        commands = [
            [sys.executable, '-m', 'pip', 'install', '--upgrade', 'pip'],
            [sys.executable, '-m', 'pip', 'install', 'telethon==1.34.0']
        ]
    
    # Execute commands
    for cmd in commands:
        print(f"Running: {' '.join(cmd)}")
        try:
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            print("✓ Success")
        except subprocess.CalledProcessError as e:
            print(f"✗ Failed: {e}")
            if 'permission' in str(e).lower():
                print("\nTry running with sudo (Linux/macOS) or as Administrator (Windows)")
            return False
    
    return True

def main():
    """Main setup function"""
    print("\n" + "="*50)
    print("    QUIZ BOT MANAGER - SETUP")
    print("="*50)
    
    if install_requirements():
        print("\n" + "="*50)
        print("✅ Setup completed successfully!")
        print("="*50)
        print("\nYou can now run the bot with:")
        print("  python main.py")
        if get_platform() == 'windows':
            print("\nNote: If you see encoding errors, run:")
            print("  chcp 65001")
    else:
        print("\n" + "="*50)
        print("❌ Setup failed!")
        print("="*50)
        print("\nPlease install manually:")
        print("  pip install telethon==1.34.0")

if __name__ == "__main__":
    main()