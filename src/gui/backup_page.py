from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFrame, 
                               QLabel, QLineEdit, QPushButton, QCheckBox, 
                               QComboBox, QSpinBox, QFileDialog, QMessageBox, QTimeEdit)
from PySide6.QtCore import Qt, QTime
import threading
from src.utils.config import load_config, save_config
from src.scheduler import register_windows_task, unregister_windows_task, run_backup_task
from src.utils.logger import logger

class BackupPage(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.init_ui()
        self.load_settings()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(25, 25, 25, 25)
        layout.setSpacing(20)
        
        # Header
        header_layout = QVBoxLayout()
        header_layout.setSpacing(5)
        
        title = QLabel("Database Backups")
        title.setObjectName("PageTitle")
        header_layout.addWidget(title)
        
        subtitle = QLabel("Create instant manual backups or set up recurring scheduled database dumps.")
        subtitle.setObjectName("PageSubtitle")
        header_layout.addWidget(subtitle)
        
        layout.addLayout(header_layout)
        
        # Split layout
        split_layout = QHBoxLayout()
        split_layout.setSpacing(20)
        
        # Left Panel: Manual Backup
        manual_frame = QFrame()
        manual_frame.setObjectName("CardFrame")
        manual_layout = QVBoxLayout(manual_frame)
        manual_layout.setSpacing(12)
        
        manual_title = QLabel("Manual Backup")
        manual_title.setStyleSheet("font-size: 15px; font-weight: bold; color: #f4f4f5;")
        manual_layout.addWidget(manual_title)
        
        # Selected DB label
        self.lbl_selected_db = QLabel("Selected Database: None")
        self.lbl_selected_db.setStyleSheet("font-weight: bold; color: #6366f1;")
        manual_layout.addWidget(self.lbl_selected_db)
        
        # Backup Dir selection
        dir_label = QLabel("Backup Destination Folder:")
        manual_layout.addWidget(dir_label)
        
        dir_input_layout = QHBoxLayout()
        self.txt_backup_dir = QLineEdit()
        self.txt_backup_dir.setPlaceholderText("Select folder to store backup SQLs")
        dir_input_layout.addWidget(self.txt_backup_dir)
        
        btn_browse_dir = QPushButton("Browse...")
        btn_browse_dir.clicked.connect(self.browse_backup_dir)
        dir_input_layout.addWidget(btn_browse_dir)
        manual_layout.addLayout(dir_input_layout)
        
        # Compression option
        self.chk_compress = QCheckBox("Compress backup as ZIP file (.zip)")
        self.chk_compress.setChecked(True)
        manual_layout.addWidget(self.chk_compress)
        
        # mysqldump path selection
        dump_path_label = QLabel("mysqldump.exe Path (Optional):")
        manual_layout.addWidget(dump_path_label)
        
        dump_input_layout = QHBoxLayout()
        self.txt_dump_path = QLineEdit()
        self.txt_dump_path.setPlaceholderText("Path to mysqldump.exe (uses Python engine if empty)")
        dump_input_layout.addWidget(self.txt_dump_path)
        
        btn_browse_dump = QPushButton("Browse...")
        btn_browse_dump.clicked.connect(self.browse_dump_path)
        dump_input_layout.addWidget(btn_browse_dump)
        manual_layout.addLayout(dump_input_layout)
        
        manual_layout.addStretch()
        
        # Backup Action Button
        self.btn_backup_now = QPushButton("Backup Selected Database Now")
        self.btn_backup_now.setObjectName("PrimaryButton")
        self.btn_backup_now.setFixedHeight(40)
        self.btn_backup_now.clicked.connect(self.trigger_manual_backup)
        manual_layout.addWidget(self.btn_backup_now)
        
        split_layout.addWidget(manual_frame, 1)
        
        # Right Panel: Scheduling Configuration
        schedule_frame = QFrame()
        schedule_frame.setObjectName("CardFrame")
        schedule_layout = QVBoxLayout(schedule_frame)
        schedule_layout.setSpacing(12)
        
        sched_title = QLabel("Schedule Configuration")
        sched_title.setStyleSheet("font-size: 15px; font-weight: bold; color: #f4f4f5;")
        schedule_layout.addWidget(sched_title)
        
        self.chk_sched_enable = QCheckBox("Enable Scheduled Backups")
        self.chk_sched_enable.stateChanged.connect(self.toggle_schedule_inputs)
        schedule_layout.addWidget(self.chk_sched_enable)
        
        # Sched options
        self.lbl_freq = QLabel("Frequency:")
        schedule_layout.addWidget(self.lbl_freq)
        self.cb_freq = QComboBox()
        self.cb_freq.addItems(["Daily", "Weekly", "Monthly"])
        self.cb_freq.currentIndexChanged.connect(self.toggle_frequency_inputs)
        schedule_layout.addWidget(self.cb_freq)
        
        self.lbl_time = QLabel("Execution Time:")
        schedule_layout.addWidget(self.lbl_time)
        self.time_edit = QTimeEdit()
        self.time_edit.setTime(QTime(2, 0)) # Default 2:00 AM
        schedule_layout.addWidget(self.time_edit)
        
        # Weekly day select
        self.lbl_day_week = QLabel("Day of Week:")
        schedule_layout.addWidget(self.lbl_day_week)
        self.cb_day_week = QComboBox()
        self.cb_day_week.addItems(["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"])
        schedule_layout.addWidget(self.cb_day_week)
        
        # Monthly day select
        self.lbl_day_month = QLabel("Day of Month:")
        schedule_layout.addWidget(self.lbl_day_month)
        self.spin_day_month = QSpinBox()
        self.spin_day_month.setRange(1, 31)
        self.spin_day_month.setValue(1)
        schedule_layout.addWidget(self.spin_day_month)
        
        # Windows Task Scheduler integration
        self.chk_headless = QCheckBox("Run when application is closed (Windows Task)")
        schedule_layout.addWidget(self.chk_headless)
        
        schedule_layout.addStretch()
        
        self.btn_save_schedule = QPushButton("Save Schedule Settings")
        self.btn_save_schedule.setObjectName("SuccessButton")
        self.btn_save_schedule.setFixedHeight(40)
        self.btn_save_schedule.clicked.connect(self.save_schedule)
        schedule_layout.addWidget(self.btn_save_schedule)
        
        split_layout.addWidget(schedule_frame, 1)
        
        layout.addLayout(split_layout)

    def browse_backup_dir(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Select Backup Destination Directory")
        if dir_path:
            self.txt_backup_dir.setText(dir_path)

    def browse_dump_path(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Locate mysqldump.exe", "", "Executables (mysqldump.exe)")
        if file_path:
            self.txt_dump_path.setText(file_path)

    def refresh_page(self):
        """Update selected database name in manual panel based on active profile."""
        profile = self.main_window.active_profile
        if profile and profile.get("database"):
            self.lbl_selected_db.setText(f"Selected Database: '{profile.get('database')}'")
            self.lbl_selected_db.setStyleSheet("font-weight: bold; color: #10b981;")
            self.btn_backup_now.setEnabled(True)
        else:
            self.lbl_selected_db.setText("Selected Database: None configured in active profile")
            self.lbl_selected_db.setStyleSheet("font-weight: bold; color: #ef4444;")
            self.btn_backup_now.setEnabled(False)

    def load_settings(self):
        """Loads scheduler settings from config.json into the UI widgets."""
        config = load_config()
        b_settings = config.get("backup_settings", {})
        
        self.txt_dump_path.setText(b_settings.get("mysqldump_path", ""))
        self.txt_backup_dir.setText(b_settings.get("backup_dir", ""))
        self.chk_compress.setChecked(b_settings.get("compress", True))
        
        # Schedule settings
        self.chk_sched_enable.setChecked(b_settings.get("schedule_enabled", False))
        
        freq_map = {"daily": 0, "weekly": 1, "monthly": 2}
        freq_str = b_settings.get("schedule_type", "daily").lower()
        self.cb_freq.setCurrentIndex(freq_map.get(freq_str, 0))
        
        # Parse Time string (HH:MM)
        time_str = b_settings.get("schedule_time", "02:00")
        try:
            h, m = map(int, time_str.split(":"))
            self.time_edit.setTime(QTime(h, m))
        except Exception:
            self.time_edit.setTime(QTime(2, 0))
            
        day_val = b_settings.get("schedule_day", 1)
        self.cb_day_week.setCurrentIndex(max(0, min(day_val - 1, 6)))
        self.spin_day_month.setValue(max(1, min(day_val, 31)))
        
        self.chk_headless.setChecked(b_settings.get("run_headless", False))
        
        self.toggle_schedule_inputs()
        self.refresh_page()

    def toggle_schedule_inputs(self):
        """Enable/disable input widgets depending on schedule toggle."""
        enabled = self.chk_sched_enable.isChecked()
        self.cb_freq.setEnabled(enabled)
        self.time_edit.setEnabled(enabled)
        self.chk_headless.setEnabled(enabled)
        self.toggle_frequency_inputs()

    def toggle_frequency_inputs(self):
        """Enable/disable day selectors depending on weekly/monthly choices."""
        if not self.chk_sched_enable.isChecked():
            self.lbl_day_week.hide()
            self.cb_day_week.hide()
            self.lbl_day_month.hide()
            self.spin_day_month.hide()
            return
            
        freq = self.cb_freq.currentText()
        if freq == "Daily":
            self.lbl_day_week.hide()
            self.cb_day_week.hide()
            self.lbl_day_month.hide()
            self.spin_day_month.hide()
        elif freq == "Weekly":
            self.lbl_day_week.show()
            self.cb_day_week.show()
            self.lbl_day_month.hide()
            self.spin_day_month.hide()
        elif freq == "Monthly":
            self.lbl_day_week.hide()
            self.cb_day_week.hide()
            self.lbl_day_month.show()
            self.spin_day_month.show()

    def save_schedule(self):
        """Persist schedule to config.json and coordinate Windows Task registrations."""
        config = load_config()
        b_settings = config.get("backup_settings", {})
        
        # Pull parameters
        enabled = self.chk_sched_enable.isChecked()
        freq = self.cb_freq.currentText().lower()
        time_str = self.time_edit.time().toString("hh:mm")
        
        # Calculate day value
        if freq == "weekly":
            day_val = self.cb_day_week.currentIndex() + 1
        elif freq == "monthly":
            day_val = self.spin_day_month.value()
        else:
            day_val = 1
            
        headless = self.chk_headless.isChecked()
        
        # Update config fields
        b_settings["mysqldump_path"] = self.txt_dump_path.text().strip()
        b_settings["backup_dir"] = self.txt_backup_dir.text().strip()
        b_settings["compress"] = self.chk_compress.isChecked()
        
        b_settings["schedule_enabled"] = enabled
        b_settings["schedule_type"] = freq
        b_settings["schedule_time"] = time_str
        b_settings["schedule_day"] = day_val
        b_settings["run_headless"] = headless
        
        config["backup_settings"] = b_settings
        save_config(config)
        
        logger.info("Saved backup scheduler settings in configuration.")
        
        # Synchronize Windows Task Scheduler
        if enabled and headless:
            success, msg = register_windows_task("backup", freq, time_str, day_val)
            if success:
                QMessageBox.information(self, "Scheduler Registered", "Windows Task Scheduler backup registered successfully!")
            else:
                QMessageBox.warning(self, "Scheduler Warning", f"Could not register Windows Task Scheduler task: {msg}")
        else:
            # Unregister just in case it was previously registered
            unregister_windows_task("backup")
            QMessageBox.information(self, "Schedule Saved", "Backup schedule saved successfully.")
            
        self.main_window.update_profile_display()

    def trigger_manual_backup(self):
        """Asynchronously execute backup operation so UI stays responsive."""
        profile = self.main_window.active_profile
        if not profile:
            QMessageBox.warning(self, "No Profile", "Active connection profile required to backup database.")
            return
            
        db_name = profile.get("database")
        if not db_name:
            QMessageBox.warning(self, "No Database", "Active profile does not have a default database defined.")
            return
            
        backup_dir = self.txt_backup_dir.text().strip()
        if not backup_dir:
            QMessageBox.warning(self, "Invalid Directory", "Please specify a valid backup folder path.")
            return
            
        # Update fields in configuration
        config = load_config()
        config["backup_settings"]["mysqldump_path"] = self.txt_dump_path.text().strip()
        config["backup_settings"]["backup_dir"] = backup_dir
        config["backup_settings"]["compress"] = self.chk_compress.isChecked()
        save_config(config)
        
        # Lock UI
        self.btn_backup_now.setEnabled(False)
        self.btn_backup_now.setText("Backing Up... Please Wait")
        self.repaint()
        
        # Launch worker thread
        def worker():
            try:
                b_settings = load_config().get("backup_settings", {})
                success, msg = run_backup_task(profile, b_settings)
                
                # Update UI thread
                from PySide6.QtCore import QMetaObject, Q_ARG
                QMetaObject.invokeMethod(self, "on_backup_complete", Qt.QueuedConnection, 
                                         Q_ARG(bool, success), Q_ARG(str, msg))
            except Exception as ex:
                logger.error(f"Manual backup thread exception: {str(ex)}")
                
        t = threading.Thread(target=worker)
        t.daemon = True
        t.start()

    # Qt slot to execute on the main thread after worker completion
    from PySide6.QtCore import Slot
    @Slot(bool, str)
    def on_backup_complete(self, success: bool, message: str):
        self.btn_backup_now.setEnabled(True)
        self.btn_backup_now.setText("Backup Selected Database Now")
        
        if success:
            QMessageBox.information(self, "Backup Success", f"Database backup completed!\n\n{message}")
        else:
            QMessageBox.critical(self, "Backup Error", f"Database backup failed:\n\n{message}")
        
        self.main_window.dashboard_page.refresh_page()
