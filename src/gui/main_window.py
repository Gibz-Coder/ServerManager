from PySide6.QtWidgets import (QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, 
                               QFrame, QLabel, QPushButton, QStackedWidget, QButtonGroup)
from PySide6.QtCore import Qt, Slot, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QPen, QBrush

from src.gui.theme import DARK_THEME_STYLE
from src.gui.dashboard_page import DashboardPage
from src.gui.jobs_page import JobsPage
from src.gui.settings_page import SettingsPage
from src.scheduler import InAppSchedulerThread
from src.utils.logger import subscribe_log, unsubscribe_log, logger
from src.utils.config import load_config, get_active_profile

def create_app_icon() -> QIcon:
    """Generate a clean, high-resolution database badge icon dynamically matching mockup 2."""
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.transparent)
    
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    
    # Outer rounded blue square
    painter.setPen(Qt.NoPen)
    # Bright blue color matching the CustomTkinter logo in the screenshot
    painter.setBrush(QColor("#007acc"))
    painter.drawRoundedRect(4, 4, 56, 56, 16, 16)
    
    # Carve a hollow hole in the center to make it hollow/transparent
    painter.setCompositionMode(QPainter.CompositionMode_Clear)
    painter.setBrush(Qt.black)
    painter.drawRoundedRect(16, 16, 32, 32, 8, 8)
    
    painter.end()
    return QIcon(pixmap)

