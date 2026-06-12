import os
import logging
from datetime import datetime

# Directory for logs
LOGS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "logs")
os.makedirs(LOGS_DIR, exist_ok=True)
LOG_FILE_PATH = os.path.join(LOGS_DIR, "app.log")

# Maintain a list of subscribers (e.g. the GUI console)
_log_subscribers = []

class CallbackHandler(logging.Handler):
    """Custom logging handler that forwards formatted log records to registered subscribers."""
    def emit(self, record):
        try:
            msg = self.format(record)
            for subscriber in _log_subscribers:
                try:
                    subscriber(msg)
                except Exception:
                    pass
        except Exception:
            self.handleError(record)

# Set up logging configuration
logger = logging.getLogger("MySQLServerManager")
logger.setLevel(logging.DEBUG)

# File handler
file_handler = logging.FileHandler(LOG_FILE_PATH, encoding="utf-8")
file_handler.setLevel(logging.INFO)
file_formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] (%(filename)s:%(lineno)d): %(message)s")
file_handler.setFormatter(file_formatter)

# Console handler
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)
console_formatter = logging.Formatter("[%(asctime)s] [%(levelname)s]: %(message)s", datefmt="%H:%M:%S")
console_handler.setFormatter(console_formatter)

# GUI Callback handler
callback_handler = CallbackHandler()
callback_handler.setLevel(logging.DEBUG)
callback_formatter = logging.Formatter("[%(asctime)s] [%(levelname)s]: %(message)s", datefmt="%H:%M:%S")
callback_handler.setFormatter(callback_formatter)

# Add handlers
logger.addHandler(file_handler)
logger.addHandler(console_handler)
logger.addHandler(callback_handler)

def subscribe_log(callback):
    """Register a callback function that receives every new log message as a formatted string."""
    if callback not in _log_subscribers:
        _log_subscribers.append(callback)

def unsubscribe_log(callback):
    """Remove a registered log subscriber."""
    if callback in _log_subscribers:
        _log_subscribers.remove(callback)

def get_log_file_path():
    return LOG_FILE_PATH

def get_recent_logs(num_lines=100):
    """Retrieve the most recent log entries from the file."""
    if not os.path.exists(LOG_FILE_PATH):
        return ""
    try:
        with open(LOG_FILE_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()
            return "".join(lines[-num_lines:])
    except Exception as e:
        return f"Error reading log file: {str(e)}"
