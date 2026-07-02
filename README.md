# DB Orchestrator

A robust, modern desktop GUI and headless command-line tool built with Python and PySide6 to automate database management, scheduled backups, chunked data retention policies, and automated scraping/syncing for MySQL servers.

---

## Key Features

- **Dynamic Theme-Switchable GUI**: Built using PySide6 with a sleek, responsive design supporting three custom themes: **Dark Mode**, **Light Mode**, and **Midnight Blue**. Includes a collapsible sidebar with slide transition animations.
- **Connection Profile Manager**: Save, switch, test, and securely store credentials for multiple MySQL databases/servers using **Fernet symmetric encryption** via [config.py](file:///c:/ProjectDev/ServerManager/src/utils/config.py).
- **Database Statistics Dashboard**: Displays active database/table sizes (in MB) and row counts dynamically, with live logging output in the console pane.
- **Automated Database Backups**:
  - Leverages native `mysqldump` (secure password masking via temporary environmental variables) with automatic `.zip`/`.gz` compression.
  - Fallback to a **Pure-Python streaming engine** (via `PyMySQL` server-side cursors in [backup.py](file:///c:/ProjectDev/ServerManager/src/backup.py)) for environments without MySQL client binaries installed.
- **Chunked Data Retention Cleanups**:
  - Clean up historical records older than a configured threshold (e.g., 6 or 12 months) via retention rules.
  - Deletes in configurable chunks (default: 5000) with minor server pauses (e.g., 0.1s sleep) to avoid row-locking, transaction blocks, and CPU spikes on high-load production servers.
  - Built-in dry-run feature to count records matching policies before execution.
- **Dual-Mode Task Scheduler**:
  - **In-App Scheduler**: Background threads monitor schedules and execute backups, retention cleanups, and MES scraper jobs while the desktop application is open.
  - **Windows Task Scheduler Integration**: Integrates directly with Windows Task Scheduler (`schtasks.exe`) to configure headless runs that execute on schedule even when the GUI is completely closed.
- **Integrated MES & EES Scraper**:
  - Automates scraping of SEMPHIL MES reports (WIP Status, Monthly Plan, Process Result, and Process Trackout) and Equipment Event System (EES) history.
  - Supports both online scraping and offline replaying of local binaries for testing and development.
  - See the detailed [MES Scraper Developer Guide](file:///c:/ProjectDev/ServerManager/mes_scraper/README.md) for more details.

---

## Directory Structure

```text
├── config.json               # Local configuration for connection profiles, backup & retention schedules
├── requirements.txt          # Python dependencies
├── run_setup.bat             # Auto-installer for the virtual environment & dependencies (supports offline/online mode)
├── run_x_gui.bat             # Desktop GUI launcher script
├── src/
│   ├── main.py               # Main application entry point (GUI / Headless CLI router)
│   ├── backup.py             # Database backup manager (mysqldump & Python streaming fallback)
│   ├── cleanup.py            # Retention rules executor (dry run & chunked database deletion)
│   ├── connection.py         # MySQL connection profile validator & statistics queries
│   ├── scheduler.py          # Local scheduler threads & Windows Task Scheduler command integrations
│   ├── gui/                  # PySide6 application window views and components
│   │   ├── main_window.py    # Main window, navigation tabs, and animated sidebar controller
│   │   ├── theme.py          # Custom CSS style definition sheets (Dark, Light, Midnight styling)
│   │   ├── dashboard_page.py # DB statistics dashboard widget
│   │   ├── jobs_page.py      # Automation widget (DB backups, data retention, MES scraper sync)
│   │   └── settings_page.py  # Configurations widget (Server connections, schedules, scraper config, theme selector)
│   └── utils/
│       ├── config.py         # Configuration profile loaders/savers with Fernet password encryption
│       └── logger.py         # Thread-safe subscribing logger engine
├── mes_scraper/              # Standalone MES/EES Scraper module with binary parsers and snapshot tables
└── tests/
    └── test_logic.py         # Unit tests validating backup streaming, chunked cleanups, and scheduler calculations
```

---

## Getting Started

### Prerequisites
- **Python 3.10 or higher** installed and added to the system `PATH`.
- A running MySQL/MariaDB server instance to connect to.

### Windows Automatic Setup (Recommended)
On Windows, you can automatically set up the virtual environment and install all dependencies by double-clicking [run_setup.bat](file:///c:/ProjectDev/ServerManager/run_setup.bat) or running:
```cmd
run_setup.bat
```
*Note: This script automatically detects if `offline_packages/` is present to run a local offline installation; otherwise, it will fetch dependencies online from PyPI.*

### Manual Setup (Cross-Platform)
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
   - **Online**:
     ```bash
     pip install -r requirements.txt
     ```
   - **Offline (Windows)**:
     ```cmd
     pip install --no-index --find-links=offline_packages -r requirements.txt
     ```

---

## Execution Modes

### 1. Graphical User Interface (GUI)
To launch the desktop manager:
- Double-click the launcher script [run_x_gui.bat](file:///c:/ProjectDev/ServerManager/run_x_gui.bat), or run:
  ```cmd
  run_x_gui.bat
  ```
- Alternatively, launch via python directly:
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
When you enable scheduling and check **Run Headless (Windows Task)** inside the GUI settings under "General & Cleanup Recurrence":
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
python tests/test_logic.py
```