def get_app_logo_pixmap() -> QPixmap:
    """Generate a clean, high-resolution 24x24 version of the hollow blue rounded square app logo."""
    pixmap = QPixmap(24, 24)
    pixmap.fill(Qt.transparent)
    
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    
    # Outer rounded blue square
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor("#007acc"))
    painter.drawRoundedRect(1, 1, 22, 22, 6, 6)
    
    # Hollow center (carve transparent hole)
    painter.setCompositionMode(QPainter.CompositionMode_Clear)
    painter.setBrush(Qt.black)
    painter.drawRoundedRect(6, 6, 12, 12, 3, 3)
    
    painter.end()
    return pixmap

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DB Orchestrator")
        self.resize(1100, 620)
        self.setStyleSheet(DARK_THEME_STYLE)
        self.setWindowIcon(create_app_icon())
        
        # Enable native Windows Immersive Dark Mode for the title bar
        import sys
        if sys.platform == "win32":
            try:
                import ctypes
                hwnd = self.winId()
                hwnd_int = int(hwnd)
                dwmapi = ctypes.windll.dwmapi
                use_dark_mode = ctypes.c_int(1)
                # DWMWA_USE_IMMERSIVE_DARK_MODE = 20
                dwmapi.DwmSetWindowAttribute(
                    hwnd_int,
                    20,
                    ctypes.byref(use_dark_mode),
                    ctypes.sizeof(use_dark_mode)
                )
            except Exception as e:
                logger.debug(f"Failed to apply Windows dark title bar: {e}")
        
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
        
        # Sidebar Title Block (Horizontal Row Layout)
        title_widget = QWidget()
        self.title_layout = QHBoxLayout(title_widget)
        self.title_layout.setContentsMargins(10, 15, 10, 15)
        self.title_layout.setSpacing(8)
        self.title_layout.setAlignment(Qt.AlignCenter)
        
        # Brand Logo
        self.lbl_title_logo = QLabel()
        self.lbl_title_logo.setPixmap(get_app_logo_pixmap())
        self.lbl_title_logo.setStyleSheet("border: none;")
        self.lbl_title_logo.setAlignment(Qt.AlignCenter)
        self.lbl_title_logo.setCursor(Qt.PointingHandCursor)
        self.lbl_title_logo.mousePressEvent = lambda event: self.toggle_sidebar()
        self.title_layout.addWidget(self.lbl_title_logo)
        
        # Title Label
        self.title_label = QLabel("DB Orchestrator")
        self.title_label.setObjectName("SidebarTitleLabel")
        self.title_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.title_label.setCursor(Qt.PointingHandCursor)
        self.title_label.mousePressEvent = lambda event: self.toggle_sidebar()
        self.title_layout.addWidget(self.title_label)
        
        sidebar_layout.addWidget(title_widget)
        
        # Sidebar separator
        sep = QFrame()
        sep.setObjectName("PageSeparator")
        sep.setFrameShape(QFrame.HLine)
        sidebar_layout.addWidget(sep)
        
        # Sidebar buttons container
        buttons_layout = QVBoxLayout()
        buttons_layout.setContentsMargins(0, 15, 0, 15)
        buttons_layout.setSpacing(2)
        
        self.btn_group = QButtonGroup(self)
        self.btn_group.setExclusive(True)
        
        # Define sidebar pages (Match simplified layout with icons)
        self.sidebar_buttons = []
        pages_def = [
            ("📊  Dashboard", 0),
            ("⚡  Automation", 1),
            ("⚙️  Settings", 2)
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
        
        # Sidebar Version Control Footer
        sidebar_layout.addStretch()
        
        self.profile_footer = QFrame()
        self.profile_footer.setObjectName("ProfileFooter")
        footer_layout = QVBoxLayout(self.profile_footer)
        footer_layout.setContentsMargins(10, 12, 10, 12)
        
        self.lbl_version = QLabel("v1.0.0")
        self.lbl_version.setAlignment(Qt.AlignCenter)
        self.lbl_version.setStyleSheet("font-size: 11px; font-weight: bold; color: #71717a;")
        footer_layout.addWidget(self.lbl_version)
        
        sidebar_layout.addWidget(self.profile_footer)
        
        # Add sidebar to main layout
        main_layout.addWidget(self.sidebar)
        
        # 2. Main Content Stack
        self.content_stack = QStackedWidget()
        
        # Instantiate pages
        self.dashboard_page = DashboardPage(self)
        self.jobs_page = JobsPage(self)
        self.settings_page = SettingsPage(self)
        
        # Add to stack
        self.content_stack.addWidget(self.dashboard_page)   # index 0
        self.content_stack.addWidget(self.jobs_page)        # index 1
        self.content_stack.addWidget(self.settings_page)    # index 2
        
        main_layout.addWidget(self.content_stack)
        
        # Connect sidebar buttons to stacked widget switching
        self.btn_group.idClicked.connect(self.content_stack.setCurrentIndex)
        
        # Log handler connection
        subscribe_log(self.on_new_log)
        
        # Apply persisted theme on startup
        saved_theme = self.config.get("theme", "Dark Mode")
        self.apply_theme(saved_theme)
        
        # Update active server profile display
        self.update_profile_display()
        
        logger.info("Application interface loaded. Ready.")

    def apply_theme(self, theme_name: str):
        """Reload application-wide style sheets dynamically."""
        from src.gui.theme import DARK_THEME_STYLE, LIGHT_THEME_STYLE, MIDNIGHT_THEME_STYLE
        theme_map = {
            "Dark Mode": DARK_THEME_STYLE,
            "Light Mode": LIGHT_THEME_STYLE,
            "Midnight Blue": MIDNIGHT_THEME_STYLE
        }
        stylesheet = theme_map.get(theme_name, DARK_THEME_STYLE)
        self.setStyleSheet(stylesheet)

    def update_profile_display(self):
        """Refresh active connection profile information across all pages."""
        self.config = load_config()
        self.active_profile = get_active_profile(self.config)
        
        # Notify subpages
        self.dashboard_page.refresh_page()
        self.jobs_page.refresh_page()
        self.settings_page.refresh_page()

    def toggle_sidebar(self):
        """Toggle sidebar layout width dynamically between 220px and 60px with transition animation."""
        width = self.sidebar.width()
        collapsed = (width > 100)
        new_width = 60 if collapsed else 220
        
        # Animate minimum width property
        self.sidebar_anim = QPropertyAnimation(self.sidebar, b"minimumWidth")
        self.sidebar_anim.setDuration(200)
        self.sidebar_anim.setStartValue(width)
        self.sidebar_anim.setEndValue(new_width)
        self.sidebar_anim.setEasingCurve(QEasingCurve.InOutQuad)
        
        # Animate maximum width property
        self.sidebar_anim_max = QPropertyAnimation(self.sidebar, b"maximumWidth")
        self.sidebar_anim_max.setDuration(200)
        self.sidebar_anim_max.setStartValue(width)
        self.sidebar_anim_max.setEndValue(new_width)
        self.sidebar_anim_max.setEasingCurve(QEasingCurve.InOutQuad)
        
        if collapsed:
            # If collapsing, hide text labels immediately to prevent text clipping
            self.update_sidebar_ui(True)
        else:
            # If expanding, restore text labels after the animation finishes
            self.sidebar_anim.finished.connect(lambda: self.update_sidebar_ui(False))
            
        self.sidebar_anim.start()
        self.sidebar_anim_max.start()

    def update_sidebar_ui(self, collapsed: bool):
        """Update navigation labels, titles, and layouts matching sidebar state."""
        if collapsed:
            self.title_label.hide()
            
            # Hide sidebar label text, leaving only Unicode icons
            self.sidebar_buttons[0].setText("📊")
            self.sidebar_buttons[1].setText("⚡")
            self.sidebar_buttons[2].setText("⚙️")
            
            for btn in self.sidebar_buttons:
                btn.setStyleSheet("text-align: center; font-size: 16px; margin: 4px 5px; padding: 12px 0px;")
                
            self.lbl_version.hide()
            

        else:
            self.title_label.show()
            
            # Restore full labels text
            self.sidebar_buttons[0].setText("📊  Dashboard")
            self.sidebar_buttons[1].setText("⚡  Automation")
            self.sidebar_buttons[2].setText("⚙️  Settings")
            
            for btn in self.sidebar_buttons:
                btn.setStyleSheet("")  # resets styling back to dark theme sheet default
                
            self.lbl_version.show()
            self.update_profile_display()
            


    @Slot(str)
    def on_new_log(self, message: str):
        """Append log message to the log consoles on the active pages."""
        self.dashboard_page.append_log(message)
        self.jobs_page.append_log(message)

    def closeEvent(self, event):
        """Clean up threads and unsubscribes on close."""
        logger.info("Application closing. Terminating background threads...")
        unsubscribe_log(self.on_new_log)
        self.scheduler_thread.stop()
        self.scheduler_thread.join(timeout=2)
        event.accept()
