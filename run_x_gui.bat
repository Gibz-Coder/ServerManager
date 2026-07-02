@echo off
:: MySQL Server Manager GUI Launcher
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo [ERROR] Virtual environment or pythonw.exe not found!
    echo Please make sure the venv is created and requirements are installed.
    pause
    exit /b 1
)

echo Launching MySQL Server Manager...
start "" ".venv\Scripts\pythonw.exe" "src\main.py"
exit /b 0
