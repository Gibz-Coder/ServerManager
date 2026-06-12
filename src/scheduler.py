import os
import sys
import json
import time
import subprocess
import threading
from datetime import datetime, timedelta
from src.utils.logger import logger
from src.utils.config import load_config, get_active_profile
from src.backup import MySQLBackupManager
from src.cleanup import MySQLCleanupManager

WORKSPACE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LAST_RUNS_PATH = os.path.join(WORKSPACE_DIR, "last_runs.json")

def load_last_runs() -> dict:
    if os.path.exists(LAST_RUNS_PATH):
        try:
            with open(LAST_RUNS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"backup": "", "cleanup": ""}

def save_last_run(task_type: str, timestamp_str: str):
    runs = load_last_runs()
    runs[task_type] = timestamp_str
    try:
        with open(LAST_RUNS_PATH, "w", encoding="utf-8") as f:
            json.dump(runs, f, indent=4)
    except Exception as e:
        logger.error(f"Failed to save last run timestamp: {str(e)}")

# Windows Task Scheduler helpers
def get_windows_python_exe() -> str:
    """Gets the path to the current virtual environment's python.exe or system python."""
    # If in venv, sys.executable points to .venv/Scripts/python.exe
    return sys.executable

def get_main_py_path() -> str:
    return os.path.join(WORKSPACE_DIR, "src", "main.py")

