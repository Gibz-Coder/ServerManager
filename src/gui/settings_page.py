import uuid
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFrame, 
                               QLabel, QLineEdit, QPushButton, QCheckBox, 
                               QComboBox, QSpinBox, QMessageBox, QTimeEdit, 
                               QListWidget, QListWidgetItem, QTabWidget, 
                               QFormLayout, QFileDialog)
from PySide6.QtCore import Qt, QTime
from src.utils.config import load_config, save_config, encrypt_password, decrypt_password
from src.connection import MySQLConnectionManager
from src.scheduler import register_windows_task, unregister_windows_task
from src.utils.logger import logger

class SettingsPage(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.profiles = []
        self.selected_profile_id = None
        
        self.init_ui()
        self.load_settings()

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
        
        title = QLabel("Settings")
        title.setObjectName("PageTitle")
        title_text_layout.addWidget(title)
        
        subtitle = QLabel("Manage connection credentials, backup paths, automated cleanup schedules, and theme options.")
        subtitle.setObjectName("PageSubtitle")
        title_text_layout.addWidget(subtitle)
        
        header_layout.addLayout(title_text_layout)
        layout.addLayout(header_layout)
        
        # Tabs container
        self.tabs = QTabWidget()
        
        
        # Setup Tabs
        self.tab_connections = QWidget()
        self.tab_general_cleanup = QWidget()
        self.tab_appearance = QWidget()
        
        self.setup_connections_tab()
        self.setup_general_cleanup_tab()
        self.setup_appearance_tab()
        
        self.tabs.addTab(self.tab_connections, "Connection Profiles")
        self.tabs.addTab(self.tab_general_cleanup, "General & Cleanup Recurrence")
        self.tabs.addTab(self.tab_appearance, "Appearance & Theme")
        
        layout.addWidget(self.tabs)

    def setup_connections_tab(self):
        # Connections Layout
        tab_layout = QHBoxLayout(self.tab_connections)
        tab_layout.setContentsMargins(15, 15, 15, 15)
        tab_layout.setSpacing(15)
        
        # Left Panel: Connections Form
        form_frame = QFrame()
        form_frame.setObjectName("CardFrame")
        form_layout = QFormLayout(form_frame)
        form_layout.setSpacing(10)
        form_layout.setLabelAlignment(Qt.AlignRight)
        
        form_title = QLabel("Server Configuration")
        form_title.setObjectName("FormHeader")
        form_layout.addRow(form_title)
        
        self.txt_name = QLineEdit()
        self.txt_name.setPlaceholderText("e.g. Local Development")
        form_layout.addRow("Profile Name:", self.txt_name)
        
        self.txt_host = QLineEdit()
        self.txt_host.setText("localhost")
        self.txt_host.setPlaceholderText("127.0.0.1 or domain")
        form_layout.addRow("Host / IP Address:", self.txt_host)
        
        self.txt_port = QLineEdit()
        self.txt_port.setText("3306")
        self.txt_port.setPlaceholderText("3306")
        form_layout.addRow("Port Number:", self.txt_port)
        
        self.txt_user = QLineEdit()
        self.txt_user.setText("root")
        self.txt_user.setPlaceholderText("root")
        form_layout.addRow("Username:", self.txt_user)
        
        self.txt_password = QLineEdit()
        self.txt_password.setEchoMode(QLineEdit.Password)
        self.txt_password.setPlaceholderText("Password")
        form_layout.addRow("Password:", self.txt_password)
        
        self.txt_db = QLineEdit()
        self.txt_db.setPlaceholderText("Optional database name")
        form_layout.addRow("Default Database:", self.txt_db)
        
        # Form Buttons
        form_buttons_layout = QHBoxLayout()
        form_buttons_layout.setSpacing(10)
        
        self.btn_test = QPushButton("Test Connection")
        self.btn_test.clicked.connect(self.test_current_inputs)
        form_buttons_layout.addWidget(self.btn_test)
        
        self.btn_save = QPushButton("Save Profile")
        self.btn_save.setObjectName("PrimaryButton")
        self.btn_save.clicked.connect(self.save_current_profile)
        form_buttons_layout.addWidget(self.btn_save)
        form_layout.addRow("", form_buttons_layout)
        
        self.lbl_test_result = QLabel("")
        self.lbl_test_result.setWordWrap(True)
        self.lbl_test_result.setStyleSheet("font-size: 11px; margin-top: 5px;")
        form_layout.addRow("", self.lbl_test_result)
        
        tab_layout.addWidget(form_frame, 3)
        
        # Right Panel: Profiles list
        list_frame = QFrame()
        list_frame.setObjectName("CardFrame")
        list_layout = QVBoxLayout(list_frame)
        list_layout.setSpacing(10)
        
        list_title = QLabel("Saved Profiles")
        list_title.setObjectName("FormHeader")
        list_layout.addWidget(list_title)
        
        self.list_widget = QListWidget()
        self.list_widget.itemSelectionChanged.connect(self.on_profile_selected)
        list_layout.addWidget(self.list_widget)
        
        list_actions = QHBoxLayout()
        list_actions.setSpacing(8)
        
        self.btn_use = QPushButton("Use Active")
        self.btn_use.setObjectName("SuccessButton")
        self.btn_use.clicked.connect(self.set_profile_active)
        list_actions.addWidget(self.btn_use)
        
        self.btn_delete = QPushButton("Delete")
        self.btn_delete.setObjectName("DangerButton")
        self.btn_delete.clicked.connect(self.delete_selected_profile)
        list_actions.addWidget(self.btn_delete)
        
        self.btn_new = QPushButton("New")
        self.btn_new.clicked.connect(self.reset_form)
        list_actions.addWidget(self.btn_new)
        list_layout.addLayout(list_actions)
        
        tab_layout.addWidget(list_frame, 2)

    def setup_general_cleanup_tab(self):
        tab_layout = QVBoxLayout(self.tab_general_cleanup)
        tab_layout.setContentsMargins(15, 15, 15, 15)
        tab_layout.setSpacing(15)
        
        # General Settings Form Box
        gen_frame = QFrame()
        gen_frame.setObjectName("CardFrame")
        gen_layout = QFormLayout(gen_frame)
        gen_layout.setSpacing(10)
        gen_layout.setLabelAlignment(Qt.AlignRight)
        
        g_title = QLabel("General Database Management Configurations")
        g_title.setObjectName("FormHeader")
        gen_layout.addRow(g_title)
        
        # Backup Destination Folder Path
        dir_layout = QHBoxLayout()
        self.txt_backup_dir = QLineEdit()
        self.txt_backup_dir.setPlaceholderText("Select folder to store backup files")
        dir_layout.addWidget(self.txt_backup_dir)
        
        btn_browse_dir = QPushButton("Browse...")
        btn_browse_dir.clicked.connect(self.browse_backup_dir)
        dir_layout.addWidget(btn_browse_dir)
        gen_layout.addRow("Backup Folder:", dir_layout)
        
        # mysqldump Path
        dump_layout = QHBoxLayout()
        self.txt_dump_path = QLineEdit()
        self.txt_dump_path.setPlaceholderText("Path to mysqldump.exe (uses python native fallback if empty)")
        dump_layout.addWidget(self.txt_dump_path)
        
        btn_browse_dump = QPushButton("Browse...")
        btn_browse_dump.clicked.connect(self.browse_dump_path)
        dump_layout.addWidget(btn_browse_dump)
        gen_layout.addRow("mysqldump Path:", dump_layout)
        
        # Compression option
        self.chk_compress = QCheckBox("Compress scheduled backups (.sql.gz format)")
        self.chk_compress.setChecked(True)
        gen_layout.addRow("", self.chk_compress)
        
        btn_save_general = QPushButton("Save General Settings")
        btn_save_general.setObjectName("PrimaryButton")
        btn_save_general.setFixedHeight(35)
        btn_save_general.clicked.connect(self.save_general_settings)
        gen_layout.addRow("", btn_save_general)
        tab_layout.addWidget(gen_frame)
        
        # Cleanup Schedule Form Box
        cleanup_frame = QFrame()
        cleanup_frame.setObjectName("CardFrame")
        cleanup_layout = QVBoxLayout(cleanup_frame)
        cleanup_layout.setSpacing(10)
        
        c_title = QLabel("Cleanup Recurrence & Schedule settings")
        c_title.setObjectName("FormHeader")
        cleanup_layout.addWidget(c_title)
        
        self.chk_sched_enable = QCheckBox("Enable Automated Retention Cleanups")
        self.chk_sched_enable.stateChanged.connect(self.toggle_schedule_inputs)
        cleanup_layout.addWidget(self.chk_sched_enable)
        
        sched_opts = QHBoxLayout()
        sched_opts.setSpacing(10)
        
        self.cb_freq = QComboBox()
        self.cb_freq.addItems(["Daily", "Weekly", "Monthly"])
        self.cb_freq.currentIndexChanged.connect(self.toggle_frequency_inputs)
        sched_opts.addWidget(self.cb_freq)
        
        self.time_edit = QTimeEdit()
        self.time_edit.setTime(QTime(3, 0))
        sched_opts.addWidget(self.time_edit)
        
        self.cb_day_week = QComboBox()
        self.cb_day_week.addItems(["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"])
        sched_opts.addWidget(self.cb_day_week)
        
        self.spin_day_month = QSpinBox()
        self.spin_day_month.setRange(1, 31)
        sched_opts.addWidget(self.spin_day_month)
        
        cleanup_layout.addLayout(sched_opts)
        
        self.chk_headless = QCheckBox("Run when application is closed (Windows Task)")
        cleanup_layout.addWidget(self.chk_headless)
        
        self.btn_save_schedule = QPushButton("Save Cleanup Schedule Settings")
        self.btn_save_schedule.setObjectName("SuccessButton")
        self.btn_save_schedule.clicked.connect(self.save_cleanup_schedule)
        cleanup_layout.addWidget(self.btn_save_schedule)
        
        tab_layout.addWidget(cleanup_frame)
        tab_layout.addStretch()

    def setup_appearance_tab(self):
        tab_layout = QVBoxLayout(self.tab_appearance)
        tab_layout.setContentsMargins(15, 15, 15, 15)
        tab_layout.setSpacing(15)
        
        theme_frame = QFrame()
        theme_frame.setObjectName("CardFrame")
        theme_layout = QFormLayout(theme_frame)
        theme_layout.setSpacing(12)
        
        theme_title = QLabel("UI Customization & Themes")
        theme_title.setObjectName("FormHeader")
        theme_layout.addRow(theme_title)
        
        self.cb_theme = QComboBox()
        self.cb_theme.addItems(["Dark Mode", "Light Mode", "Midnight Blue"])
        theme_layout.addRow("Select Theme Style:", self.cb_theme)
        
        btn_save_theme = QPushButton("Apply & Save Theme Style")
        btn_save_theme.setObjectName("PrimaryButton")
        btn_save_theme.setFixedHeight(35)
        btn_save_theme.clicked.connect(self.save_theme_setting)
        theme_layout.addRow("", btn_save_theme)
        
        tab_layout.addWidget(theme_frame)
        tab_layout.addStretch()

    def browse_backup_dir(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Select Backup Destination Directory")
        if dir_path:
            self.txt_backup_dir.setText(dir_path)

    def browse_dump_path(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Locate mysqldump.exe", "", "Executables (mysqldump.exe)")
        if file_path:
            self.txt_dump_path.setText(file_path)

    def load_settings(self):
        """Loads profiles, configuration path details, schedules, and themes."""
        config = load_config()
        self.load_profiles_list()
        
        # General & Recurrence
        b_settings = config.get("backup_settings", {})
        self.txt_backup_dir.setText(b_settings.get("backup_dir", ""))
        self.txt_dump_path.setText(b_settings.get("mysqldump_path", ""))
        self.chk_compress.setChecked(b_settings.get("compress", True))
        
        c_sched = config.get("retention_schedule", {})
        self.chk_sched_enable.setChecked(c_sched.get("schedule_enabled", False))
        
        freq_map = {"daily": 0, "weekly": 1, "monthly": 2}
        self.cb_freq.setCurrentIndex(freq_map.get(c_sched.get("schedule_type", "daily").lower(), 0))
        
        time_str = c_sched.get("schedule_time", "03:00")
        try:
            h, m = map(int, time_str.split(":"))
            self.time_edit.setTime(QTime(h, m))
        except Exception:
            self.time_edit.setTime(QTime(3, 0))
            
        day_val = c_sched.get("schedule_day", 1)
        self.cb_day_week.setCurrentIndex(max(0, min(day_val - 1, 6)))
        self.spin_day_month.setValue(max(1, min(day_val, 31)))
        
        self.chk_headless.setChecked(c_sched.get("run_headless", False))
        
        # Appearance
        saved_theme = config.get("theme", "Dark Mode")
        self.cb_theme.setCurrentText(saved_theme)
        
        self.toggle_schedule_inputs()

    def refresh_page(self):
        """Fires when MainWindow signals configuration reloads."""
        self.load_settings()

    # Connection profiles handlers
    def load_profiles_list(self):
        self.list_widget.clear()
        config = load_config()
        self.profiles = config.get("connection_profiles", [])
        active_id = config.get("active_profile_id")
        
        for profile in self.profiles:
            is_active = (profile.get("id") == active_id)
            display_name = profile.get("name", "Unnamed Profile")
            if is_active:
                display_name += " [ACTIVE]"
                
            item = QListWidgetItem(display_name)
            item.setData(Qt.UserRole, profile.get("id"))
            if is_active:
                item.setForeground(Qt.green)
            self.list_widget.addItem(item)
        self.reset_form()

    def on_profile_selected(self):
        selected_items = self.list_widget.selectedItems()
        if not selected_items:
            return
            
        profile_id = selected_items[0].data(Qt.UserRole)
        self.selected_profile_id = profile_id
        
        target_profile = None
        for p in self.profiles:
            if p.get("id") == profile_id:
                target_profile = p
                break
                
        if target_profile:
            self.txt_name.setText(target_profile.get("name", ""))
            self.txt_host.setText(target_profile.get("host", "localhost"))
            self.txt_port.setText(str(target_profile.get("port", 3306)))
            self.txt_user.setText(target_profile.get("user", "root"))
            self.txt_password.setText(decrypt_password(target_profile.get("password", "")))
            self.txt_db.setText(target_profile.get("database", ""))
            self.lbl_test_result.setText("")

    def reset_form(self):
        self.selected_profile_id = None
        self.list_widget.clearSelection()
        self.txt_name.clear()
        self.txt_host.setText("localhost")
        self.txt_port.setText("3306")
        self.txt_user.setText("root")
        self.txt_password.clear()
        self.txt_db.clear()
        self.lbl_test_result.setText("")

    def get_form_profile_dict(self) -> dict:
        return {
            "host": self.txt_host.text().strip(),
            "port": self.txt_port.text().strip(),
            "user": self.txt_user.text().strip(),
            "password": self.txt_password.text(),
            "database": self.txt_db.text().strip()
        }

    def test_current_inputs(self):
        self.lbl_test_result.setText("Testing connection...")
        self.lbl_test_result.setStyleSheet("color: #a1a1aa;")
        self.repaint()
        
        profile = self.get_form_profile_dict()
        if not profile["host"] or not profile["user"]:
            self.lbl_test_result.setText("Failed: Host and User fields cannot be empty.")
            self.lbl_test_result.setStyleSheet("color: #ef4444;")
            return
            
        success, msg = MySQLConnectionManager.test_connection(profile)
        if success:
            self.lbl_test_result.setText("✓ Connection successful!")
            self.lbl_test_result.setStyleSheet("color: #10b981; font-weight: bold;")
        else:
            self.lbl_test_result.setText(f"✗ Connection failed: {msg}")
            self.lbl_test_result.setStyleSheet("color: #ef4444;")

    def save_current_profile(self):
        name = self.txt_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Validation Error", "Please specify a Profile Name.")
            return
            
        profile_data = self.get_form_profile_dict()
        if not profile_data["host"] or not profile_data["user"]:
            QMessageBox.warning(self, "Validation Error", "Host and Username are required fields.")
            return
            
        config = load_config()
        profiles = config.get("connection_profiles", [])
        encrypted_pass = encrypt_password(profile_data["password"])
        
        if self.selected_profile_id:
            for idx, p in enumerate(profiles):
                if p.get("id") == self.selected_profile_id:
                    profiles[idx] = {
                        "id": self.selected_profile_id,
                        "name": name,
                        "host": profile_data["host"],
                        "port": int(profile_data["port"] or 3306),
                        "user": profile_data["user"],
                        "password": encrypted_pass,
                        "database": profile_data["database"]
                    }
                    break
            logger.info(f"Updated profile details: {name}")
        else:
            new_id = str(uuid.uuid4())
            new_profile = {
                "id": new_id,
                "name": name,
                "host": profile_data["host"],
                "port": int(profile_data["port"] or 3306),
                "user": profile_data["user"],
                "password": encrypted_pass,
                "database": profile_data["database"]
            }
            profiles.append(new_profile)
            self.selected_profile_id = new_id
            logger.info(f"Created new connection profile: {name}")
            
        config["connection_profiles"] = profiles
        save_config(config)
        
        self.load_profiles_list()
        for idx in range(self.list_widget.count()):
            item = self.list_widget.item(idx)
            if item.data(Qt.UserRole) == self.selected_profile_id:
                self.list_widget.setCurrentItem(item)
                break
        QMessageBox.information(self, "Success", "Profile saved successfully!")

    def set_profile_active(self):
        selected_items = self.list_widget.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Selection Required", "Please select a profile from the list.")
            return
            
        profile_id = selected_items[0].data(Qt.UserRole)
        config = load_config()
        config["active_profile_id"] = profile_id
        save_config(config)
        
        logger.info(f"Switched active connection profile ID to: {profile_id}")
        self.main_window.update_profile_display()
        self.load_profiles_list()
        
        for idx in range(self.list_widget.count()):
            item = self.list_widget.item(idx)
            if item.data(Qt.UserRole) == profile_id:
                self.list_widget.setCurrentItem(item)
                break
        QMessageBox.information(self, "Success", "Active connection profile updated.")

    def delete_selected_profile(self):
        selected_items = self.list_widget.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Selection Required", "Please select a profile to delete.")
            return
            
        profile_id = selected_items[0].data(Qt.UserRole)
        ret = QMessageBox.question(self, "Confirm Delete", "Are you sure you want to delete this profile?", 
                                    QMessageBox.Yes | QMessageBox.No)
        if ret == QMessageBox.No:
            return
            
        config = load_config()
        profiles = config.get("connection_profiles", [])
        
        updated_profiles = [p for p in profiles if p.get("id") != profile_id]
        config["connection_profiles"] = updated_profiles
        if config.get("active_profile_id") == profile_id:
            config["active_profile_id"] = None
            
        save_config(config)
        logger.info(f"Deleted profile ID: {profile_id}")
        self.main_window.update_profile_display()
        self.load_profiles_list()

    # General Settings and cleanup scheduler handlers
    def save_general_settings(self):
        config = load_config()
        b_settings = config.get("backup_settings", {})
        
        b_settings["backup_dir"] = self.txt_backup_dir.text().strip()
        b_settings["mysqldump_path"] = self.txt_dump_path.text().strip()
        b_settings["compress"] = self.chk_compress.isChecked()
        
        config["backup_settings"] = b_settings
        save_config(config)
        logger.info("Saved general database management configurations.")
        QMessageBox.information(self, "Success", "General backup configurations saved.")
        self.main_window.update_profile_display()

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

    def save_cleanup_schedule(self):
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
        logger.info("Saved automated deletion recurrence schedule configurations.")
        
        if enabled and headless:
            success, msg = register_windows_task("cleanup", freq, time_str, day_val)
            if success:
                QMessageBox.information(self, "Schedule Saved", "Retention cleanup scheduler task registered via Windows Task Scheduler.")
            else:
                QMessageBox.warning(self, "Schedule Warning", f"Could not register Windows Task: {msg}")
        else:
            unregister_windows_task("cleanup")
            QMessageBox.information(self, "Schedule Saved", "Automated deletion schedule configuration saved.")
            
        self.main_window.update_profile_display()

    # Appearance theme handlers
    def save_theme_setting(self):
        selected_theme = self.cb_theme.currentText()
        config = load_config()
        config["theme"] = selected_theme
        save_config(config)
        
        logger.info(f"Theme style updated and applied: {selected_theme}")
        self.main_window.apply_theme(selected_theme)
        QMessageBox.information(self, "Theme Applied", f"Application theme switched to {selected_theme}.")
