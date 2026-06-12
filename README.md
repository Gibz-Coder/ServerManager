# MySQL Server Manager

A robust, modern desktop GUI and headless command-line tool built with Python and PySide6 to automate database management, scheduled backups, and chunked data retention policies for MySQL servers.

---

## Key Features

- **Modern Dark-Themed GUI**: Built using PySide6 with a sleek, responsive dark mode design.
- **Connection Profile Manager**: Save, switch, and test credentials for multiple MySQL databases/servers.
- **Database Statistics Dashboard**: Displays database/table sizes (in MB) and row counts dynamically.
- **Automated Database Backups**:
  - Leverages native `mysqldump` (secure password masking via environmental variables) with automatic `.zip` compression.
  - Fallback to a **Pure-Python streaming engine** (via `PyMySQL` server-side cursors) for environments without MySQL client binaries installed.
- **Chunked Data Retention Cleanups**:
  - Clean up historical records older than a configured threshold (e.g., 6 months).
  - Deletes in configurable chunks (default: 5000) with minor server pauses to avoid row-locking, transaction blocks, and CPU spikes on high-load production servers.
  - Built-in dry-run feature to count records matching policies before execution.
- **Dual-Mode Task Scheduler**:
  - **In-App Scheduler**: Background threads monitor schedules while the desktop application is open.
  - **Windows Task Scheduler Integration**: Integrates directly with Windows Task Scheduler (`schtasks.exe`) to configure headless runs that execute on schedule even when the GUI is completely closed.

---

## Directory Structure

```text
├── config.json               # Local configuration for connection profiles, backup & retention schedules
├── requirements.txt          # Python dependencies
├── install_offline.txt       # Script instructions to set up the python environment offline
├── run_gui.txt               # Script instructions to launch the GUI manager
├── src/
│   ├── main.py               # Main application entry point (GUI / Headless CLI router)
│   ├── backup.py             # Database backup manager (mysqldump & Python streaming fallback)
│   ├── cleanup.py            # Retention rules executor (dry run & chunked database deletion)
│   ├── connection.py         # MySQL connection profile validator & statistics queries
│   ├── scheduler.py          # Local scheduler threads & Windows Task Scheduler command integrations
│   ├── gui/                  # PySide6 application window views and components
│   │   ├── main_window.py    # Main window and sidebar frame controller
│   │   ├── theme.py          # Custom CSS style definition sheet (Dark theme styling)
│   │   ├── dashboard_page.py # DB statistics dashboard widget
│   │   ├── connection_page.py# Server profile manager widget
│   │   ├── backup_page.py    # Backups configuration widget
│   │   ├── cleanup_page.py   # Retention rules & dry runs widget
│   │   └── logs_page.py      # Console logger viewer widget
│   └── utils/
│       ├── config.py         # Configuration profile loaders and savers
│       └── logger.py         # Thread-safe subscribing logger engine
└── tests/
    └── test_logic.py         # Unit tests validating backup streaming and chunked cleanup deletes
```

---

## Getting Started

### Prerequisites
- **Python 3.10 or higher** installed and added to the system `PATH`.
- A running MySQL/MariaDB server instance to connect to.

### Online Setup (Standard)
1. Open a terminal in the root directory.
2. Initialize a virtual environment:
   ```bash
   python -m venv .venv
   ```
3. Activate the virtual environment:
   - **Windows CMD/PowerShell**:
     ```powershell
     .\.venv\Scripts\activate
     ```
   - **Linux/macOS**:
     ```bash
     source .venv/bin/activate
     ```
4. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

### Offline Setup (Windows Environment)
If installing on an offline or restricted server:
1. Ensure the `offline_packages/` directory containing the `.whl` files is present in the workspace.
2. Rename [install_offline.txt](install_offline.txt) to `install_offline.bat` and double-click to execute. This automatically creates the virtual environment and installs the wheels offline using:
   ```cmd
   .\.venv\Scripts\python.exe -m pip install --no-index --find-links=offline_packages -r requirements.txt
   ```

---

## Execution Modes

### 1. Graphical User Interface (GUI)
To launch the desktop manager:
- Rename [run_gui.txt](run_gui.txt) to `run_gui.bat` and run it, or launch via:
  ```bash
  python src/main.py
  ```

### 2. Headless CLI (Automated Scheduled Runs)
The application can be run directly from command line tools or system schedulers without loading any GUI. It uses the currently **active connection profile** configured in `config.json`.

Available flags:
- `--headless`: Enables command line execution.
- `--run-backup`: Performs a database backup using current settings.
- `--run-cleanup`: Runs all enabled retention cleanup rules.
- `--run-tasks`: Runs both backup and cleanup operations.

**Examples:**
```bash
# Run database backups only
python src/main.py --headless --run-backup

# Run all scheduled tasks (backups + cleanups)
python src/main.py --headless --run-tasks
```

---

## Scheduling System

### Headless Windows Task Scheduler Setup
When you enable scheduling and check **Run Headless (Windows Task)** inside the GUI settings:
1. The app invokes Windows `schtasks.exe` via Python subprocess.
2. It registers a task named `MySQL_ServerManager_Backup` and/or `MySQL_ServerManager_Cleanup`.
3. The task runs invisible to the user in the background, executing the headless command:
   ```cmd
   "C:\path\to\venv\python.exe" "C:\path\to\src\main.py" --headless --run-<task_type>
   ```

To check registered schedules in Command Prompt:
```cmd
schtasks /query /tn "MySQL_ServerManager_Backup"
```

---

## Unit Testing

To verify the core logic engines (backup and chunked cleanup) without connecting to a real database, execute the unit tests from the project root:

```bash
python -m unittest tests/test_logic.py
```
