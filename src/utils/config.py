import os
import json
import base64
from cryptography.fernet import Fernet
from src.utils.logger import logger

# Configuration files paths
WORKSPACE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_PATH = os.path.join(WORKSPACE_DIR, "config.json")

# Secure key storage in User AppData
APPDATA_DIR = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or WORKSPACE_DIR
SECURE_DIR = os.path.join(APPDATA_DIR, "MySQLServerManager")
os.makedirs(SECURE_DIR, exist_ok=True)
KEY_PATH = os.path.join(SECURE_DIR, "secret.key")

_fernet = None

def _get_fernet():
    global _fernet
    if _fernet is not None:
        return _fernet
    
    try:
        if os.path.exists(KEY_PATH):
            with open(KEY_PATH, "rb") as key_file:
                key = key_file.read()
        else:
            key = Fernet.generate_key()
            with open(KEY_PATH, "wb") as key_file:
                key_file.write(key)
        _fernet = Fernet(key)
    except Exception as e:
        logger.error(f"Failed to load/create encryption key: {str(e)}. Falling back to transient key.")
        # Transient key (will not persist across app restarts if disk write failed)
        transient_key = Fernet.generate_key()
        _fernet = Fernet(transient_key)
    
    return _fernet

def encrypt_password(password: str) -> str:
    """Encrypt a password string."""
    if not password:
        return ""
    try:
        f = _get_fernet()
        encrypted = f.encrypt(password.encode("utf-8"))
        return encrypted.decode("utf-8")
    except Exception as e:
        logger.error(f"Password encryption failed: {str(e)}")
        return ""

def decrypt_password(encrypted_password: str) -> str:
    """Decrypt an encrypted password string."""
    if not encrypted_password:
        return ""
    try:
        f = _get_fernet()
        decrypted = f.decrypt(encrypted_password.encode("utf-8"))
        return decrypted.decode("utf-8")
    except Exception as e:
        logger.error(f"Password decryption failed: {str(e)}")
        return ""

# Default configuration template
DEFAULT_CONFIG = {
    "connection_profiles": [],
    "active_profile_id": None,
    "backup_settings": {
        "mysqldump_path": "",
        "backup_dir": os.path.join(WORKSPACE_DIR, "backups"),
        "compress": True,
        "schedule_enabled": False,
        "schedule_type": "daily",  # daily, weekly, monthly
        "schedule_time": "02:00",  # HH:MM
        "schedule_day": 1,         # 1-7 for weekly (Mon=1), 1-31 for monthly
        "run_headless": False      # Use Windows Task Scheduler
    },
    "retention_rules": [],         # List of dicts: {db: str, table: str, column: str, months: int, enabled: bool}
    "retention_schedule": {
        "schedule_enabled": False,
        "schedule_type": "daily",
        "schedule_time": "03:00",
        "schedule_day": 1,
        "run_headless": False
    }
}

def load_config() -> dict:
    """Load configuration from the config.json file."""
    if not os.path.exists(CONFIG_PATH):
        logger.info("Config file not found. Creating default configuration.")
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG
    
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = json.load(f)
            # Merge defaults in case of missing keys
            config = _merge_dicts(DEFAULT_CONFIG, config)
            return config
    except Exception as e:
        logger.error(f"Failed to load config file: {str(e)}. Using defaults.")
        return DEFAULT_CONFIG

def save_config(config: dict):
    """Save configuration to the config.json file."""
    try:
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)
    except Exception as e:
        logger.error(f"Failed to save config file: {str(e)}")

def _merge_dicts(default: dict, custom: dict) -> dict:
    """Recursively merge custom dict into default dict."""
    merged = default.copy()
    for k, v in custom.items():
        if k in merged and isinstance(merged[k], dict) and isinstance(v, dict):
            merged[k] = _merge_dicts(merged[k], v)
        else:
            merged[k] = v
    return merged

def get_active_profile(config: dict = None) -> dict:
    """Get the currently active connection profile."""
    if config is None:
        config = load_config()
    
    profile_id = config.get("active_profile_id")
    if not profile_id:
        return None
        
    for p in config.get("connection_profiles", []):
        if p.get("id") == profile_id:
            # Return a copy and decrypt password
            profile_copy = p.copy()
            profile_copy["password"] = decrypt_password(p.get("password", ""))
            return profile_copy
            
    return None
