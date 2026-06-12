@echo off
:: MySQL Server Manager Offline Installer for Windows
cd /d "%~dp0"

echo ===================================================
echo MySQL Server Manager - Offline Environment Installer
echo ===================================================
echo.

:: Check if offline packages folder exists
if not exist "offline_packages" (
    echo [ERROR] The 'offline_packages' directory is missing!
    echo Please make sure the folder containing .whl files is present.
    pause
    exit /b 1
)

:: Create virtual environment
echo [1/2] Creating python virtual environment (.venv)...
python -m venv .venv
if %errorlevel% neq 0 (
    echo [ERROR] Failed to initialize python virtual environment.
    echo Ensure Python is installed on your system path.
    pause
    exit /b 1
)

:: Install dependencies offline
echo [2/2] Installing requirements from local offline packages...
.\.venv\Scripts\python.exe -m pip install --no-index --find-links=offline_packages -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] Dependency installation failed.
    pause
    exit /b 1
)

echo.
echo ===================================================
echo [SUCCESS] Offline installation completed successfully!
echo You can now use 'run_gui.bat' to launch the manager.
echo ===================================================
echo.
pause
exit /b 0