def register_windows_task(task_type: str, schedule_type: str, time_str: str, day_val: int) -> tuple[bool, str]:
    """
    Registers a Windows Task Scheduler task using schtasks.exe.
    - task_type: 'backup', 'cleanup', or 'all'
    """
    task_name = f"MySQL_ServerManager_{task_type.capitalize()}"
    python_exe = get_windows_python_exe()
    main_py = get_main_py_path()
    
    # Task Command to run headless runner
    command_str = f'"{python_exe}" "{main_py}" --headless --run-{task_type}'
    
    # Build schtasks arguments
    # /sc daily | weekly | monthly
    # /st HH:MM
    # /d MON | TUE | ... | 1-31
    sc_arg = "daily"
    if schedule_type == "weekly":
        sc_arg = "weekly"
    elif schedule_type == "monthly":
        sc_arg = "monthly"
        
    cmd = [
        "schtasks", "/create", 
        "/tn", task_name, 
        "/tr", command_str, 
        "/sc", sc_arg, 
        "/st", time_str, 
        "/f"  # Force overwrite if exists
    ]
    
    # Weekly requires days of week (e.g. MON, TUE)
    # Monthly requires day of month (e.g. 1-31)
    if schedule_type == "weekly":
        days_map = {1: "MON", 2: "TUE", 3: "WED", 4: "THU", 5: "FRI", 6: "SAT", 7: "SUN"}
        day_str = days_map.get(day_val, "MON")
        cmd.extend(["/d", day_str])
    elif schedule_type == "monthly":
        cmd.extend(["/d", str(day_val)])
        
    try:
        logger.info(f"Registering Windows Task: {task_name}")
        logger.info(f"Command line: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return True, result.stdout
    except subprocess.CalledProcessError as e:
        err_msg = f"Failed to register Windows Task Scheduler task: {e.stderr}"
        logger.error(err_msg)
        return False, err_msg
    except Exception as e:
        err_msg = f"Error running schtasks: {str(e)}"
        logger.error(err_msg)
        return False, err_msg

def unregister_windows_task(task_type: str) -> tuple[bool, str]:
    """Remove a task from the Windows Task Scheduler."""
    task_name = f"MySQL_ServerManager_{task_type.capitalize()}"
    cmd = ["schtasks", "/delete", "/tn", task_name, "/f"]
    try:
        logger.info(f"Removing Windows Task: {task_name}")
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return True, result.stdout
    except subprocess.CalledProcessError as e:
        # If the task doesn't exist, we treat it as successfully removed
        if "ERROR: The system cannot find the file specified" in e.stderr:
            return True, "Task did not exist"
        err_msg = f"Failed to unregister Windows task: {e.stderr}"
        logger.error(err_msg)
        return False, err_msg
    except Exception as e:
        err_msg = f"Error deleting Windows task: {str(e)}"
        logger.error(err_msg)
        return False, err_msg


# Local Scheduler Thread (running inside the GUI)
class InAppSchedulerThread(threading.Thread):
    def __init__(self):
        super().__init__()
        self.daemon = True
        self.stop_event = threading.Event()

    def stop(self):
        self.stop_event.set()

    def run(self):
        logger.info("In-App Local Scheduler Thread started.")
        while not self.stop_event.is_set():
            try:
                self.check_and_run_tasks()
            except Exception as e:
                logger.error(f"Error in scheduler check loop: {str(e)}")
            
            # Wait 30 seconds between checks (responsive enough for minute-level schedules)
            self.stop_event.wait(30)
            
        logger.info("In-App Local Scheduler Thread stopped.")

    def check_and_run_tasks(self):
        config = load_config()
        active_profile = get_active_profile(config)
        if not active_profile:
            return # No active connection configured, cannot run any tasks
            
        now = datetime.now()
        last_runs = load_last_runs()
        
        # 1. Check Backup Schedule (only if run_headless is FALSE, i.e., local app scheduler handles it)
        b_sched = config.get("backup_settings", {})
        if b_sched.get("schedule_enabled") and not b_sched.get("run_headless"):
            if self.is_task_due("backup", b_sched, last_runs.get("backup"), now):
                logger.info("Scheduled Backup is due. Launching execution...")
                success, msg = run_backup_task(active_profile, b_sched)
                if success:
                    save_last_run("backup", now.strftime("%Y-%m-%d %H:%M:%S"))
                    
        # 2. Check Cleanup Schedule (only if run_headless is FALSE)
        c_sched = config.get("retention_schedule", {})
        if c_sched.get("schedule_enabled") and not c_sched.get("run_headless"):
            if self.is_task_due("cleanup", c_sched, last_runs.get("cleanup"), now):
                logger.info("Scheduled Cleanup is due. Launching execution...")
                success, msg = run_cleanup_task(active_profile, config.get("retention_rules", []))
                if success:
                    save_last_run("cleanup", now.strftime("%Y-%m-%d %H:%M:%S"))

    def is_task_due(self, task_type: str, schedule: dict, last_run_str: str, now: datetime) -> bool:
        """Determines if a task should be run based on schedule type, time, and last execution date."""
        sched_time_str = schedule.get("schedule_time", "02:00")
        try:
            sched_hour, sched_min = map(int, sched_time_str.split(":"))
        except Exception:
            sched_hour, sched_min = 2, 0
            
        # Target time for today
        target_time = now.replace(hour=sched_hour, minute=sched_min, second=0, microsecond=0)
        
        # If current time is before the scheduled hour today, we definitely don't run yet
        if now < target_time:
            return False
            
        # Parse last run
        last_run = None
        if last_run_str:
            try:
                last_run = datetime.strptime(last_run_str, "%Y-%m-%d %H:%M:%S")
            except Exception:
                pass
                
        schedule_type = schedule.get("schedule_type", "daily")
        day_val = schedule.get("schedule_day", 1)
        
        if schedule_type == "daily":
            # If never run, or last run was before today
            if not last_run or last_run.date() < now.date():
                return True
                
        elif schedule_type == "weekly":
            # Check if current day of week matches scheduled day of week (Mon=1, Sun=7)
            # Python's weekday is 0-6 (Mon=0), convert to 1-7
            current_weekday = now.isoweekday()
            if current_weekday == day_val:
                # Run if never run, or last run was before this week
                if not last_run or last_run.isocalendar()[:2] != now.isocalendar()[:2]:
                    return True
                    
        elif schedule_type == "monthly":
            # Check if current day of month matches scheduled day
            if now.day == day_val:
                # Run if never run, or last run was before this month
                if not last_run or (last_run.year < now.year) or (last_run.year == now.year and last_run.month < now.month):
                    return True
                    
        return False

# Headless execution runners
def run_backup_task(active_profile: dict, backup_settings: dict) -> tuple[bool, str]:
    """Helper to run a full backup task for the configured database."""
    db_name = active_profile.get("database")
    if not db_name:
        err = "Backup failed: No default database selected in active connection profile."
        logger.error(err)
        return False, err
        
    backup_mgr = MySQLBackupManager(
        profile=active_profile,
        backup_dir=backup_settings.get("backup_dir", os.path.join(WORKSPACE_DIR, "backups")),
        mysqldump_path=backup_settings.get("mysqldump_path", ""),
        compress=backup_settings.get("compress", True)
    )
    
    success, msg = backup_mgr.run_backup(db_name)
    return success, msg

def run_cleanup_task(active_profile: dict, retention_rules: list[dict]) -> tuple[bool, str]:
    """Helper to run all enabled database retention cleanup rules."""
    cleanup_mgr = MySQLCleanupManager(profile=active_profile)
    total_rules = len(retention_rules)
    enabled_rules = [r for r in retention_rules if r.get("enabled", True)]
    
    if not enabled_rules:
        msg = "Cleanup: No active retention rules found."
        logger.info(msg)
        return True, msg
        
    success_count = 0
    total_deleted = 0
    errors = []
    
    for rule in enabled_rules:
        db = rule.get("db")
        table = rule.get("table")
        col = rule.get("column")
        months = rule.get("months", 6)
        
        logger.info(f"Executing scheduled cleanup rule on table `{db}`.`{table}`...")
        success, deleted, msg = cleanup_mgr.run_cleanup(db, table, col, months)
        if success:
            success_count += 1
            total_deleted += deleted
        else:
            errors.append(f"{db}.{table}: {msg}")
            
    summary_msg = f"Cleanup complete: {success_count}/{len(enabled_rules)} rules executed successfully. Total rows deleted: {total_deleted}."
    if errors:
        summary_msg += f" Errors: {'; '.join(errors)}"
        logger.error(summary_msg)
        return False, summary_msg
        
    logger.info(summary_msg)
    return True, summary_msg
