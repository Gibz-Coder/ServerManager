from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFrame, 
                               QLabel, QLineEdit, QPushButton, QListWidget, 
                               QListWidgetItem, QMessageBox, QFormLayout)
from PySide6.QtCore import Qt
from src.connection import MySQLConnectionManager
from src.utils.config import load_config, save_config, encrypt_password, decrypt_password
from src.utils.logger import logger
import uuid

class ConnectionPage(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.profiles = []
        self.selected_profile_id = None
        self.init_ui()
        self.load_profiles_list()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(25, 25, 25, 25)
        layout.setSpacing(20)
        
        # Header
        header_layout = QVBoxLayout()
        header_layout.setSpacing(5)
        
        title = QLabel("Connection Profiles")
        title.setObjectName("PageTitle")
        header_layout.addWidget(title)
        
        subtitle = QLabel("Create, test, and manage MySQL server connection credentials securely.")
        subtitle.setObjectName("PageSubtitle")
        header_layout.addWidget(subtitle)
        
        layout.addLayout(header_layout)
        
        # Split layout: Form (left) vs Profiles List (right)
        split_layout = QHBoxLayout()
        split_layout.setSpacing(20)
        
        # Left Panel: Credentials Form
        form_frame = QFrame()
        form_frame.setObjectName("CardFrame")
        form_layout = QFormLayout(form_frame)
        form_layout.setSpacing(12)
        form_layout.setLabelAlignment(Qt.AlignRight)
        
        form_title = QLabel("Server Configuration")
        form_title.setStyleSheet("font-size: 15px; font-weight: bold; color: #f4f4f5; margin-bottom: 5px;")
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
        
        # Form Actions Buttons
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
        
        # Connection test result feedback box
        self.lbl_test_result = QLabel("")
        self.lbl_test_result.setWordWrap(True)
        self.lbl_test_result.setStyleSheet("font-size: 11px; margin-top: 5px;")
        form_layout.addRow("", self.lbl_test_result)
        
        split_layout.addWidget(form_frame, 3)
        
        # Right Panel: Profiles List
        list_frame = QFrame()
        list_frame.setObjectName("CardFrame")
        list_layout = QVBoxLayout(list_frame)
        list_layout.setSpacing(10)
        
        list_title = QLabel("Saved Profiles")
        list_title.setStyleSheet("font-size: 15px; font-weight: bold; color: #f4f4f5;")
        list_layout.addWidget(list_title)
        
        self.list_widget = QListWidget()
        self.list_widget.itemSelectionChanged.connect(self.on_profile_selected)
        list_layout.addWidget(self.list_widget)
        
        # Actions for profiles
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
        
        split_layout.addWidget(list_frame, 2)
        
        layout.addLayout(split_layout)

    def load_profiles_list(self):
        """Read config profiles and populate list widget."""
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
        """Load selected profile details into the form inputs."""
        selected_items = self.list_widget.selectedItems()
        if not selected_items:
            return
            
        profile_id = selected_items[0].data(Qt.UserRole)
        self.selected_profile_id = profile_id
        
        # Find profile
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
            
            # Decrypt password for form
            decrypted = decrypt_password(target_profile.get("password", ""))
            self.txt_password.setText(decrypted)
            self.txt_db.setText(target_profile.get("database", ""))
            
            self.lbl_test_result.setText("")

    def reset_form(self):
        """Clear form input fields for writing a new profile."""
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
        """Returns input credentials as profile dictionary format."""
        return {
            "host": self.txt_host.text().strip(),
            "port": self.txt_port.text().strip(),
            "user": self.txt_user.text().strip(),
            "password": self.txt_password.text(),
            "database": self.txt_db.text().strip()
        }

    def test_current_inputs(self):
        """Try connecting using values typed directly inside the fields."""
        self.lbl_test_result.setText("Testing connection...")
        self.lbl_test_result.setStyleSheet("color: #a1a1aa;")
        self.repaint()
        
        profile = self.get_form_profile_dict()
        if not profile["host"] or not profile["user"]:
            self.lbl_test_result.setText("Failed: Host and User fields cannot be empty.")
            self.lbl_test_result.setStyleSheet("color: #ef4444;")
            return
            
        # Run test
        success, msg = MySQLConnectionManager.test_connection(profile)
        if success:
            self.lbl_test_result.setText("✓ Connection successful!")
            self.lbl_test_result.setStyleSheet("color: #10b981; font-weight: bold;")
        else:
            self.lbl_test_result.setText(f"✗ Connection failed: {msg}")
            self.lbl_test_result.setStyleSheet("color: #ef4444;")

    def save_current_profile(self):
        """Save form credentials into config.json securely."""
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
        
        # Password encryption
        encrypted_pass = encrypt_password(profile_data["password"])
        
        if self.selected_profile_id:
            # Edit existing profile
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
            # Create a new profile
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
        
        # Reload List UI
        self.load_profiles_list()
        
        # Keep selected
        for idx in range(self.list_widget.count()):
            item = self.list_widget.item(idx)
            if item.data(Qt.UserRole) == self.selected_profile_id:
                self.list_widget.setCurrentItem(item)
                break
                
        QMessageBox.information(self, "Success", "Profile saved successfully!")

    def set_profile_active(self):
        """Activate selected profile as core database connection."""
        selected_items = self.list_widget.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Selection Required", "Please select a profile from the list.")
            return
            
        profile_id = selected_items[0].data(Qt.UserRole)
        config = load_config()
        config["active_profile_id"] = profile_id
        save_config(config)
        
        logger.info(f"Switched active connection profile ID to: {profile_id}")
        
        # Update app connections status
        self.main_window.update_profile_display()
        self.load_profiles_list()
        
        # Select activated item
        for idx in range(self.list_widget.count()):
            item = self.list_widget.item(idx)
            if item.data(Qt.UserRole) == profile_id:
                self.list_widget.setCurrentItem(item)
                break
                
        QMessageBox.information(self, "Success", "Active connection profile updated.")

    def delete_selected_profile(self):
        """Remove profile from config file."""
        selected_items = self.list_widget.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Selection Required", "Please select a profile to delete.")
            return
            
        profile_id = selected_items[0].data(Qt.UserRole)
        
        # Confirmation
        ret = QMessageBox.question(self, "Confirm Delete", "Are you sure you want to delete this profile?", 
                                    QMessageBox.Yes | QMessageBox.No)
        if ret == QMessageBox.No:
            return
            
        config = load_config()
        profiles = config.get("connection_profiles", [])
        
        # Filter profile
        updated_profiles = [p for p in profiles if p.get("id") != profile_id]
        config["connection_profiles"] = updated_profiles
        
        # Reset active profile if it was deleted
        if config.get("active_profile_id") == profile_id:
            config["active_profile_id"] = None
            
        save_config(config)
        logger.info(f"Deleted profile ID: {profile_id}")
        
        self.main_window.update_profile_display()
        self.load_profiles_list()
