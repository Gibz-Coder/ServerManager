import os
import sys
import argparse

# Add project root to sys.path to allow executing this file directly
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.utils.logger import logger
from src.utils.config import load_config, get_active_profile
from src.scheduler import run_backup_task, run_cleanup_task

def run_headless(args):
    """Headless runner interface for automated/scheduled backups and cleanups."""
    logger.info("Initializing MySQL Server Manager Headless CLI...")
    
    config = load_config()
    active_profile = get_active_profile(config)
    
    if not active_profile:
        logger.error("Headless execution failed: No active MySQL connection profile configured.")
        sys.exit(1)
        
    logger.info(f"Using active connection profile: {active_profile.get('host')}:{active_profile.get('port')} (User: {active_profile.get('user')})")
    
    executed = False
    
    # 1. Run backup if requested
    if args.run_backup or args.run_tasks:
        logger.info("Executing headless scheduled backup...")
        b_settings = config.get("backup_settings", {})
        success, msg = run_backup_task(active_profile, b_settings)
        if success:
            logger.info(f"Backup successful: {msg}")
        else:
            logger.error(f"Backup failed: {msg}")
        executed = True
        
    # 2. Run cleanup if requested
    if args.run_cleanup or args.run_tasks:
        logger.info("Executing headless scheduled table cleanups...")
        rules = config.get("retention_rules", [])
        success, msg = run_cleanup_task(active_profile, rules)
        if success:
            logger.info(f"Cleanup successful: {msg}")
        else:
            logger.error(f"Cleanup failed: {msg}")
        executed = True
        
    if not executed:
        logger.warning("No action arguments provided (use --run-backup, --run-cleanup, or --run-tasks).")

def run_gui():
    """Deferred GUI entry point importing PySide6 elements only when needed."""
    logger.info("Initializing MySQL Server Manager Graphical User Interface...")
    
    try:
        from PySide6.QtWidgets import QApplication
        from src.gui.main_window import MainWindow
    except ImportError as e:
        logger.critical(f"Failed to load PySide6 GUI libraries. Make sure dependencies are installed: {str(e)}")
        print(f"\nCRITICAL ERROR: PySide6 library is missing. Install requirements.txt first.\nError: {e}")
        sys.exit(1)
        
    app = QApplication(sys.argv)
    app.setApplicationName("MySQL Server Manager")
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MySQL Server Manager - Desktop App with Scheduled Backups & Cleanups")
    parser.add_argument("--headless", action="store_true", help="Run in command-line headless mode (no GUI)")
    parser.add_argument("--run-backup", action="store_true", help="Run configured database backup task")
    parser.add_argument("--run-cleanup", action="store_true", help="Run configured data retention cleanup rules")
    parser.add_argument("--run-tasks", action="store_true", help="Run all scheduled tasks (backup and cleanup)")
    
    args = parser.parse_args()
    
    if args.headless:
        run_headless(args)
    else:
        run_gui()
