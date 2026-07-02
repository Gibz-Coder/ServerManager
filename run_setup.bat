@echo off
:: MySQL Server Manager - Server Setup & Dependency Installer
cd /d "%~dp0"

echo ===================================================
echo MySQL Server Manager - Environment Setup Wizard
echo ===================================================
echo.

:: Step 1: Check Python installation
echo [1/3] Checking for Python installation...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not added to your system PATH.
    echo Please install Python 3.10 or higher and try again.
    pause
    exit /b 1
)
for /f "tokens=2" %%i in ('python --version') do set pyver=%%i
echo [INFO] Found Python version %pyver%

:: Step 2: Create virtual environment
echo.
echo [2/3] Setting up Python virtual environment...
if exist ".venv" (
    echo [INFO] Virtual environment .venv already exists.
) else (
    echo [INFO] Creating virtual environment .venv...
    python -m venv .venv
)

if not exist ".venv" (
    echo [ERROR] Failed to create virtual environment.
    pause
    exit /b 1
)

:: Step 3: Install dependencies
echo.
echo [3/3] Installing project dependencies...

:: Upgrade pip first
.\.venv\Scripts\python.exe -m pip install --upgrade pip >nul 2>&1

:: Check if we have offline packages folder
if not exist "offline_packages" goto :online_install

echo [INFO] Found 'offline_packages' folder. Attempting offline installation...
.\.venv\Scripts\python.exe -m pip install --no-index --find-links=offline_packages -r requirements.txt
if %errorlevel% equ 0 goto :success

echo.
echo [WARNING] Offline installation failed or was incomplete.
echo Attempting to download and install online from PyPI...

:online_install
echo [INFO] Installing dependencies online from PyPI...
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install dependencies online.
    pause
    exit /b 1
)

:success
echo.
echo ===================================================
echo [SUCCESS] Environment setup completed successfully!
echo.
echo To run the desktop GUI:
echo   Double-click 'run_gui.bat' or run: .\.venv\Scripts\python.exe src\main.py
echo.
echo To run the headless scheduler:
echo   .\.venv\Scripts\python.exe src\main.py --scheduler
echo ===================================================
echo.
pause
exit /b 0
