from PySide6.QtWidgets import (QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, 
                               QFrame, QLabel, QPushButton, QStackedWidget, QButtonGroup)
from PySide6.QtCore import Qt, Slot

from src.gui.theme import DARK_THEME_STYLE
from src.gui.dashboard_page import DashboardPage
from src.gui.connection_page import ConnectionPage
from src.gui.backup_page import BackupPage
from src.gui.cleanup_page import CleanupPage
from src.gui.logs_page import LogsPage
from src.scheduler import InAppSchedulerThread
from src.utils.logger import subscribe_log, unsubscribe_log, logger
from src.utils.config import load_config, get_active_profile

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MySQL Server Manager")
        self.resize(1100, 700)
        self.setStyleSheet(DARK_THEME_STYLE)
        
        # Load active connection config
        self.config = load_config()
        self.active_profile = get_active_profile(self.config)
        
        # Init local scheduler thread
        self.scheduler_thread = InAppSchedulerThread()
        self.scheduler_thread.start()
        
        # Create Main UI structure
        self.init_ui()
        
        # Log handler connection
        subscribe_log(self.on_new_log)
        logger.info("Application interface loaded. Ready.")

    def init_ui(self):
        # Central widget
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        
        # Main layout
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # 1. Sidebar Frame
        self.sidebar = QFrame()
        self.sidebar.setObjectName("SidebarFrame")
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)
        
        # Sidebar Title
        title_label = QLabel("ServerManager")
        title_label.setObjectName("SidebarTitle")
        title_label.setAlignment(Qt.AlignCenter)
        sidebar_layout.addWidget(title_label)
        
        # Sidebar buttons container
        buttons_layout = QVBoxLayout()
        buttons_layout.setContentsMargins(0, 15, 0, 15)
        buttons_layout.setSpacing(2)
        
        self.btn_group = QButtonGroup(self)
        self.btn_group.setExclusive(True)
        
        # Define sidebar pages
        self.sidebar_buttons = []
        pages_def = [
            ("Dashboard", 0),
            ("Connections", 1),
            ("Backups", 2),
            ("Retention Rules", 3),
            ("System Logs", 4)
        ]
        
        for name, index in pages_def:
            btn = QPushButton(name)
            btn.setObjectName("SidebarButton")
            btn.setCheckable(True)
            self.btn_group.addButton(btn, index)
            buttons_layout.addWidget(btn)
            self.sidebar_buttons.append(btn)
            
        # Select Dashboard by default
        self.sidebar_buttons[0].setChecked(True)
        sidebar_layout.addLayout(buttons_layout)
        
        # Active profile indicator in sidebar footer
        sidebar_layout.addStretch()
        
        self.profile_footer = QFrame()
        self.profile_footer.setStyleSheet("border-top: 1px solid #27272a; padding: 15px;")
        footer_layout = QVBoxLayout(self.profile_footer)
        footer_layout.setContentsMargins(10, 10, 10, 10)
        
        footer_label = QLabel("ACTIVE PROFILE:")
        footer_label.setStyleSheet("font-size: 10px; color: #71717a; font-weight: bold;")
        footer_layout.addWidget(footer_label)
        
        self.profile_name_label = QLabel("None")
        self.profile_name_label.setStyleSheet("font-weight: bold; color: #10b981; font-size: 12px;")
        footer_layout.addWidget(self.profile_name_label)
        
        sidebar_layout.addWidget(self.profile_footer)
        
        # Add sidebar to main layout
        main_layout.addWidget(self.sidebar)
        
        # 2. Main Content Stack
        self.content_stack = QStackedWidget()
        
        # Instantiate pages
        self.dashboard_page = DashboardPage(self)
        self.connection_page = ConnectionPage(self)
        self.backup_page = BackupPage(self)
        self.cleanup_page = CleanupPage(self)
        self.logs_page = LogsPage(self)
        
        # Add to stack
        self.content_stack.addWidget(self.dashboard_page)   # index 0
        self.content_stack.addWidget(self.connection_page)  # index 1
        self.content_stack.addWidget(self.backup_page)      # index 2
        self.content_stack.addWidget(self.cleanup_page)     # index 3
        self.content_stack.addWidget(self.logs_page)        # index 4
        
        main_layout.addWidget(self.content_stack)
        
        # Connect sidebar buttons to stacked widget switching
        self.btn_group.idClicked.connect(self.content_stack.setCurrentIndex)
        
        # Update connection profile display
        self.update_profile_display()

    def update_profile_display(self):
        """Refresh active connection profile information across all pages."""
        self.config = load_config()
        self.active_profile = get_active_profile(self.config)
        
        if self.active_profile:
            name = f"{self.active_profile.get('user')}@{self.active_profile.get('host')}"
            db = self.active_profile.get('database')
            if db:
                name += f"/{db}"
            self.profile_name_label.setText(name)
            self.profile_name_label.setStyleSheet("font-weight: bold; color: #10b981; font-size: 12px;")
        else:
            self.profile_name_label.setText("No Active Server")
            self.profile_name_label.setStyleSheet("font-weight: bold; color: #ef4444; font-size: 12px;")
            
        # Notify subpages
        self.dashboard_page.refresh_page()
        self.backup_page.refresh_page()
        self.cleanup_page.refresh_page()

    @Slot(str)
    def on_new_log(self, message: str):
        """Append log message to the log page console."""
        # Use QMetaObject.invokeMethod if running from a non-gui background thread to keep it safe
        # In this case, logs page handles appending safely
        self.logs_page.append_log(message)

    def closeEvent(self, event):
        """Clean up threads and unsubscribes on close."""
        logger.info("Application closing. Terminating background threads...")
        unsubscribe_log(self.on_new_log)
        self.scheduler_thread.stop()
        self.scheduler_thread.join(timeout=2)
        event.accept()
