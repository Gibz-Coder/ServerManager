import os
import threading
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFrame, 
                               QLabel, QLineEdit, QPushButton, QCheckBox, 
                               QComboBox, QSpinBox, QMessageBox, QTimeEdit, 
                               QTableWidget, QTableWidgetItem, QHeaderView, 
                               QAbstractItemView, QListWidget, QListWidgetItem,
                               QTextEdit, QScrollArea, QTabWidget, QFormLayout)
from PySide6.QtCore import Qt, QTime, Slot, QMetaObject, Q_ARG
from src.utils.config import load_config, save_config
from src.connection import MySQLConnectionManager
from src.cleanup import MySQLCleanupManager
from src.scheduler import register_windows_task, unregister_windows_task, run_backup_task, run_cleanup_task
from src.utils.logger import logger, get_recent_logs

class JobsPage(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.databases = []
        self.tables = []
        self.columns = []
        self.selected_rule_idx = None
        
        self.init_ui()
        self.load_settings()
        self.load_historical_logs()

    def init_ui(self):
        # Main Layout is vertical
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)
        
        # Header
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 10)
        
        title = QLabel("Automation")
        title.setObjectName("PageTitle")
        header_layout.addWidget(title)
        
        main_layout.addLayout(header_layout)
        
        # Tabs container
        self.tabs = QTabWidget()
        self.tabs.currentChanged.connect(self.on_tab_changed)
        
        # Setup Tabs
        self.tab_backup = QWidget()
        self.tab_retention = QWidget()
        self.tab_mes = QWidget()
        
        self.setup_backup_tab()
        self.setup_retention_tab()
        self.setup_mes_tab()
        
        self.tabs.addTab(self.tab_backup, "DB Backup Config")
        self.tabs.addTab(self.tab_retention, "Data Retention Rules")
        self.tabs.addTab(self.tab_mes, "MES Automation")
        
        main_layout.addWidget(self.tabs, 3)
        
        # BOTTOM: Log Console Box
        self.log_console = QTextEdit()
        self.log_console.setObjectName("LogConsole")
        self.log_console.setReadOnly(True)
        self.log_console.setMinimumHeight(150)
        self.log_console.setMaximumHeight(200)
        main_layout.addWidget(self.log_console, 1)

    def setup_backup_tab(self):
        tab_layout = QHBoxLayout(self.tab_backup)
        tab_layout.setContentsMargins(15, 15, 15, 15)
        tab_layout.setSpacing(15)
        
        # Left Panel: Manual Backups
        card_manual = QFrame()
        card_manual.setObjectName("CardFrame")
        col_manual_layout = QVBoxLayout(card_manual)
        col_manual_layout.setSpacing(10)
        
        b_title = QLabel("Manual Schema Backup")
        b_title.setStyleSheet("font-size: 15px; font-weight: bold; color: #6366f1; margin-bottom: 5px;")
        col_manual_layout.addWidget(b_title)
        
        self.lbl_selected_db = QLabel("No active profile configured.")
        self.lbl_selected_db.setStyleSheet("font-weight: bold; color: #ef4444;")
        col_manual_layout.addWidget(self.lbl_selected_db)
        
        col_manual_layout.addWidget(QLabel("Select Schemas to Backup:"))
        self.chk_select_all = QCheckBox("Select All")
        self.chk_select_all.stateChanged.connect(self.on_select_all_changed)
        col_manual_layout.addWidget(self.chk_select_all)
        
        self.list_databases = QListWidget()
        self.list_databases.setMinimumHeight(120)
        self.list_databases.setMaximumHeight(180)
        self.list_databases.setObjectName("DatabaseList")
        col_manual_layout.addWidget(self.list_databases)
        
        self.chk_compress = QCheckBox("Compress manual backups (.sql.gz format)")
        self.chk_compress.setChecked(True)
        col_manual_layout.addWidget(self.chk_compress)
        
        self.btn_backup_now = QPushButton("Backup Selected Schemas Now")
        self.btn_backup_now.setObjectName("PrimaryButton")
        self.btn_backup_now.setFixedHeight(35)
        self.btn_backup_now.clicked.connect(self.trigger_manual_backup)
        col_manual_layout.addWidget(self.btn_backup_now)
        col_manual_layout.addStretch()
        
        tab_layout.addWidget(card_manual, 1)
        
        # Right Panel: Automated Recurrent Schedule
        card_schedule = QFrame()
        card_schedule.setObjectName("CardFrame")
        col_sched_layout = QVBoxLayout(card_schedule)
        col_sched_layout.setSpacing(10)
        
        sched_title = QLabel("Automated Backup Schedule")
        sched_title.setStyleSheet("font-size: 15px; font-weight: bold; color: #10b981; margin-bottom: 5px;")
        col_sched_layout.addWidget(sched_title)
        
        self.chk_b_sched_enable = QCheckBox("Enable Recurrent Backups")
        self.chk_b_sched_enable.stateChanged.connect(self.toggle_backup_schedule_inputs)
        col_sched_layout.addWidget(self.chk_b_sched_enable)
        
        col_sched_layout.addWidget(QLabel("Recurrence Frequency:"))
        self.cb_b_freq = QComboBox()
        self.cb_b_freq.addItems(["Every 4 Hours", "Daily", "Weekly", "Monthly"])
        self.cb_b_freq.currentIndexChanged.connect(self.toggle_backup_frequency_inputs)
        col_sched_layout.addWidget(self.cb_b_freq)
        
        b_time_layout = QHBoxLayout()
        self.lbl_time_type = QLabel("Scheduled Time:")
        b_time_layout.addWidget(self.lbl_time_type)
        self.time_b_edit = QTimeEdit()
        self.time_b_edit.setTime(QTime(2, 0))
        b_time_layout.addWidget(self.time_b_edit)
        col_sched_layout.addLayout(b_time_layout)
        
        col_sched_layout.addWidget(QLabel("Day of Week/Month:"))
        self.cb_b_day_week = QComboBox()
        self.cb_b_day_week.addItems(["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"])
        col_sched_layout.addWidget(self.cb_b_day_week)
        
        self.spin_b_day_month = QSpinBox()
        self.spin_b_day_month.setRange(1, 31)
        col_sched_layout.addWidget(self.spin_b_day_month)
        
        self.chk_b_headless = QCheckBox("Run when closed (Windows Task)")
        col_sched_layout.addWidget(self.chk_b_headless)
        
        self.btn_save_backup_schedule = QPushButton("Save Backup Schedule")
        self.btn_save_backup_schedule.setObjectName("SuccessButton")
        self.btn_save_backup_schedule.clicked.connect(self.save_backup_schedule)
        col_sched_layout.addWidget(self.btn_save_backup_schedule)
        col_sched_layout.addStretch()
        
        tab_layout.addWidget(card_schedule, 1)

    def setup_retention_tab(self):
        tab_layout = QHBoxLayout(self.tab_retention)
        tab_layout.setContentsMargins(15, 15, 15, 15)
        tab_layout.setSpacing(15)
        
        # Left side: Rule creation form card
        card_form = QFrame()
        card_form.setObjectName("CardFrame")
        col_retention_layout = QVBoxLayout(card_form)
        col_retention_layout.setSpacing(10)
        
        r_title = QLabel("Retention Deletion Rule Editor")
        r_title.setStyleSheet("font-size: 15px; font-weight: bold; color: #0ea5e9; margin-bottom: 5px;")
        col_retention_layout.addWidget(r_title)
        
        # Form layout for compact fields
        form_layout = QFormLayout()
        form_layout.setSpacing(8)
        form_layout.setLabelAlignment(Qt.AlignRight)
        
        # Database Selection
        self.cb_db = QComboBox()
        self.cb_db.currentIndexChanged.connect(self.on_db_changed)
        form_layout.addRow("Database:", self.cb_db)
        
        # Table Selection
        self.cb_table = QComboBox()
        self.cb_table.currentIndexChanged.connect(self.on_table_changed)
        form_layout.addRow("Table:", self.cb_table)
        
        # Column Selection
        self.cb_column = QComboBox()
        form_layout.addRow("Date Column:", self.cb_column)
        
        # Retention Window
        self.spin_months = QSpinBox()
        self.spin_months.setRange(1, 120)
        self.spin_months.setValue(6)
        form_layout.addRow("Retain (Mo):", self.spin_months)
        
        col_retention_layout.addLayout(form_layout)
        
        self.chk_rule_enabled = QCheckBox("Enable this rule")
        self.chk_rule_enabled.setChecked(True)
        col_retention_layout.addWidget(self.chk_rule_enabled)
        
        # Action Buttons
        r_act_layout = QHBoxLayout()
        self.btn_dry_run = QPushButton("Simulate (Dry Run)")
        self.btn_dry_run.clicked.connect(self.trigger_dry_run)
        r_act_layout.addWidget(self.btn_dry_run)
        
        self.btn_clean_now = QPushButton("Clean Up Now")
        self.btn_clean_now.setObjectName("DangerButton")
        self.btn_clean_now.clicked.connect(self.trigger_immediate_cleanup)
        r_act_layout.addWidget(self.btn_clean_now)
        col_retention_layout.addLayout(r_act_layout)
        
        self.btn_save_rule = QPushButton("Add New Rule")
        self.btn_save_rule.setObjectName("PrimaryButton")
        self.btn_save_rule.clicked.connect(self.save_rule)
        col_retention_layout.addWidget(self.btn_save_rule)
        col_retention_layout.addStretch()
        
        tab_layout.addWidget(card_form, 1)
        
        # Right side: Table list card
        card_table = QFrame()
        card_table.setObjectName("CardFrame")
        table_layout = QVBoxLayout(card_table)
        table_layout.setSpacing(10)
        
        table_title = QLabel("Active Retention Rules")
        table_title.setStyleSheet("font-size: 15px; font-weight: bold; color: #10b981; margin-bottom: 5px;")
        table_layout.addWidget(table_title)
        
        self.table_rules = QTableWidget()
        self.table_rules.setColumnCount(5)
        self.table_rules.setHorizontalHeaderLabels(["DB", "Table", "Column", "Retain", "Status"])
        self.table_rules.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_rules.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table_rules.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_rules.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table_rules.verticalHeader().setVisible(False)
        self.table_rules.itemSelectionChanged.connect(self.on_rule_row_selected)
        table_layout.addWidget(self.table_rules)
        
        r_row_btns = QHBoxLayout()
        self.btn_delete_rule = QPushButton("Delete Rule")
        self.btn_delete_rule.setObjectName("DangerButton")
        self.btn_delete_rule.clicked.connect(self.delete_rule)
        r_row_btns.addWidget(self.btn_delete_rule)
        
        self.btn_new_rule = QPushButton("Reset Selection")
        self.btn_new_rule.clicked.connect(self.reset_selection)
        r_row_btns.addWidget(self.btn_new_rule)
        table_layout.addLayout(r_row_btns)
        
        tab_layout.addWidget(card_table, 2)

    def setup_mes_tab(self):
        tab_layout = QVBoxLayout(self.tab_mes)
        tab_layout.setContentsMargins(15, 15, 15, 15)
        tab_layout.setSpacing(15)
        
        # Top panel: Status & Actions (Horizontal Layout)
        top_panels = QHBoxLayout()
        top_panels.setSpacing(15)
        
        # Left Panel: Status Control
        self.card_mes_status = QFrame()
        self.card_mes_status.setObjectName("CardFrame")
        status_layout = QVBoxLayout(self.card_mes_status)
        status_layout.setSpacing(10)
        
        status_title = QLabel("MES AUTOMATION STATUS")
        status_title.setStyleSheet("font-size: 12px; font-weight: bold; color: #6366f1; margin-bottom: 2px;")
        status_layout.addWidget(status_title)
        
        self.lbl_mes_status = QLabel("🔴 Stopped")
        self.lbl_mes_status.setStyleSheet("font-size: 18px; font-weight: bold; color: #ef4444;")
        status_layout.addWidget(self.lbl_mes_status)
        
        self.lbl_mes_desc = QLabel("Automated 24/7 scraping is disabled.")
        self.lbl_mes_desc.setStyleSheet("font-size: 12px; color: #a1a1aa;")
        status_layout.addWidget(self.lbl_mes_desc)
        
        btns_layout = QHBoxLayout()
        self.btn_toggle_mes = QPushButton("Start Automation")
        self.btn_toggle_mes.setObjectName("SuccessButton")
        self.btn_toggle_mes.clicked.connect(self.toggle_mes_scheduler)
        btns_layout.addWidget(self.btn_toggle_mes)
        
        self.btn_run_now = QPushButton("Run Scraper Now")
        self.btn_run_now.setObjectName("PrimaryButton")
        self.btn_run_now.clicked.connect(self.trigger_manual_scrape)
        btns_layout.addWidget(self.btn_run_now)
        status_layout.addLayout(btns_layout)
        status_layout.addStretch()
        
        top_panels.addWidget(self.card_mes_status, 1)
        
        # Right Panel: Last Execution Metrics
        self.card_mes_metrics = QFrame()
        self.card_mes_metrics.setObjectName("CardFrame")
        metrics_layout = QVBoxLayout(self.card_mes_metrics)
        metrics_layout.setSpacing(8)
        
        metrics_title = QLabel("LAST SCRAPING RUN METRICS")
        metrics_title.setStyleSheet("font-size: 12px; font-weight: bold; color: #10b981; margin-bottom: 2px;")
        metrics_layout.addWidget(metrics_title)
        
        self.lbl_mes_last_run = QLabel("Last Run: Never")
        self.lbl_mes_last_run.setStyleSheet("font-size: 14px; font-weight: bold; color: #e4e4e7;")
        metrics_layout.addWidget(self.lbl_mes_last_run)
        
        self.lbl_mes_mode = QLabel("Scraper Mode: --")
        self.lbl_mes_mode.setStyleSheet("font-size: 12px; color: #a1a1aa;")
        metrics_layout.addWidget(self.lbl_mes_mode)
        
        self.lbl_mes_next_run = QLabel("Next Run: --")
        self.lbl_mes_next_run.setStyleSheet("font-size: 12px; color: #a1a1aa;")
        metrics_layout.addWidget(self.lbl_mes_next_run)
        
        metrics_layout.addStretch()
        top_panels.addWidget(self.card_mes_metrics, 1)
        
        tab_layout.addLayout(top_panels, 1)
        
        # Bottom panel: Database Record Counts Table
        card_db_counts = QFrame()
        card_db_counts.setObjectName("CardFrame")
        db_layout = QVBoxLayout(card_db_counts)
        db_layout.setSpacing(10)
        
        db_title_layout = QHBoxLayout()
        db_title = QLabel("MES Database Target Tables & Record Counts")
        db_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #38bdf8;")
        db_title_layout.addWidget(db_title)
        
        self.btn_refresh_counts = QPushButton("🔄 Refresh Counts")
        self.btn_refresh_counts.setFixedWidth(120)
        self.btn_refresh_counts.clicked.connect(self.refresh_mes_table_counts)
        db_title_layout.addWidget(self.btn_refresh_counts)
        db_layout.addLayout(db_title_layout)
        
        self.table_mes_counts = QTableWidget()
        self.table_mes_counts.setColumnCount(3)
        self.table_mes_counts.setHorizontalHeaderLabels(["Table Name", "Total Record Count", "Data Size (MB)"])
        self.table_mes_counts.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_mes_counts.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table_mes_counts.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_mes_counts.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table_mes_counts.verticalHeader().setVisible(False)
        db_layout.addWidget(self.table_mes_counts)
        
        tab_layout.addWidget(card_db_counts, 2)

    def refresh_page(self):
        """Update active server connection profile status and schemas lists."""
        profile = self.main_window.active_profile
        config = self.main_window.config
        b_settings = config.get("backup_settings", {})
        
        self.list_databases.clear()
        self.databases = []
        self.cb_db.clear()
        self.cb_table.clear()
        self.cb_column.clear()
        
        if not profile:
            self.lbl_selected_db.setText("No active connection profile.")
            self.lbl_selected_db.setStyleSheet("font-weight: bold; color: #ef4444;")
            self.btn_backup_now.setEnabled(False)
            self.btn_dry_run.setEnabled(False)
            self.btn_clean_now.setEnabled(False)
            return
            
        self.lbl_selected_db.setText(f"Active Connection: '{profile.get('name')}'")
        self.lbl_selected_db.setStyleSheet("font-weight: bold; color: #10b981;")
        self.btn_backup_now.setEnabled(True)
        self.btn_dry_run.setEnabled(True)
        self.btn_clean_now.setEnabled(True)
        
        # Test connection & load available databases
        success, _ = MySQLConnectionManager.test_connection(profile)
        if not success:
            return
            
        mgr = MySQLConnectionManager(profile)
        self.databases = mgr.get_databases()
        
        # Load saved schemas from config
        saved_schemas = b_settings.get("schemas", [])
        for db in self.databases:
            item = QListWidgetItem(db)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            if db in saved_schemas:
                item.setCheckState(Qt.Checked)
            else:
                item.setCheckState(Qt.Unchecked)
            self.list_databases.addItem(item)
            
        # Set up retention database dropdown list
        self.cb_db.addItems(self.databases)
        def_db = profile.get("database")
        if def_db and def_db in self.databases:
            self.cb_db.setCurrentIndex(self.cb_db.findText(def_db))
            
        # Refresh MES tab too
        try:
            self.refresh_mes_tab()
        except AttributeError:
            pass

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
        
        first_date_idx = -1
        for idx, col in enumerate(self.columns):
            label = f"{col['name']} ({col['type']})"
            if col['is_date']:
                label += " [DATE]"
                if first_date_idx == -1:
                    first_date_idx = idx
            self.cb_column.addItem(label, col['name'])
            
        if first_date_idx != -1:
            self.cb_column.setCurrentIndex(first_date_idx)

    def load_settings(self):
        config = load_config()
        
        # 1. Load Backup settings
        b_settings = config.get("backup_settings", {})
        self.chk_b_sched_enable.setChecked(b_settings.get("schedule_enabled", False))
        
        freq_map = {"daily": 0, "weekly": 1, "monthly": 2}
        self.cb_b_freq.setCurrentIndex(freq_map.get(b_settings.get("schedule_type", "daily").lower(), 0))
        
        time_str = b_settings.get("schedule_time", "02:00")
        try:
            h, m = map(int, time_str.split(":"))
            self.time_b_edit.setTime(QTime(h, m))
        except Exception:
            self.time_b_edit.setTime(QTime(2, 0))
            
        b_day = b_settings.get("schedule_day", 1)
        self.cb_b_day_week.setCurrentIndex(max(0, min(b_day - 1, 6)))
        self.spin_b_day_month.setValue(max(1, min(b_day, 31)))
        
        self.chk_b_headless.setChecked(b_settings.get("run_headless", False))
        
        # 2. Load Retention Rules settings
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
            
        self.toggle_backup_schedule_inputs()
        self.reset_selection()
        self.refresh_page()

    def toggle_backup_schedule_inputs(self):
        enabled = self.chk_b_sched_enable.isChecked()
        self.cb_b_freq.setEnabled(enabled)
        self.time_b_edit.setEnabled(enabled)
        self.chk_b_headless.setEnabled(enabled)
        self.toggle_backup_frequency_inputs()

    def toggle_backup_frequency_inputs(self):
        if not self.chk_b_sched_enable.isChecked():
            self.cb_b_day_week.hide()
            self.spin_b_day_month.hide()
            return
            
        freq = self.cb_b_freq.currentText()
        if freq == "Every 4 Hours":
            self.lbl_time_type.setText("Start Time:")
            self.cb_b_day_week.hide()
            self.spin_b_day_month.hide()
        elif freq == "Daily":
            self.lbl_time_type.setText("Scheduled Time:")
            self.cb_b_day_week.hide()
            self.spin_b_day_month.hide()
        elif freq == "Weekly":
            self.lbl_time_type.setText("Scheduled Time:")
            self.cb_b_day_week.show()
            self.spin_b_day_month.hide()
        elif freq == "Monthly":
            self.lbl_time_type.setText("Scheduled Time:")
            self.cb_b_day_week.hide()
            self.spin_b_day_month.show()

    def on_select_all_changed(self):
        state = self.chk_select_all.checkState()
        for idx in range(self.list_databases.count()):
            item = self.list_databases.item(idx)
            item.setCheckState(state)

    def save_backup_schedule(self):
        config = load_config()
        b_settings = config.get("backup_settings", {})
        
        # Schemas
        selected_schemas = []
        for idx in range(self.list_databases.count()):
            item = self.list_databases.item(idx)
            if item.checkState() == Qt.Checked:
                selected_schemas.append(item.text())
        b_settings["schemas"] = selected_schemas
        
        # Schedule settings
        enabled = self.chk_b_sched_enable.isChecked()
        freq = self.cb_b_freq.currentText().lower()
        time_str = self.time_b_edit.time().toString("hh:mm")
        
        if freq == "weekly":
            day_val = self.cb_b_day_week.currentIndex() + 1
        elif freq == "monthly":
            day_val = self.spin_b_day_month.value()
        else:
            day_val = 1
            
        headless = self.chk_b_headless.isChecked()
        
        b_settings["schedule_enabled"] = enabled
        b_settings["schedule_type"] = freq
        b_settings["schedule_time"] = time_str
        b_settings["schedule_day"] = day_val
        b_settings["run_headless"] = headless
        
        config["backup_settings"] = b_settings
        save_config(config)
        
        logger.info("Saved backup recurrence schedule configuration.")
        
        if enabled and headless:
            success, msg = register_windows_task("backup", freq, time_str, day_val)
            if success:
                QMessageBox.information(self, "Backup Schedule", "Backup schedule task registered via Windows Task Scheduler.")
            else:
                QMessageBox.warning(self, "Backup Schedule Warning", f"Could not register Windows Task: {msg}")
        else:
            unregister_windows_task("backup")
            QMessageBox.information(self, "Backup Schedule", "Backup schedule configurations saved.")
            
        self.main_window.update_profile_display()

    def trigger_manual_backup(self):
        profile = self.main_window.active_profile
        if not profile:
            QMessageBox.warning(self, "No Connection Profile", "Active profile required for database backups.")
            return
            
        selected_schemas = []
        for idx in range(self.list_databases.count()):
            item = self.list_databases.item(idx)
            if item.checkState() == Qt.Checked:
                selected_schemas.append(item.text())
                
        if not selected_schemas:
            QMessageBox.warning(self, "Selection Required", "Please select at least one database schema.")
            return
            
        config = load_config()
        config["backup_settings"]["schemas"] = selected_schemas
        config["backup_settings"]["compress"] = self.chk_compress.isChecked()
        save_config(config)
        
        self.btn_backup_now.setEnabled(False)
        self.btn_backup_now.setText("Backing Up... Please Wait")
        self.repaint()
        
        def worker():
            try:
                b_settings = load_config().get("backup_settings", {})
                success, msg = run_backup_task(profile, b_settings)
                QMetaObject.invokeMethod(self, "on_backup_complete", Qt.QueuedConnection, 
                                         Q_ARG(bool, success), Q_ARG(str, msg))
            except Exception as e:
                logger.error(f"Manual backup background process failed: {str(e)}")
                
        t = threading.Thread(target=worker)
        t.daemon = True
        t.start()

    @Slot(bool, str)
    def on_backup_complete(self, success: bool, message: str):
        self.btn_backup_now.setEnabled(True)
        self.btn_backup_now.setText("Backup Selected Schemas Now")
        if success:
            QMessageBox.information(self, "Backup Complete", f"Backup executed successfully!\n\n{message}")
        else:
            QMessageBox.critical(self, "Backup Failed", f"Database backup failed:\n\n{message}")
        self.main_window.dashboard_page.refresh_page()

    # Retention Logic handlers
    def on_rule_row_selected(self):
        selected_ranges = self.table_rules.selectedRanges()
        if not selected_ranges:
            return
        row = selected_ranges[0].topRow()
        self.selected_rule_idx = row
        
        config = load_config()
        rule = config.get("retention_rules", [])[row]
        
        db = rule.get("db")
        table = rule.get("table")
        col = rule.get("column")
        
        if db in self.databases:
            self.cb_db.setCurrentIndex(self.cb_db.findText(db))
            if table in self.tables:
                self.cb_table.setCurrentIndex(self.cb_table.findText(table))
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
            "db": db, "table": table, "column": col, "months": months, "enabled": enabled
        }
        
        if self.selected_rule_idx is not None and self.selected_rule_idx < len(rules):
            rules[self.selected_rule_idx] = rule_data
            logger.info(f"Updated retention rule details: {db}.{table}.{col}")
        else:
            for r in rules:
                if r["db"] == db and r["table"] == table and r["column"] == col:
                    QMessageBox.warning(self, "Duplicate Rule", "Rule configuration already exists for this table column.")
                    return
            rules.append(rule_data)
            logger.info(f"Added new retention rule: {db}.{table}.{col}")
            
        config["retention_rules"] = rules
        save_config(config)
        self.load_settings()
        QMessageBox.information(self, "Success", "Data retention rule saved.")

    def delete_rule(self):
        if self.selected_rule_idx is None:
            QMessageBox.warning(self, "Selection Required", "Select a rule to delete.")
            return
            
        ret = QMessageBox.question(self, "Confirm Delete", "Delete selected retention rule?", QMessageBox.Yes | QMessageBox.No)
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

    def trigger_dry_run(self):
        profile = self.main_window.active_profile
        if not profile:
            QMessageBox.warning(self, "No Connection Profile", "Active profile required for dry run simulations.")
            return
            
        db = self.cb_db.currentText()
        table = self.cb_table.currentText()
        col = self.cb_column.currentData()
        months = self.spin_months.value()
        
        if not db or not table or not col:
            QMessageBox.warning(self, "Validation Error", "Verify Database, Table, and Column details.")
            return
            
        self.btn_dry_run.setEnabled(False)
        self.btn_dry_run.setText("Simulating...")
        self.repaint()
        
        def worker():
            try:
                mgr = MySQLCleanupManager(profile)
                success, count, msg = mgr.run_dry_run(db, table, col, months)
                QMetaObject.invokeMethod(self, "on_dry_run_complete", Qt.QueuedConnection,
                                         Q_ARG(bool, success), Q_ARG(int, count), Q_ARG(str, msg))
            except Exception as e:
                logger.error(f"Dry run execution failed: {str(e)}")
                
        t = threading.Thread(target=worker)
        t.daemon = True
        t.start()

    @Slot(bool, int, str)
    def on_dry_run_complete(self, success: bool, count: int, message: str):
        self.btn_dry_run.setEnabled(True)
        self.btn_dry_run.setText("Simulate (Dry Run)")
        if success:
            QMessageBox.information(self, "Dry Run Result", f"Simulation Complete!\n\nTarget table: `{self.cb_db.currentText()}`.`{self.cb_table.currentText()}`\nCutoff: older than {self.spin_months.value()} months\n\nRows matched for deletion: {count:,}")
        else:
            QMessageBox.critical(self, "Simulation Failed", f"Dry run simulation error:\n\n{message}")

    def trigger_immediate_cleanup(self):
        profile = self.main_window.active_profile
        if not profile:
            QMessageBox.warning(self, "No Active Profile", "Active profile required for cleanups.")
            return
            
        db = self.cb_db.currentText()
        table = self.cb_table.currentText()
        col = self.cb_column.currentData()
        months = self.spin_months.value()
        
        if not db or not table or not col:
            QMessageBox.warning(self, "Validation Error", "Verify Database, Table, and Column details.")
            return
            
        ret = QMessageBox.warning(self, "CRITICAL WARNING: DATA DELETION",
                                  f"You are about to PERMANENTLY PURGE data from `{db}`.`{table}` where `{col}` is older than {months} months.\n\n"
                                  "This action cannot be undone. Continue?",
                                  QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if ret == QMessageBox.No:
            return
            
        self.btn_clean_now.setEnabled(False)
        self.btn_clean_now.setText("Deleting Rows...")
        self.repaint()
        
        def worker():
            try:
                mgr = MySQLCleanupManager(profile)
                success, total_deleted, msg = mgr.run_cleanup(db, table, col, months)
                QMetaObject.invokeMethod(self, "on_cleanup_complete", Qt.QueuedConnection,
                                         Q_ARG(bool, success), Q_ARG(int, total_deleted), Q_ARG(str, msg))
            except Exception as e:
                logger.error(f"Immediate database purge failed: {str(e)}")
                
        t = threading.Thread(target=worker)
        t.daemon = True
        t.start()

    @Slot(bool, int, str)
    def on_cleanup_complete(self, success: bool, total_deleted: int, message: str):
        self.btn_clean_now.setEnabled(True)
        self.btn_clean_now.setText("Clean Up Now")
        if success:
            QMessageBox.information(self, "Cleanup Complete", f"Data retention cleanup successful!\n\nTotal rows deleted: {total_deleted:,}")
        else:
            QMessageBox.critical(self, "Cleanup Failed", f"Cleanup operation encountered errors:\n\n{message}")
        self.main_window.dashboard_page.refresh_page()

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

    def on_tab_changed(self, index):
        if index == 2:  # MES Automation Tab
            self.refresh_mes_tab()

    def refresh_mes_tab(self):
        config = load_config()
        mes_settings = config.get("mes_scraper_settings", {})
        
        enabled = mes_settings.get("schedule_enabled", False)
        interval = mes_settings.get("interval_minutes", 5)
        offline = mes_settings.get("offline_mode", True)
        
        self.lbl_mes_mode.setText(f"Scraper Mode: {'Offline / Mock' if offline else 'Online / Live MES'}")
        
        if enabled:
            self.lbl_mes_status.setText(f"🟢 Active (Every {interval}m)")
            self.lbl_mes_status.setStyleSheet("font-size: 18px; font-weight: bold; color: #10b981;")
            self.lbl_mes_desc.setText(f"Automated scraping schedule is running 24/7.")
            self.btn_toggle_mes.setText("Stop Automation")
            self.btn_toggle_mes.setObjectName("DangerButton")
        else:
            self.lbl_mes_status.setText("🔴 Stopped")
            self.lbl_mes_status.setStyleSheet("font-size: 18px; font-weight: bold; color: #ef4444;")
            self.lbl_mes_desc.setText("Automated scraping is disabled.")
            self.btn_toggle_mes.setText("Start Automation")
            self.btn_toggle_mes.setObjectName("SuccessButton")
            
        self.btn_toggle_mes.style().unpolish(self.btn_toggle_mes)
        self.btn_toggle_mes.style().polish(self.btn_toggle_mes)
            
        from src.scheduler import load_last_runs
        last_runs = load_last_runs()
        last_run_str = last_runs.get("mes_scraper", "")
        
        if last_run_str:
            self.lbl_mes_last_run.setText(f"Last Run: {last_run_str}")
            
            try:
                from datetime import datetime, timedelta
                last_run_dt = datetime.strptime(last_run_str, "%Y-%m-%d %H:%M:%S")
                next_run_dt = last_run_dt + timedelta(minutes=interval)
                self.lbl_mes_next_run.setText(f"Next Run: {next_run_dt.strftime('%Y-%m-%d %H:%M:%S')}")
            except Exception:
                self.lbl_mes_next_run.setText("Next Run: Error calculating")
        else:
            self.lbl_mes_last_run.setText("Last Run: Never")
            if enabled:
                self.lbl_mes_next_run.setText("Next Run: Due Imminently")
            else:
                self.lbl_mes_next_run.setText("Next Run: --")
                
        self.refresh_mes_table_counts()

    def refresh_mes_table_counts(self):
        profile = self.main_window.active_profile
        self.table_mes_counts.setRowCount(0)
        
        target_tables = [
            "wip_status", "wip_status_snapshot",
            "monthly_plan", "monthly_plan_snapshot",
            "process_result", "process_result_snapshot",
            "process_trackout", "process_trackout_snapshot",
            "eqp_detailed_history", "eqp_detailed_history_snapshot"
        ]
        
        if not profile:
            self.table_mes_counts.setRowCount(len(target_tables))
            for idx, tbl in enumerate(target_tables):
                self.table_mes_counts.setItem(idx, 0, QTableWidgetItem(tbl))
                self.table_mes_counts.setItem(idx, 1, QTableWidgetItem("Offline / Disconnected"))
                self.table_mes_counts.setItem(idx, 2, QTableWidgetItem("--"))
            return
            
        mgr = MySQLConnectionManager(profile)
        db_name = profile.get("database", "mes_data")
        
        try:
            stats = mgr.get_table_stats(db_name)
            stats_dict = {row["name"]: row for row in stats}
        except Exception as e:
            logger.error(f"Failed to query database table statistics: {e}")
            stats_dict = {}
            
        self.table_mes_counts.setRowCount(len(target_tables))
        for idx, tbl in enumerate(target_tables):
            row_data = stats_dict.get(tbl)
            
            tbl_item = QTableWidgetItem(tbl)
            self.table_mes_counts.setItem(idx, 0, tbl_item)
            
            if row_data:
                rows_item = QTableWidgetItem(f"{row_data['rows']:,}")
                rows_item.setTextAlignment(Qt.AlignCenter)
                self.table_mes_counts.setItem(idx, 1, rows_item)
                
                size_item = QTableWidgetItem(f"{row_data['size_mb']:.2f} MB")
                size_item.setTextAlignment(Qt.AlignCenter)
                self.table_mes_counts.setItem(idx, 2, size_item)
            else:
                try:
                    conn = mgr.get_connection()
                    with conn.cursor() as cursor:
                        cursor.execute(f"SELECT COUNT(*) as cnt FROM `{db_name}`.`{tbl}`")
                        cnt = cursor.fetchone()["cnt"]
                        rows_item = QTableWidgetItem(f"{cnt:,}")
                        rows_item.setTextAlignment(Qt.AlignCenter)
                        self.table_mes_counts.setItem(idx, 1, rows_item)
                    conn.close()
                except Exception:
                    rows_item = QTableWidgetItem("Table not created")
                    rows_item.setTextAlignment(Qt.AlignCenter)
                    rows_item.setForeground(Qt.gray)
                    self.table_mes_counts.setItem(idx, 1, rows_item)
                    
                self.table_mes_counts.setItem(idx, 2, QTableWidgetItem("--"))

    def toggle_mes_scheduler(self):
        config = load_config()
        mes_settings = config.get("mes_scraper_settings", {})
        
        enabled = not mes_settings.get("schedule_enabled", False)
        mes_settings["schedule_enabled"] = enabled
        
        config["mes_scraper_settings"] = mes_settings
        save_config(config)
        
        if enabled:
            logger.info("Background MES Scraper automation scheduler enabled.")
            QMessageBox.information(self, "Scheduler Active", "MES Scraper scheduler activated. It will run in the background every 5 minutes.")
        else:
            logger.info("Background MES Scraper automation scheduler disabled.")
            QMessageBox.information(self, "Scheduler Stopped", "MES Scraper scheduler deactivated.")
            
        self.refresh_mes_tab()

    def trigger_manual_scrape(self):
        profile = self.main_window.active_profile
        if not profile:
            QMessageBox.warning(self, "No Active Profile", "Active connection profile required to write scraped data.")
            return
            
        self.btn_run_now.setEnabled(False)
        self.btn_run_now.setText("Scraping...")
        self.lbl_mes_status.setText("🔄 Scraping in progress...")
        self.lbl_mes_status.setStyleSheet("font-size: 18px; font-weight: bold; color: #38bdf8;")
        self.repaint()
        
        config = load_config()
        offline = config.get("mes_scraper_settings", {}).get("offline_mode", True)
        
        def worker():
            try:
                from src.scheduler import run_mes_scraper_task
                success, msg = run_mes_scraper_task(offline=offline)
                QMetaObject.invokeMethod(self, "on_scrape_complete", Qt.QueuedConnection,
                                         Q_ARG(bool, success), Q_ARG(str, msg))
            except Exception as e:
                logger.error(f"Manual scraping runner exception: {e}")
                QMetaObject.invokeMethod(self, "on_scrape_complete", Qt.QueuedConnection,
                                         Q_ARG(bool, False), Q_ARG(str, str(e)))
                
        t = threading.Thread(target=worker)
        t.daemon = True
        t.start()

    @Slot(bool, str)
    def on_scrape_complete(self, success: bool, message: str):
        self.btn_run_now.setEnabled(True)
        self.btn_run_now.setText("Run Scraper Now")
        if success:
            QMessageBox.information(self, "Success", "Scraping job completed and database records updated successfully!")
        else:
            QMessageBox.critical(self, "Scraper Failed", f"Scraper execution failed:\n\n{message}")
        self.refresh_mes_tab()
        self.main_window.dashboard_page.refresh_page()
