#!/usr/bin/env python3
"""
Database Lock Fix Script
Run this to resolve database lock issues and automatically start main.py
"""

import os
import sqlite3
import time
import subprocess
import sys
import signal

def kill_running_instances():
    """Kill any running instances of main.py"""
    try:
        # Get current PID to avoid killing self
        current_pid = os.getpid()
        
        # Find and kill other Python processes running main.py
        result = subprocess.run(['pgrep', '-f', 'main.py'], capture_output=True, text=True)
        if result.returncode == 0:
            pids = result.stdout.strip().split('\n')
            for pid_str in pids:
                try:
                    pid = int(pid_str.strip())
                    if pid != current_pid:
                        print(f"Killing process {pid}")
                        os.kill(pid, signal.SIGTERM)
                        time.sleep(1)
                        # Force kill if still running
                        try:
                            os.kill(pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                except (ValueError, ProcessLookupError):
                    pass
    except FileNotFoundError:
        # pgrep not available, try ps
        try:
            result = subprocess.run(['ps', 'aux'], capture_output=True, text=True)
            lines = result.stdout.split('\n')
            for line in lines:
                if 'main.py' in line and 'python' in line:
                    parts = line.split()
                    if len(parts) > 1:
                        try:
                            pid = int(parts[1])
                            if pid != os.getpid():
                                print(f"Killing process {pid}")
                                os.kill(pid, signal.SIGTERM)
                                time.sleep(1)
                        except (ValueError, ProcessLookupError):
                            pass
        except:
            print("Could not automatically kill processes. Please manually kill any running main.py instances.")

def fix_database_lock():
    """Fix database lock issues"""
    db_files = ['quiz_bot.db', 'quiz_bot.db-wal', 'quiz_bot.db-shm']
    
    print("Fixing database lock issues...")
    
    # Kill running instances first
    kill_running_instances()
    time.sleep(2)
    
    # Remove lock files
    for db_file in db_files:
        if os.path.exists(db_file):
            try:
                # Test if file is locked
                with open(db_file, 'r+b') as f:
                    pass
                print(f"✓ {db_file} is accessible")
            except (IOError, OSError) as e:
                print(f"✗ {db_file} is locked or inaccessible: {e}")
                
                # Try to remove the file
                try:
                    os.remove(db_file)
                    print(f"✓ Removed {db_file}")
                except OSError as remove_error:
                    print(f"✗ Could not remove {db_file}: {remove_error}")
                    
                    # Last resort: rename the file
                    try:
                        backup_name = f"{db_file}.backup_{int(time.time())}"
                        os.rename(db_file, backup_name)
                        print(f"✓ Renamed {db_file} to {backup_name}")
                    except OSError as rename_error:
                        print(f"✗ Could not rename {db_file}: {rename_error}")
    
    # Try to create a fresh database
    try:
        conn = sqlite3.connect('quiz_bot.db', timeout=5)
        cursor = conn.cursor()
        cursor.execute('SELECT 1')
        conn.close()
        print("✓ Database is now accessible")
        return True
    except sqlite3.OperationalError as e:
        print(f"✗ Database still has issues: {e}")
        return False

def run_main_py():
    """Run main.py after fixing database issues"""
    if not os.path.exists('main.py'):
        print("✗ main.py not found in current directory")
        return False
    
    print("\n" + "="*50)
    print("Starting main.py...")
    print("="*50)
    
    try:
        # Use subprocess to run main.py and allow it to inherit the terminal
        result = subprocess.run([sys.executable, 'main.py'])
        return result.returncode == 0
    except KeyboardInterrupt:
        print("\n\n✓ main.py stopped by user (Ctrl+C)")
        return True
    except Exception as e:
        print(f"✗ Error running main.py: {e}")
        return False

if __name__ == "__main__":
    print("Database Lock Fix Script")
    print("=" * 30)
    
    success = fix_database_lock()
    
    if success:
        print("\n✓ Database lock issues resolved!")
        print("Starting main.py automatically...")
        time.sleep(1)  # Brief pause for readability
        run_main_py()
    else:
        print("\n✗ Could not resolve database lock issues")
        print("Try manually removing quiz_bot.db* files:")
        print("rm quiz_bot.db*")
        print("\nAdditional tips:")
        print("- Make sure to use Ctrl+C (not Ctrl+Z) to stop the script")
        print("- Check for background processes: ps aux | grep main.py")
        print("- If issues persist, restart your terminal/system")

