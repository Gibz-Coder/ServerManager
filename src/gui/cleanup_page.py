from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFrame, 
                               QLabel, QPushButton, QCheckBox, QComboBox, 
                               QSpinBox, QMessageBox, QTimeEdit, QTableWidget, 
                               QTableWidgetItem, QHeaderView, QAbstractItemView)
from PySide6.QtCore import Qt, QTime, Slot, QMetaObject, Q_ARG
import threading
from src.utils.config import load_config, save_config
from src.connection import MySQLConnectionManager
from src.cleanup import MySQLCleanupManager
from src.scheduler import register_windows_task, unregister_windows_task, run_cleanup_task
from src.utils.logger import logger

class CleanupPage(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.databases = []
        self.tables = []
        self.columns = []
        self.selected_rule_idx = None
        self.init_ui()
        self.load_settings()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(25, 25, 25, 25)
        layout.setSpacing(20)
        
        # Header
        header_layout = QVBoxLayout()
        header_layout.setSpacing(5)
        
        title = QLabel("Retention & Cleanups")
        title.setObjectName("PageTitle")
        header_layout.addWidget(title)
        
        subtitle = QLabel("Set rules to automatically delete data older than a specified duration (e.g., 6 months).")
        subtitle.setObjectName("PageSubtitle")
        header_layout.addWidget(subtitle)
        
        layout.addLayout(header_layout)
        
        # Split layout
        split_layout = QHBoxLayout()
        split_layout.setSpacing(20)
        
        # Left Panel: Configure Rule
        rule_frame = QFrame()
        rule_frame.setObjectName("CardFrame")
        rule_layout = QVBoxLayout(rule_frame)
        rule_layout.setSpacing(12)
        
        rule_title = QLabel("Configure Retention Rule")
        rule_title.setStyleSheet("font-size: 15px; font-weight: bold; color: #f4f4f5;")
        rule_layout.addWidget(rule_title)
        
        # Database Select
        rule_layout.addWidget(QLabel("Select Database:"))
        self.cb_db = QComboBox()
        self.cb_db.currentIndexChanged.connect(self.on_db_changed)
        rule_layout.addWidget(self.cb_db)
        
        # Table Select
        rule_layout.addWidget(QLabel("Select Table:"))
        self.cb_table = QComboBox()
        self.cb_table.currentIndexChanged.connect(self.on_table_changed)
        rule_layout.addWidget(self.cb_table)
        
        # Column Select (date only highlighted)
        rule_layout.addWidget(QLabel("Select Date/Timestamp Column:"))
        self.cb_column = QComboBox()
        rule_layout.addWidget(self.cb_column)
        
        # Retention duration
        rule_layout.addWidget(QLabel("Retention Window (Months):"))
        self.spin_months = QSpinBox()
        self.spin_months.setRange(1, 120)
        self.spin_months.setValue(6)  # Default 6 months
        rule_layout.addWidget(self.spin_months)
        
        self.chk_rule_enabled = QCheckBox("Enable this rule")
        self.chk_rule_enabled.setChecked(True)
        rule_layout.addWidget(self.chk_rule_enabled)
        
        # Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)
        
        self.btn_dry_run = QPushButton("Simulate (Dry Run)")
        self.btn_dry_run.clicked.connect(self.trigger_dry_run)
        btn_layout.addWidget(self.btn_dry_run)
        
        self.btn_clean_now = QPushButton("Clean Up Now")
        self.btn_clean_now.setObjectName("DangerButton")
        self.btn_clean_now.clicked.connect(self.trigger_immediate_cleanup)
        btn_layout.addWidget(self.btn_clean_now)
        
        rule_layout.addLayout(btn_layout)
        
        rule_layout.addStretch()
        
        self.btn_save_rule = QPushButton("Add/Update Rule")
        self.btn_save_rule.setObjectName("PrimaryButton")
        self.btn_save_rule.setFixedHeight(35)
        self.btn_save_rule.clicked.connect(self.save_rule)
        rule_layout.addWidget(self.btn_save_rule)
        
        split_layout.addWidget(rule_frame, 3)
        
        # Right Panel: Active Rules Grid & Scheduling
        right_panel = QVBoxLayout()
        right_panel.setSpacing(20)
        
        # Active Rules table
        rules_frame = QFrame()
        rules_frame.setObjectName("CardFrame")
        rules_layout = QVBoxLayout(rules_frame)
        
        rules_title = QLabel("Active Rules")
        rules_title.setStyleSheet("font-size: 15px; font-weight: bold; color: #f4f4f5;")
        rules_layout.addWidget(rules_title)
        
        self.table_rules = QTableWidget()
        self.table_rules.setColumnCount(5)
        self.table_rules.setHorizontalHeaderLabels(["DB", "Table", "Column", "Retain", "Status"])
        self.table_rules.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_rules.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table_rules.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_rules.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table_rules.verticalHeader().setVisible(False)
        self.table_rules.itemSelectionChanged.connect(self.on_rule_row_selected)
        rules_layout.addWidget(self.table_rules)
        
        rules_buttons = QHBoxLayout()
        rules_buttons.setSpacing(10)
        
        self.btn_delete_rule = QPushButton("Delete Rule")
        self.btn_delete_rule.setObjectName("DangerButton")
        self.btn_delete_rule.clicked.connect(self.delete_rule)
        rules_buttons.addWidget(self.btn_delete_rule)
        
        self.btn_new_rule = QPushButton("Reset Selection")
        self.btn_new_rule.clicked.connect(self.reset_selection)
        rules_buttons.addWidget(self.btn_new_rule)
        
        rules_layout.addLayout(rules_buttons)
        right_panel.addWidget(rules_frame, 3)
        
        # Cleanup Automation Schedule
        schedule_frame = QFrame()
        schedule_frame.setObjectName("CardFrame")
        schedule_layout = QVBoxLayout(schedule_frame)
        schedule_layout.setSpacing(10)
        
        sched_title = QLabel("Cleanup Automation Schedule")
        sched_title.setStyleSheet("font-size: 15px; font-weight: bold; color: #f4f4f5;")
        schedule_layout.addWidget(sched_title)
        
        self.chk_sched_enable = QCheckBox("Enable Automated Retention Cleanups")
        self.chk_sched_enable.stateChanged.connect(self.toggle_schedule_inputs)
        schedule_layout.addWidget(self.chk_sched_enable)
        
        sched_opts = QHBoxLayout()
        sched_opts.setSpacing(10)
        
        self.cb_freq = QComboBox()
        self.cb_freq.addItems(["Daily", "Weekly", "Monthly"])
        self.cb_freq.currentIndexChanged.connect(self.toggle_frequency_inputs)
        sched_opts.addWidget(self.cb_freq)
        
        self.time_edit = QTimeEdit()
        self.time_edit.setTime(QTime(3, 0)) # Default 3:00 AM
        sched_opts.addWidget(self.time_edit)
        
        # Weekly/Monthly selectors
        self.cb_day_week = QComboBox()
        self.cb_day_week.addItems(["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"])
        sched_opts.addWidget(self.cb_day_week)
        
        self.spin_day_month = QSpinBox()
        self.spin_day_month.setRange(1, 31)
        sched_opts.addWidget(self.spin_day_month)
        
        schedule_layout.addLayout(sched_opts)
        
        self.chk_headless = QCheckBox("Run when application is closed (Windows Task)")
        schedule_layout.addWidget(self.chk_headless)
        
        self.btn_save_schedule = QPushButton("Save Cleanup Schedule")
        self.btn_save_schedule.setObjectName("SuccessButton")
        self.btn_save_schedule.clicked.connect(self.save_schedule)
        schedule_layout.addWidget(self.btn_save_schedule)
        
        right_panel.addWidget(schedule_frame, 2)
        
        split_layout.addLayout(right_panel, 4)
        
        layout.addLayout(split_layout)

    def refresh_page(self):
        """Reload database details from the active server connection profile."""
        profile = self.main_window.active_profile
        self.cb_db.clear()
        self.cb_table.clear()
        self.cb_column.clear()
        
        if not profile:
            self.databases = []
            self.btn_dry_run.setEnabled(False)
            self.btn_clean_now.setEnabled(False)
            return
            
        self.btn_dry_run.setEnabled(True)
        self.btn_clean_now.setEnabled(True)
        
        # Run test to see if connected
        success, _ = MySQLConnectionManager.test_connection(profile)
        if not success:
            return
            
        mgr = MySQLConnectionManager(profile)
        self.databases = mgr.get_databases()
        
        # Add databases to combobox
        self.cb_db.addItems(self.databases)
        
        # Pre-select profile's default database if present
        def_db = profile.get("database")
        if def_db and def_db in self.databases:
            idx = self.cb_db.findText(def_db)
            self.cb_db.setCurrentIndex(idx)

    def on_db_changed(self):
        self.cb_table.clear()
        db_name = self.cb_db.currentText()
        if not db_name or not self.main_window.active_profile:
            return
            
        mgr = MySQLConnectionManager(self.main_window.active_profile)
        self.tables = mgr.get_tables(db_name)
        self.cb_table.addItems(self.tables)

    def on_table_changed(self):
        self.cb_column.clear()
        db_name = self.cb_db.currentText()
        table_name = self.cb_table.currentText()
        if not db_name or not table_name or not self.main_window.active_profile:
            return
            
        mgr = MySQLConnectionManager(self.main_window.active_profile)
        self.columns = mgr.get_columns(db_name, table_name)
        
        # Populate list and highlight date columns
        first_date_idx = -1
        for idx, col in enumerate(self.columns):
            label = f"{col['name']} ({col['type']})"
            if col['is_date']:
                label += " [DATE COLUMN]"
                if first_date_idx == -1:
                    first_date_idx = idx
            self.cb_column.addItem(label, col['name'])
            
        # Pre-select first date column found
        if first_date_idx != -1:
            self.cb_column.setCurrentIndex(first_date_idx)

    def load_settings(self):
        """Loads retention settings and schedules from configuration file."""
        config = load_config()
        
        # 1. Load active rules list
        rules = config.get("retention_rules", [])
        self.table_rules.setRowCount(len(rules))
        for row_idx, rule in enumerate(rules):
            db_item = QTableWidgetItem(rule.get("db"))
            tbl_item = QTableWidgetItem(rule.get("table"))
            col_item = QTableWidgetItem(rule.get("column"))
            ret_item = QTableWidgetItem(f"{rule.get('months')} mo")
            ret_item.setTextAlignment(Qt.AlignCenter)
            
            status = "Active" if rule.get("enabled", True) else "Disabled"
            stat_item = QTableWidgetItem(status)
            stat_item.setTextAlignment(Qt.AlignCenter)
            if rule.get("enabled", True):
                stat_item.setForeground(Qt.green)
            else:
                stat_item.setForeground(Qt.gray)
                
            self.table_rules.setItem(row_idx, 0, db_item)
            self.table_rules.setItem(row_idx, 1, tbl_item)
            self.table_rules.setItem(row_idx, 2, col_item)
            self.table_rules.setItem(row_idx, 3, ret_item)
            self.table_rules.setItem(row_idx, 4, stat_item)
            
        # 2. Load schedules
        sched = config.get("retention_schedule", {})
        self.chk_sched_enable.setChecked(sched.get("schedule_enabled", False))
        
        freq_map = {"daily": 0, "weekly": 1, "monthly": 2}
        self.cb_freq.setCurrentIndex(freq_map.get(sched.get("schedule_type", "daily"), 0))
        
        time_str = sched.get("schedule_time", "03:00")
        try:
            h, m = map(int, time_str.split(":"))
            self.time_edit.setTime(QTime(h, m))
        except Exception:
            self.time_edit.setTime(QTime(3, 0))
            
        day_val = sched.get("schedule_day", 1)
        self.cb_day_week.setCurrentIndex(max(0, min(day_val - 1, 6)))
        self.spin_day_month.setValue(max(1, min(day_val, 31)))
        
        self.chk_headless.setChecked(sched.get("run_headless", False))
        
        self.toggle_schedule_inputs()
        self.reset_selection()
        self.refresh_page()

    def toggle_schedule_inputs(self):
        enabled = self.chk_sched_enable.isChecked()
        self.cb_freq.setEnabled(enabled)
        self.time_edit.setEnabled(enabled)
        self.chk_headless.setEnabled(enabled)
        self.toggle_frequency_inputs()

    def toggle_frequency_inputs(self):
        if not self.chk_sched_enable.isChecked():
            self.cb_day_week.hide()
            self.spin_day_month.hide()
            return
            
        freq = self.cb_freq.currentText()
        if freq == "Daily":
            self.cb_day_week.hide()
            self.spin_day_month.hide()
        elif freq == "Weekly":
            self.cb_day_week.show()
            self.spin_day_month.hide()
        elif freq == "Monthly":
            self.cb_day_week.hide()
            self.spin_day_month.show()

    def on_rule_row_selected(self):
        selected_ranges = self.table_rules.selectedRanges()
        if not selected_ranges:
            return
            
        row = selected_ranges[0].topRow()
        self.selected_rule_idx = row
        
        config = load_config()
        rule = config.get("retention_rules", [])[row]
        
        # Pre-select matching values in cascading dropdowns
        db = rule.get("db")
        table = rule.get("table")
        col = rule.get("column")
        
        if db in self.databases:
            self.cb_db.setCurrentIndex(self.cb_db.findText(db))
            if table in self.tables:
                self.cb_table.setCurrentIndex(self.cb_table.findText(table))
                # Find column name in userData
                col_idx = -1
                for idx in range(self.cb_column.count()):
                    if self.cb_column.itemData(idx) == col:
                        col_idx = idx
                        break
                if col_idx != -1:
                    self.cb_column.setCurrentIndex(col_idx)
                    
        self.spin_months.setValue(rule.get("months", 6))
        self.chk_rule_enabled.setChecked(rule.get("enabled", True))
        
        self.btn_save_rule.setText("Update Selected Rule")

    def reset_selection(self):
        self.selected_rule_idx = None
        self.table_rules.clearSelection()
        self.spin_months.setValue(6)
        self.chk_rule_enabled.setChecked(True)
        self.btn_save_rule.setText("Add New Rule")

    def save_rule(self):
        """Persists the edited rule to the config settings."""
        db = self.cb_db.currentText()
        table = self.cb_table.currentText()
        col = self.cb_column.currentData()
        months = self.spin_months.value()
        enabled = self.chk_rule_enabled.isChecked()
        
        if not db or not table or not col:
            QMessageBox.warning(self, "Validation Error", "Please verify Database, Table, and Date Column fields.")
            return
            
        config = load_config()
        rules = config.get("retention_rules", [])
        
        rule_data = {
            "db": db,
            "table": table,
            "column": col,
            "months": months,
            "enabled": enabled
        }
        
        if self.selected_rule_idx is not None and self.selected_rule_idx < len(rules):
            rules[self.selected_rule_idx] = rule_data
            logger.info(f"Updated retention rule: {db}.{table}.{col}")
        else:
            # Prevent duplicates
            for r in rules:
                if r["db"] == db and r["table"] == table and r["column"] == col:
                    QMessageBox.warning(self, "Duplicate Rule", "A rule already exists for this table column.")
                    return
            rules.append(rule_data)
            logger.info(f"Added new retention rule: {db}.{table}.{col}")
            
        config["retention_rules"] = rules
        save_config(config)
        
        self.load_settings()
        QMessageBox.information(self, "Success", "Retention rule saved successfully!")

    def delete_rule(self):
        """Removes the selected rule from config."""
        if self.selected_rule_idx is None:
            QMessageBox.warning(self, "Selection Required", "Please select a rule from the list.")
            return
            
        ret = QMessageBox.question(self, "Confirm Delete", "Delete this retention rule?", QMessageBox.Yes | QMessageBox.No)
        if ret == QMessageBox.No:
            return
            
        config = load_config()
        rules = config.get("retention_rules", [])
        if self.selected_rule_idx < len(rules):
            removed = rules.pop(self.selected_rule_idx)
            config["retention_rules"] = rules
            save_config(config)
            logger.info(f"Deleted retention rule: {removed.get('db')}.{removed.get('table')}")
            
        self.load_settings()

    def save_schedule(self):
        """Saves cleanup schedule and synchronizes Windows Task Scheduler task."""
        config = load_config()
        sched = config.get("retention_schedule", {})
        
        enabled = self.chk_sched_enable.isChecked()
        freq = self.cb_freq.currentText().lower()
        time_str = self.time_edit.time().toString("hh:mm")
        
        if freq == "weekly":
            day_val = self.cb_day_week.currentIndex() + 1
        elif freq == "monthly":
            day_val = self.spin_day_month.value()
        else:
            day_val = 1
            
        headless = self.chk_headless.isChecked()
        
        sched["schedule_enabled"] = enabled
        sched["schedule_type"] = freq
        sched["schedule_time"] = time_str
        sched["schedule_day"] = day_val
        sched["run_headless"] = headless
        
        config["retention_schedule"] = sched
        save_config(config)
        
        logger.info("Saved retention cleanup scheduler settings.")
        
        if enabled and headless:
            success, msg = register_windows_task("cleanup", freq, time_str, day_val)
            if success:
                QMessageBox.information(self, "Schedule Registered", "Windows Task Scheduler cleanup registered successfully!")
            else:
                QMessageBox.warning(self, "Scheduler Warning", f"Could not register task: {msg}")
        else:
            unregister_windows_task("cleanup")
            QMessageBox.information(self, "Schedule Saved", "Cleanup schedule settings saved successfully.")
            
        self.main_window.update_profile_display()

    def trigger_dry_run(self):
        """Executes simulation on active form selection."""
        profile = self.main_window.active_profile
        if not profile:
            QMessageBox.warning(self, "No Active Profile", "Please activate a connection profile first.")
            return
            
        db = self.cb_db.currentText()
        table = self.cb_table.currentText()
        col = self.cb_column.currentData()
        months = self.spin_months.value()
        
        if not db or not table or not col:
            QMessageBox.warning(self, "Validation Error", "Verify Database, Table, and Column fields.")
            return
            
        self.btn_dry_run.setEnabled(False)
        self.btn_dry_run.setText("Simulating...")
        self.repaint()
        
        # Worker thread
        def worker():
            try:
                mgr = MySQLCleanupManager(profile)
                success, count, msg = mgr.run_dry_run(db, table, col, months)
                QMetaObject.invokeMethod(self, "on_dry_run_complete", Qt.QueuedConnection,
                                         Q_ARG(bool, success), Q_ARG(int, count), Q_ARG(str, msg))
            except Exception as e:
                logger.error(f"Dry run thread failed: {str(e)}")
                
        t = threading.Thread(target=worker)
        t.daemon = True
        t.start()

    @Slot(bool, int, str)
    def on_dry_run_complete(self, success: bool, count: int, message: str):
        self.btn_dry_run.setEnabled(True)
        self.btn_dry_run.setText("Simulate (Dry Run)")
        if success:
            QMessageBox.information(self, "Dry Run Result", f"Simulation Success!\n\nDatabase: {self.cb_db.currentText()}\nTable: {self.cb_table.currentText()}\nRetention cutoff: {self.spin_months.value()} months\n\nRows matched for deletion: {count:,}")
        else:
            QMessageBox.critical(self, "Simulation Failed", f"Dry run failed:\n\n{message}")

    def trigger_immediate_cleanup(self):
        """Asynchronously triggers the real chunked data deletion after a safety check dialog."""
        profile = self.main_window.active_profile
        if not profile:
            QMessageBox.warning(self, "No Active Profile", "Please activate a connection profile first.")
            return
            
        db = self.cb_db.currentText()
        table = self.cb_table.currentText()
        col = self.cb_column.currentData()
        months = self.spin_months.value()
        
        if not db or not table or not col:
            QMessageBox.warning(self, "Validation Error", "Verify Database, Table, and Column fields.")
            return
            
        # Direct Warning Confirmation
        ret = QMessageBox.warning(self, "CRITICAL WARNING: DATA DELETION",
                                  f"You are about to PERMANENTLY DELETE data from `{db}`.`{table}` where column `{col}` is older than {months} months.\n\n"
                                  "This operation cannot be undone. Do you wish to continue?",
                                  QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        
        if ret == QMessageBox.No:
            return
            
        self.btn_clean_now.setEnabled(False)
        self.btn_clean_now.setText("Deleting Rows...")
        self.repaint()
        
        # Worker thread
        def worker():
            try:
                mgr = MySQLCleanupManager(profile)
                success, total_deleted, msg = mgr.run_cleanup(db, table, col, months)
                QMetaObject.invokeMethod(self, "on_cleanup_complete", Qt.QueuedConnection,
                                         Q_ARG(bool, success), Q_ARG(int, total_deleted), Q_ARG(str, msg))
            except Exception as e:
                logger.error(f"Immediate cleanup thread failed: {str(e)}")
                
        t = threading.Thread(target=worker)
        t.daemon = True
        t.start()

    @Slot(bool, int, str)
    def on_cleanup_complete(self, success: bool, total_deleted: int, message: str):
        self.btn_clean_now.setEnabled(True)
        self.btn_clean_now.setText("Clean Up Now")
        
        if success:
            QMessageBox.information(self, "Cleanup Complete", f"Data cleanup successful!\n\nTotal rows deleted: {total_deleted:,}")
        else:
            QMessageBox.critical(self, "Cleanup Failed", f"Cleanup operation encountered errors:\n\n{message}")
            
        self.main_window.dashboard_page.refresh_page()
