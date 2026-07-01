import os
import shutil
from datetime import datetime, timedelta
import calendar
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFrame, 
                               QLabel, QPushButton, QListWidget, QListWidgetItem, 
                               QProgressBar, QTextEdit)
from PySide6.QtCore import Qt, QSize, Slot, QMetaObject, Q_ARG
from src.utils.config import load_config, get_active_profile
from src.connection import MySQLConnectionManager
from src.utils.logger import logger, get_recent_logs

class DashboardPage(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.init_ui()
        self.load_historical_logs()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(25, 25, 25, 25)
        layout.setSpacing(20)
        
        # Header Row
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 10)
        
        title = QLabel("Dashboard")
        title.setObjectName("PageTitle")
        header_layout.addWidget(title)
        
        header_layout.addStretch()
        
        # Modern top-right Refresh button
        self.btn_refresh = QPushButton("🔄 Refresh")
        self.btn_refresh.setObjectName("PrimaryButton")
        self.btn_refresh.setFixedWidth(100)
        self.btn_refresh.setFixedHeight(30)
        self.btn_refresh.clicked.connect(self.refresh_page)
        header_layout.addWidget(self.btn_refresh)
        
        layout.addLayout(header_layout)
        
        # Top Row: Metrics Cards
        top_layout = QHBoxLayout()
        top_layout.setSpacing(15)
        
        # Card 1: Active Connection
        self.card_conn = QFrame()
        self.card_conn.setObjectName("CardFrame")
        cc_layout = QVBoxLayout(self.card_conn)
        cc_layout.setSpacing(6)
        
        lbl_cc_hdr = QLabel("ACTIVE CONNECTION")
        lbl_cc_hdr.setObjectName("CardTitle")
        cc_layout.addWidget(lbl_cc_hdr)
        
        self.lbl_conn_name = QLabel("No active profile")
        self.lbl_conn_name.setObjectName("CardValue")
        self.lbl_conn_name.setStyleSheet("font-size: 18px;")
        cc_layout.addWidget(self.lbl_conn_name)
        
        self.lbl_conn_detail = QLabel("Configure a profile in Settings")
        self.lbl_conn_detail.setObjectName("CardDesc")
        cc_layout.addWidget(self.lbl_conn_detail)
        
        self.lbl_conn_status = QLabel("🔴 Offline")
        self.lbl_conn_status.setStyleSheet("font-size: 12px; font-weight: bold; color: #71717a;")
        cc_layout.addWidget(self.lbl_conn_status)
        cc_layout.addStretch()
        
        top_layout.addWidget(self.card_conn, 1)
        
        # Card 2: Disk Storage
        self.card_disk = QFrame()
        self.card_disk.setObjectName("CardFrame")
        cd_layout = QVBoxLayout(self.card_disk)
        cd_layout.setSpacing(6)
        
        lbl_cd_hdr = QLabel("DISK STORAGE")
        lbl_cd_hdr.setObjectName("CardTitle")
        cd_layout.addWidget(lbl_cd_hdr)
        
        self.lbl_disk_values = QLabel("Used: 0.0 GB / 0.0 GB")
        self.lbl_disk_values.setObjectName("CardValue")
        self.lbl_disk_values.setStyleSheet("font-size: 16px;")
        cd_layout.addWidget(self.lbl_disk_values)
        
        self.progress_disk = QProgressBar()
        self.progress_disk.setValue(0)
        self.progress_disk.setFixedHeight(8)
        self.progress_disk.setTextVisible(False)
        self.progress_disk.setObjectName("DiskProgressBar")
        self.progress_disk.setStyleSheet("""
            QProgressBar {
                background-color: #27272a;
                border: none;
                border-radius: 4px;
            }
            QProgressBar::chunk {
                background-color: #6366f1;
                border-radius: 4px;
            }
        """)
        cd_layout.addWidget(self.progress_disk)
        
        self.lbl_disk_free = QLabel("Free space: 0.0 GB")
        self.lbl_disk_free.setObjectName("CardDesc")
        cd_layout.addWidget(self.lbl_disk_free)
        cd_layout.addStretch()
        
        top_layout.addWidget(self.card_disk, 1)
        
        # Card 3: Backup Repository Info
        self.card_repo = QFrame()
        self.card_repo.setObjectName("CardFrame")
        cr_layout = QVBoxLayout(self.card_repo)
        cr_layout.setSpacing(6)
        
        lbl_cr_hdr = QLabel("BACKUP REPOSITORY")
        lbl_cr_hdr.setObjectName("CardTitle")
        cr_layout.addWidget(lbl_cr_hdr)
        
        self.lbl_folder_size = QLabel("Size: 0.0 B")
        self.lbl_folder_size.setObjectName("CardValue")
        self.lbl_folder_size.setStyleSheet("font-size: 18px;")
        cr_layout.addWidget(self.lbl_folder_size)
        
        self.lbl_backup_count = QLabel("0 backup files")
        self.lbl_backup_count.setObjectName("CardDesc")
        cr_layout.addWidget(self.lbl_backup_count)
        
        self.lbl_repo_path = QLabel("Path: --")
        self.lbl_repo_path.setObjectName("CardDesc")
        self.lbl_repo_path.setStyleSheet("font-size: 11px;")
        self.lbl_repo_path.setWordWrap(False)
        cr_layout.addWidget(self.lbl_repo_path)
        cr_layout.addStretch()
        
        top_layout.addWidget(self.card_repo, 1)
        
        layout.addLayout(top_layout)
        
        # Middle Row: Scheduled Tasks & Log Console
        middle_layout = QHBoxLayout()
        middle_layout.setSpacing(15)
        
        # Left Panel: Scheduled Automation Tasks Card
        card_sched = QFrame()
        card_sched.setObjectName("CardFrame")
        cs_layout = QVBoxLayout(card_sched)
        cs_layout.setSpacing(10)
        
        lbl_cs_hdr = QLabel("SCHEDULED AUTOMATION TASKS")
        lbl_cs_hdr.setObjectName("CardTitle")
        lbl_cs_hdr.setStyleSheet("margin-bottom: 5px;")
        cs_layout.addWidget(lbl_cs_hdr)
        
        self.list_jobs = QListWidget()
        self.list_jobs.setObjectName("DatabaseList")
        cs_layout.addWidget(self.list_jobs)
        
        self.lbl_no_jobs = QLabel("No scheduled automation tasks are currently active.")
        self.lbl_no_jobs.setObjectName("CardDesc")
        self.lbl_no_jobs.setAlignment(Qt.AlignCenter)
        self.lbl_no_jobs.setStyleSheet("font-style: italic; margin: 20px 0;")
        cs_layout.addWidget(self.lbl_no_jobs)
        
        middle_layout.addWidget(card_sched, 2)
        
        # Right Panel: Activity Console Log Card
        card_console = QFrame()
        card_console.setObjectName("CardFrame")
        csl_layout = QVBoxLayout(card_console)
        csl_layout.setSpacing(10)
        
        lbl_csl_hdr = QLabel("LIVE SYSTEM ACTIVITY LOG")
        lbl_csl_hdr.setObjectName("CardTitle")
        lbl_csl_hdr.setStyleSheet("margin-bottom: 5px;")
        csl_layout.addWidget(lbl_csl_hdr)
        
        self.log_console = QTextEdit()
        self.log_console.setObjectName("LogConsole")
        self.log_console.setReadOnly(True)
        self.log_console.setStyleSheet("""
            QTextEdit {
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 11px;
                background-color: #0c0c0e;
                border: 1px solid #27272a;
                border-radius: 6px;
                color: #e4e4e7;
            }
        """)
        csl_layout.addWidget(self.log_console)
        
        middle_layout.addWidget(card_console, 3)
        
        layout.addLayout(middle_layout, 1)
        
        self.refresh_page()

    def load_historical_logs(self):
        logs = get_recent_logs(100)
        self.log_console.setPlainText(logs)
        self.scroll_to_bottom()

    @Slot(str)
    def append_log(self, message: str):
        QMetaObject.invokeMethod(self.log_console, "append", Qt.QueuedConnection, Q_ARG(str, message))
        QMetaObject.invokeMethod(self, "scroll_to_bottom", Qt.QueuedConnection)

    @Slot()
    def scroll_to_bottom(self):
        scrollbar = self.log_console.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def refresh_page(self):
        """Loads and updates connection profiles, schedules, and disk space usage."""
        config = load_config()
        
        # 1. Update Connection Profile Info
        active_profile = get_active_profile(config)
        if active_profile:
            self.lbl_conn_name.setText(active_profile.get("name", "Unnamed Profile"))
            self.lbl_conn_detail.setText(f"{active_profile.get('host')}:{active_profile.get('port')} (DB: {active_profile.get('database', '')})")
            
            # Simple connection test to verify status badge
            success, _ = MySQLConnectionManager.test_connection(active_profile)
            if success:
                self.lbl_conn_status.setText("🟢 Connected")
                self.lbl_conn_status.setStyleSheet("font-size: 12px; font-weight: bold; color: #10b981;")
            else:
                self.lbl_conn_status.setText("🔴 Disconnected")
                self.lbl_conn_status.setStyleSheet("font-size: 12px; font-weight: bold; color: #ef4444;")
        else:
            self.lbl_conn_name.setText("No Connection Profile")
            self.lbl_conn_detail.setText("Configure server credentials in Settings.")
            self.lbl_conn_status.setText("🔴 Offline")
            self.lbl_conn_status.setStyleSheet("font-size: 12px; font-weight: bold; color: #71717a;")
            
        # 2. Update Scheduled Jobs
        self.list_jobs.clear()
        jobs = []
        
        b_settings = config.get("backup_settings", {})
        if b_settings.get("schedule_enabled"):
            b_freq = b_settings.get("schedule_type", "daily")
            # format frequency beautifully
            b_freq_display = b_freq.replace("every 4 hours", "Every 4 Hours").capitalize()
            b_time = b_settings.get("schedule_time", "02:00")
            b_day = b_settings.get("schedule_day", 1)
            next_b = self.get_next_run_time(b_freq, b_time, b_day)
            jobs.append(f"⚡ Backup ({b_freq_display} at {b_time})\n   Next: {next_b}")
            
        c_sched = config.get("retention_schedule", {})
        if c_sched.get("schedule_enabled"):
            c_freq = c_sched.get("schedule_type", "daily")
            c_freq_display = c_freq.capitalize()
            c_time = c_sched.get("schedule_time", "03:00")
            c_day = c_sched.get("schedule_day", 1)
            next_c = self.get_next_run_time(c_freq, c_time, c_day)
            jobs.append(f"🧹 Cleanup ({c_freq_display} at {c_time})\n   Next: {next_c}")
        else:
            jobs.append("🧹 Cleanup (Disabled in Settings)")
            
        # Add Data Retention Rules details
        r_rules = config.get("retention_rules", [])
        active_rules = [r for r in r_rules if r.get("enabled", True)]
        if active_rules:
            jobs.append("📋 Active Retention Rules:")
            for rule in active_rules:
                db = rule.get("db", "")
                table = rule.get("table", "")
                months = rule.get("months", 6)
                jobs.append(f"  • {db}.{table} ({months} mo)")
                
        if jobs:
            self.lbl_no_jobs.hide()
            self.list_jobs.show()
            for j in jobs:
                self.list_jobs.addItem(QListWidgetItem(j))
        else:
            self.list_jobs.hide()
            self.lbl_no_jobs.show()
            
        # 3. Update Disk Space Details
        backup_dir = b_settings.get("backup_dir", "")
        if not backup_dir:
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            backup_dir = os.path.join(project_root, "backups")
            
        os.makedirs(backup_dir, exist_ok=True)
        
        try:
            total, used, free = shutil.disk_usage(backup_dir)
            total_gb = total / (1024 ** 3)
            used_gb = used / (1024 ** 3)
            free_gb = free / (1024 ** 3)
            
            self.lbl_disk_values.setText(f"Used: {used_gb:.1f} GB / {total_gb:.1f} GB")
            pct = int((used / total) * 100) if total > 0 else 0
            self.progress_disk.setValue(pct)
            self.lbl_disk_free.setText(f"Free space: {free_gb:.1f} GB ({100 - pct}% remaining)")
        except Exception as e:
            logger.error(f"Failed to fetch disk space usage: {str(e)}")
            self.lbl_disk_values.setText("Used: N/A / N/A")
            self.progress_disk.setValue(0)
            self.lbl_disk_free.setText("Free space: N/A")
            
        # Folder Size and Backup Count
        folder_size = 0
        backup_count = 0
        try:
            for root, dirs, files in os.walk(backup_dir):
                for f in files:
                    fp = os.path.join(root, f)
                    if os.path.exists(fp):
                        folder_size += os.path.getsize(fp)
                        backup_count += 1
            self.lbl_folder_size.setText(f"Size: {self.format_size(folder_size)}")
            self.lbl_backup_count.setText(f"{backup_count} backup files")
            
            # Shorten display path, full path in tooltip
            short_path = backup_dir
            if len(short_path) > 35:
                short_path = short_path[:15] + "..." + short_path[-17:]
            self.lbl_repo_path.setText(f"Path: {short_path}")
            self.lbl_repo_path.setToolTip(backup_dir)
        except Exception as e:
            logger.error(f"Failed to scan folder size: {str(e)}")
            self.lbl_folder_size.setText("Size: Error")
            self.lbl_backup_count.setText("N/A files")
            self.lbl_repo_path.setText("Path: Error")

    def format_size(self, size_bytes):
        if size_bytes == 0:
            return "0.0 B"
        units = ["B", "KB", "MB", "GB", "TB"]
        i = 0
        while size_bytes >= 1024 and i < len(units) - 1:
            size_bytes /= 1024
            i += 1
        return f"{size_bytes:.1f} {units[i]}"

    def get_next_run_time(self, schedule_type: str, schedule_time: str, schedule_day: int = 1) -> str:
        """Helper to calculate next run datetime based on schedule frequency settings."""
        try:
            h, m = map(int, schedule_time.split(":"))
        except Exception:
            h, m = 2, 0
            
        now = datetime.now()
        target = now.replace(hour=h, minute=m, second=0, microsecond=0)
        
        if schedule_type == "every 4 hours":
            start_dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
            diff_seconds = (now - start_dt).total_seconds()
            import math
            k = math.floor(diff_seconds / (4 * 3600))
            target = start_dt + timedelta(hours=(k + 1) * 4)
        elif schedule_type == "daily":
            if now >= target:
                target += timedelta(days=1)
        elif schedule_type == "weekly":
            # schedule_day is 1 (Mon) to 7 (Sun). Python's weekday() is 0 (Mon) to 6 (Sun).
            target_weekday = schedule_day - 1
            current_weekday = now.weekday()
            days_ahead = target_weekday - current_weekday
            if days_ahead < 0 or (days_ahead == 0 and now >= target):
                days_ahead += 7
            target += timedelta(days=days_ahead)
        elif schedule_type == "monthly":
            # schedule_day is 1-31.
            # Handle month wrap
            if now.day > schedule_day or (now.day == schedule_day and now >= target):
                # Move to next month
                if now.month == 12:
                    target = target.replace(year=now.year + 1, month=1)
                else:
                    target = target.replace(month=now.month + 1)
                    
            # Clamp the day to the month's maximum day (preventing errors on 31st feb, etc.)
            _, num_days = calendar.monthrange(target.year, target.month)
            target = target.replace(day=min(schedule_day, num_days))
            
        return target.strftime("%Y-%m-%d %H:%M")
