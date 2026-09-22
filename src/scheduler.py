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
    mo_val = None
    if schedule_type == "weekly":
        sc_arg = "weekly"
    elif schedule_type == "monthly":
        sc_arg = "monthly"
    elif schedule_type == "every 4 hours":
        sc_arg = "hourly"
        mo_val = 4
        
    cmd = [
        "schtasks", "/create", 
        "/tn", task_name, 
        "/tr", command_str, 
        "/sc", sc_arg, 
    ]
    
    if mo_val is not None:
        cmd.extend(["/mo", str(mo_val)])
        
    cmd.extend([
        "/st", time_str, 
        "/f"  # Force overwrite if exists
    ])
    
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
                save_last_run("backup", now.strftime("%Y-%m-%d %H:%M:%S"))
                
                def run_backup_async():
                    try:
                        success, msg = run_backup_task(active_profile, b_sched)
                        if success:
                            logger.info(f"Scheduled backup succeeded: {msg}")
                        else:
                            logger.error(f"Scheduled backup failed: {msg}")
                    except Exception as e:
                        logger.error(f"Error in background scheduled backup: {e}")
                threading.Thread(target=run_backup_async, daemon=True).start()
                    
        # 2. Check Cleanup Schedule (only if run_headless is FALSE)
        c_sched = config.get("retention_schedule", {})
        if c_sched.get("schedule_enabled") and not c_sched.get("run_headless"):
            if self.is_task_due("cleanup", c_sched, last_runs.get("cleanup"), now):
                logger.info("Scheduled Cleanup is due. Launching execution...")
                save_last_run("cleanup", now.strftime("%Y-%m-%d %H:%M:%S"))
                
                def run_cleanup_async():
                    try:
                        success, msg = run_cleanup_task(active_profile, config.get("retention_rules", []))
                        if success:
                            logger.info(f"Scheduled cleanup succeeded: {msg}")
                        else:
                            logger.error(f"Scheduled cleanup failed: {msg}")
                    except Exception as e:
                        logger.error(f"Error in background scheduled cleanup: {e}")
                threading.Thread(target=run_cleanup_async, daemon=True).start()

        # 3. Check MES Scraper Schedule (run 24/7 inside the app if enabled)
        mes_settings = config.get("mes_scraper_settings", {})
        if mes_settings.get("schedule_enabled"):
            interval_min = mes_settings.get("interval_minutes", 5)
            mes_last_run_str = last_runs.get("mes_scraper", "")
            mes_last_run = None
            if mes_last_run_str:
                try:
                    mes_last_run = datetime.strptime(mes_last_run_str, "%Y-%m-%d %H:%M:%S")
                except Exception:
                    pass
            
            due = False
            if not mes_last_run:
                due = True
            else:
                elapsed = (now - mes_last_run).total_seconds()
                if elapsed >= (interval_min * 60) - 5:  # 5-second tolerance
                    due = True
                    
            if due:
                logger.info("Scheduled MES Scraper job is due. Launching execution...")
                save_last_run("mes_scraper", now.strftime("%Y-%m-%d %H:%M:%S"))
                
                offline_mode = mes_settings.get("offline_mode", True)
                
                def run_mes_async():
                    try:
                        success, msg = run_mes_scraper_task(offline=offline_mode)
                        if success:
                            logger.info(f"Scheduled MES Scraper succeeded: {msg}")
                        else:
                            logger.error(f"Scheduled MES Scraper failed: {msg}")
                    except Exception as e:
                        logger.error(f"Error in background scheduled MES Scraper: {e}")
                threading.Thread(target=run_mes_async, daemon=True).start()

    def is_task_due(self, task_type: str, schedule: dict, last_run_str: str, now: datetime) -> bool:
        """Determines if a task should be run based on schedule type, time, and last execution date."""
        # Parse last run
        last_run = None
        if last_run_str:
            try:
                last_run = datetime.strptime(last_run_str, "%Y-%m-%d %H:%M:%S")
            except Exception:
                pass
                
        schedule_type = schedule.get("schedule_type", "daily")
        day_val = schedule.get("schedule_day", 1)
        
        if schedule_type == "every 4 hours":
            # Repetition starts relative to the configured Start Time of the day
            sched_time_str = schedule.get("schedule_time", "02:00")
            try:
                start_hour, start_min = map(int, sched_time_str.split(":"))
            except Exception:
                start_hour, start_min = 2, 0
                
            start_dt = now.replace(hour=start_hour, minute=start_min, second=0, microsecond=0)
            diff_seconds = (now - start_dt).total_seconds()
            
            # Find the nearest 4-hourly repetition boundary before or equal to 'now'
            import math
            k = math.floor(diff_seconds / (4 * 3600))
            last_slot = start_dt + timedelta(hours=k * 4)
            
            if not last_run or last_run < last_slot:
                return True
            return False
            
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
    """Helper to run a backup task for multiple configured schemas."""
    # Try to load schemas list from settings
    schemas = backup_settings.get("schemas", [])
    
    # Fallback to profile default database if schemas list is empty
    if not schemas:
        db_name = active_profile.get("database")
        if db_name:
            schemas = [db_name]
            
    # Fallback to all databases if still empty
    if not schemas:
        try:
            from src.connection import MySQLConnectionManager
            mgr = MySQLConnectionManager(active_profile)
            schemas = mgr.get_databases()
        except Exception as e:
            err = f"Backup failed: No database specified and could not fetch available schemas: {str(e)}"
            logger.error(err)
            return False, err
            
    if not schemas:
        err = "Backup failed: No databases found to backup."
        logger.error(err)
        return False, err
        
    backup_mgr = MySQLBackupManager(
        profile=active_profile,
        backup_dir=backup_settings.get("backup_dir", os.path.join(WORKSPACE_DIR, "backups")),
        connection_name=active_profile.get("name", "Default"),
        mysqldump_path=backup_settings.get("mysqldump_path", ""),
        compress=backup_settings.get("compress", True)
    )
    
    success_schemas = []
    failed_schemas = []
    errors = []
    
    for schema in schemas:
        try:
            success, msg = backup_mgr.run_backup(schema)
            if success:
                success_schemas.append(schema)
            else:
                failed_schemas.append(schema)
                errors.append(f"{schema}: {msg}")
        except Exception as e:
            failed_schemas.append(schema)
            errors.append(f"{schema}: {str(e)}")
            
    summary = f"Backup process complete. Succeeded: {len(success_schemas)}/{len(schemas)} schemas."
    if failed_schemas:
        summary += f" Failed: {', '.join(failed_schemas)}. Errors: {'; '.join(errors)}"
        logger.error(summary)
        return False, summary
        
    logger.info(summary)
    return True, summary

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


