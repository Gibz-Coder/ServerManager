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
        
        # Header
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 10)
        header_layout.setSpacing(10)
        
        self.btn_toggle = QPushButton("«")
        self.btn_toggle.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                color: #a1a1aa;
                font-size: 18px;
                font-weight: bold;
                max-width: 32px;
                max-height: 32px;
                padding: 4px;
            }
            QPushButton:hover {
                background-color: #27272a;
                color: #ffffff;
                border-radius: 4px;
            }
        """)
        self.btn_toggle.clicked.connect(self.main_window.toggle_sidebar)
        header_layout.addWidget(self.btn_toggle, 0, Qt.AlignVCenter)
        
        title_text_layout = QVBoxLayout()
        title_text_layout.setSpacing(2)
        
        title = QLabel("Dashboard")
        title.setObjectName("PageTitle")
        title_text_layout.addWidget(title)
        
        subtitle = QLabel("Overview of configured connections, scheduled background jobs, and backup storage.")
        subtitle.setObjectName("PageSubtitle")
        title_text_layout.addWidget(subtitle)
        
        header_layout.addLayout(title_text_layout)
        layout.addLayout(header_layout)
        
        # Cards Layout (Horizontal)
        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(15)
        
        # Card 1: Connections List
        self.card_conn = QFrame()
        self.card_conn.setObjectName("CardFrame")
        self.card_conn.setMinimumHeight(320)
        cc_layout = QVBoxLayout(self.card_conn)
        
        cc_title = QLabel("Connections")
        cc_title.setObjectName("CardTitle")
        cc_layout.addWidget(cc_title)
        
        self.list_connections = QListWidget()
        self.list_connections.setObjectName("DatabaseList")
        cc_layout.addWidget(self.list_connections)
        
        self.lbl_no_conn = QLabel("No connections configured.")
        self.lbl_no_conn.setAlignment(Qt.AlignCenter)
        self.lbl_no_conn.setStyleSheet("color: #71717a; font-style: italic;")
        cc_layout.addWidget(self.lbl_no_conn)
        
        cards_layout.addWidget(self.card_conn)
        
        # Card 2: Scheduled Jobs List
        self.card_jobs = QFrame()
        self.card_jobs.setObjectName("CardFrame")
        self.card_jobs.setMinimumHeight(320)
        cj_layout = QVBoxLayout(self.card_jobs)
        
        cj_title = QLabel("Scheduled Jobs")
        cj_title.setObjectName("CardTitle")
        cj_layout.addWidget(cj_title)
        
        self.list_jobs = QListWidget()
        self.list_jobs.setObjectName("DatabaseList")
        cj_layout.addWidget(self.list_jobs)
        
        self.lbl_no_jobs = QLabel("No scheduled jobs.")
        self.lbl_no_jobs.setAlignment(Qt.AlignCenter)
        self.lbl_no_jobs.setStyleSheet("color: #71717a; font-style: italic;")
        cj_layout.addWidget(self.lbl_no_jobs)
        
        cards_layout.addWidget(self.card_jobs)
        
        # Card 3: Disk Usage
        self.card_disk = QFrame()
        self.card_disk.setObjectName("CardFrame")
        self.card_disk.setMinimumHeight(320)
        cd_layout = QVBoxLayout(self.card_disk)
        cd_layout.setSpacing(12)
        
        cd_title = QLabel("Disk Usage")
        cd_title.setObjectName("CardTitle")
        cd_layout.addWidget(cd_title)
        
        self.lbl_disk_values = QLabel("Used: 0.0 GB / 0.0 GB | Free: 0.0 GB")
        self.lbl_disk_values.setObjectName("DiskValueLabel")
        cd_layout.addWidget(self.lbl_disk_values)
        
        self.progress_disk = QProgressBar()
        self.progress_disk.setValue(0)
        self.progress_disk.setTextVisible(True)
        self.progress_disk.setObjectName("DiskProgressBar")
        cd_layout.addWidget(self.progress_disk)
        
        self.lbl_folder_size = QLabel("Backup folder size: 0.0 B")
        self.lbl_folder_size.setObjectName("FolderSizeLabel")
        cd_layout.addWidget(self.lbl_folder_size)
        
        cd_layout.addStretch()
        cards_layout.addWidget(self.card_disk)
        
        layout.addLayout(cards_layout)
        
        # Controls Row below cards
        controls_layout = QHBoxLayout()
        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.setObjectName("PrimaryButton")
        self.btn_refresh.setIconSize(QSize(16, 16))
        self.btn_refresh.setFixedWidth(120)
        self.btn_refresh.clicked.connect(self.refresh_page)
        controls_layout.addWidget(self.btn_refresh)
        controls_layout.addStretch()
        
        layout.addLayout(controls_layout)
        
        # Log Console Box spanning the bottom
        self.log_console = QTextEdit()
        self.log_console.setObjectName("LogConsole")
        self.log_console.setReadOnly(True)
        self.log_console.setMinimumHeight(150)
        self.log_console.setMaximumHeight(200)
        layout.addWidget(self.log_console, 1)
        
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
        active_id = config.get("active_profile_id")
        
        # 1. Update Connection Profiles
        self.list_connections.clear()
        profiles = config.get("connection_profiles", [])
        if profiles:
            self.lbl_no_conn.hide()
            self.list_connections.show()
            for p in profiles:
                is_active = p.get("id") == active_id
                display = p.get("name", "Unnamed")
                if is_active:
                    display += " (Active)"
                
                item = QListWidgetItem(display)
                if is_active:
                    item.setForeground(Qt.green)
                else:
                    item.setForeground(Qt.gray)
                self.list_connections.addItem(item)
        else:
            self.list_connections.hide()
            self.lbl_no_conn.show()
            
        # 2. Update Scheduled Jobs
        self.list_jobs.clear()
        jobs = []
        
        b_settings = config.get("backup_settings", {})
        if b_settings.get("schedule_enabled"):
            b_freq = b_settings.get("schedule_type", "daily").capitalize()
            b_time = b_settings.get("schedule_time", "02:00")
            b_day = b_settings.get("schedule_day", 1)
            next_b = self.get_next_run_time(b_settings.get("schedule_type", "daily"), b_time, b_day)
            jobs.append(f"Backup - {b_freq} at {b_time} (Next: {next_b})")
            
        c_sched = config.get("retention_schedule", {})
        if c_sched.get("schedule_enabled"):
            c_freq = c_sched.get("schedule_type", "daily").capitalize()
            c_time = c_sched.get("schedule_time", "03:00")
            c_day = c_sched.get("schedule_day", 1)
            next_c = self.get_next_run_time(c_sched.get("schedule_type", "daily"), c_time, c_day)
            jobs.append(f"Cleanup - {c_freq} at {c_time} (Next: {next_c})")
            
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
            
            self.lbl_disk_values.setText(f"Used: {used_gb:.1f} GB / {total_gb:.1f} GB | Free: {free_gb:.1f} GB")
            pct = int((used / total) * 100) if total > 0 else 0
            self.progress_disk.setValue(pct)
        except Exception as e:
            logger.error(f"Failed to fetch disk space usage: {str(e)}")
            self.lbl_disk_values.setText("Used: N/A / N/A | Free: N/A")
            self.progress_disk.setValue(0)
            
        # Folder Size
        folder_size = 0
        try:
            for root, dirs, files in os.walk(backup_dir):
                for f in files:
                    fp = os.path.join(root, f)
                    if os.path.exists(fp):
                        folder_size += os.path.getsize(fp)
            self.lbl_folder_size.setText(f"Backup folder size: {self.format_size(folder_size)}")
        except Exception as e:
            logger.error(f"Failed to scan folder size: {str(e)}")
            self.lbl_folder_size.setText("Backup folder size: Error reading")

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
        
        if schedule_type == "daily":
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
