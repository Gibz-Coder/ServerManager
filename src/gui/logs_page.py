from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, QPushButton
from PySide6.QtCore import Qt, QMetaObject, Q_ARG, Slot
from src.utils.logger import get_recent_logs, get_log_file_path

class LogsPage(QWidget):
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
        vbox_header = QVBoxLayout()
        vbox_header.setSpacing(5)
        
        title = QLabel("System Logs")
        title.setObjectName("PageTitle")
        vbox_header.addWidget(title)
        
        subtitle = QLabel("Real-time logging console of backup schedules, cleanup actions, and database connections.")
        subtitle.setObjectName("PageSubtitle")
        vbox_header.addWidget(subtitle)
        header_layout.addLayout(vbox_header)
        
        header_layout.addStretch()
        
        btn_clear = QPushButton("Clear Console")
        btn_clear.clicked.connect(self.clear_console)
        header_layout.addWidget(btn_clear)
        
        btn_refresh = QPushButton("Reload Logs")
        btn_refresh.setObjectName("PrimaryButton")
        btn_refresh.clicked.connect(self.load_historical_logs)
        header_layout.addWidget(btn_refresh)
        
        layout.addLayout(header_layout)
        
        # Console output
        self.log_console = QTextEdit()
        self.log_console.setObjectName("LogConsole")
        self.log_console.setReadOnly(True)
        layout.addWidget(self.log_console)

    def load_historical_logs(self):
        """Loads recent logs from the physical app.log file on disk."""
        logs = get_recent_logs(200)
        self.log_console.setPlainText(logs)
        self.scroll_to_bottom()

    @Slot(str)
    def append_log(self, message: str):
        """Thread-safe method to append a new log entry to the console."""
        # Use invokeMethod to guarantee this UI operation executes on the main GUI thread
        QMetaObject.invokeMethod(self.log_console, "append", Qt.QueuedConnection, Q_ARG(str, message))
        # Keep scroll to bottom
        QMetaObject.invokeMethod(self, "scroll_to_bottom", Qt.QueuedConnection)

    @Slot()
    def scroll_to_bottom(self):
        scrollbar = self.log_console.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def clear_console(self):
        self.log_console.clear()