_mes_scraper_lock = threading.Lock()

def run_mes_scraper_task(offline: bool = False) -> tuple[bool, str]:
    """
    Executes the MES scraping job (both report scraper and EES scraper).
    Thread-safe lock prevents concurrent scraping runs.
    """
    if not _mes_scraper_lock.acquire(blocking=False):
        return False, "Scraper job is already running."
        
    try:
        import sys
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        mes_dir = os.path.join(project_root, "mes_scraper")
        if mes_dir not in sys.path:
            sys.path.insert(0, mes_dir)
            
        from src.utils.config import sync_mes_dotenv, load_config
        config = load_config()
        sync_mes_dotenv(config)
        
        from dotenv import load_dotenv
        dotenv_path = os.path.join(mes_dir, ".env")
        load_dotenv(dotenv_path, override=True)
        
        import importlib
        mes_main = importlib.import_module("main")
        db_module = importlib.import_module("db")
        init_db = db_module.init_db
        
        import logging
        from src.utils.logger import file_handler, callback_handler
        for name in ("scraper_direct", "mes_scraper", "main", "ees_scraper", "db"):
            l = logging.getLogger(name)
            l.setLevel(logging.INFO)
            if file_handler not in l.handlers:
                l.addHandler(file_handler)
            if callback_handler not in l.handlers:
                l.addHandler(callback_handler)
            l.propagate = False
            
        logger.info("Initializing MES Scraper database tables...")
        init_db(force=False)
        
        logger.info(f"Starting MES reports scraping (Offline Mode: {offline})...")
        mes_main.run_job(offline=offline)
        
        logger.info(f"Starting EES history scraping (Offline Mode: {offline})...")
        mes_main.run_ees_job(offline=offline)
        
        from src.connection import MySQLConnectionManager
        from src.utils.config import get_active_profile
        profile = get_active_profile(config)
        if profile:
            mgr = MySQLConnectionManager(profile)
            db_name = profile.get("database", "mes_data")
            for tbl in ("wip_status", "monthly_plan", "process_result", "process_trackout", "eqp_detailed_history"):
                try:
                    conn = mgr.get_connection()
                    with conn.cursor() as cursor:
                        cursor.execute(f"SELECT COUNT(*) as cnt FROM `{db_name}`.`{tbl}`")
                        cnt = cursor.fetchone()["cnt"]
                        logger.info(f"Table `{db_name}`.`{tbl}` now has {cnt} rows.")
                    conn.close()
                except Exception as ex:
                    logger.debug(f"Failed to query row count for table {tbl}: {ex}")
                    
        return True, "Scraping job completed successfully."
    except Exception as e:
        import traceback
        err_detail = traceback.format_exc()
        logger.error(f"MES scraper run failed: {str(e)}\n{err_detail}")
        return False, f"Scraper failed: {str(e)}"
    finally:
        _mes_scraper_lock.release()
