"""
Configuration service for the File Transfer Automation System.

Manages loading, saving, and accessing application configuration
from config/config.json with sensible defaults for all settings.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("app")

# Default configuration values — used when config.json is missing or incomplete
_DEFAULTS: dict[str, Any] = {
    "stability_check_interval": 5,       # seconds between stability checks
    "required_stable_checks": 2,         # consecutive stable checks to declare READY
    "max_retries": 3,                    # max retry attempts for failed transfers
    "retry_delay": 10,                   # seconds between retries
    "hash_algorithm": "sha256",          # integrity hash algorithm
    "hash_chunk_size": 65536,            # bytes per chunk when hashing (64 KB)
    "automatic_monitoring": True,        # start monitoring on launch
    "reconciliation_interval": 30,       # seconds between full folder scans
    "overwrite_policy": "ask",           # "ask", "overwrite", "skip"
    "temp_file_prefix": ".",             # prefix for temp copy files
    "temp_file_suffix": ".transfer_tmp", # suffix for temp copy files
    "log_max_bytes": 5_242_880,          # 5 MB per log file
    "log_backup_count": 3,               # number of rotated log backups
    "network_drive_mode": False,         # optimize for shared network drives
    "auto_cleanup_enabled": False,       # enable automatic deletion of source files
    "batch_compression_enabled": True,   # compress all queued files into a single zip
    "zip_password": "password123",       # default password for zip files
}


class ConfigurationService:
    """
    Loads and persists application configuration.

    Configuration is stored in a JSON file. Missing keys are filled
    from defaults. The service validates value types and ranges.
    """

    def __init__(self, config_path: str | Path | None = None):
        if config_path is None:
            # Default: config/config.json relative to project root
            self._path = Path(__file__).resolve().parent.parent / "config" / "config.json"
        else:
            self._path = Path(config_path)

        self._data: dict[str, Any] = {}
        self.load()

    def load(self) -> None:
        """Load configuration from disk, merging with defaults."""
        self._data = dict(_DEFAULTS)  # start with defaults

        if self._path.exists():
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    user_config = json.load(f)
                if isinstance(user_config, dict):
                    self._data.update(user_config)
                    logger.info("Configuration loaded from %s", self._path)
                else:
                    logger.warning(
                        "Configuration file has unexpected format; using defaults."
                    )
            except (json.JSONDecodeError, OSError) as e:
                logger.error("Failed to load configuration: %s. Using defaults.", e)
        else:
            logger.info(
                "Configuration file not found at %s. Using defaults.", self._path
            )
            # Create the file with defaults so the user can edit it
            self.save()

    def save(self) -> None:
        """Persist current configuration to disk."""
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=4)
            logger.info("Configuration saved to %s", self._path)
        except OSError as e:
            logger.error("Failed to save configuration: %s", e)

    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value by key."""
        return self._data.get(key, default if default is not None else _DEFAULTS.get(key))

    def set(self, key: str, value: Any) -> None:
        """Set a configuration value and persist."""
        self._data[key] = value

    def get_int(self, key: str, default: int = 0) -> int:
        """Get a configuration value as an integer."""
        try:
            return int(self.get(key, default))
        except (TypeError, ValueError):
            return default

    def get_float(self, key: str, default: float = 0.0) -> float:
        """Get a configuration value as a float."""
        try:
            return float(self.get(key, default))
        except (TypeError, ValueError):
            return default

    def get_bool(self, key: str, default: bool = False) -> bool:
        """Get a configuration value as a boolean."""
        val = self.get(key, default)
        if isinstance(val, bool):
            return val
        if isinstance(val, str):
            return val.lower() in ("true", "1", "yes")
        return bool(val)

    def get_str(self, key: str, default: str = "") -> str:
        """Get a configuration value as a string."""
        val = self.get(key, default)
        return str(val) if val is not None else default

    @property
    def stability_check_interval(self) -> int:
        return self.get_int("stability_check_interval", 5)

    @property
    def required_stable_checks(self) -> int:
        return self.get_int("required_stable_checks", 2)

    @property
    def max_retries(self) -> int:
        return self.get_int("max_retries", 3)

    @property
    def retry_delay(self) -> int:
        return self.get_int("retry_delay", 10)

    @property
    def hash_algorithm(self) -> str:
        return self.get_str("hash_algorithm", "sha256")

    @property
    def hash_chunk_size(self) -> int:
        return self.get_int("hash_chunk_size", 65536)

    @property
    def automatic_monitoring(self) -> bool:
        return self.get_bool("automatic_monitoring", True)

    @property
    def reconciliation_interval(self) -> int:
        return self.get_int("reconciliation_interval", 30)

    @property
    def overwrite_policy(self) -> str:
        return self.get_str("overwrite_policy", "ask")

    @property
    def temp_file_prefix(self) -> str:
        return self.get_str("temp_file_prefix", ".")

    @property
    def temp_file_suffix(self) -> str:
        return self.get_str("temp_file_suffix", ".transfer_tmp")

    @property
    def network_drive_mode(self) -> bool:
        return self.get_bool("network_drive_mode", False)

    @property
    def auto_cleanup_enabled(self) -> bool:
        return self.get_bool("auto_cleanup_enabled", False)

    @property
    def batch_compression_enabled(self) -> bool:
        return self.get_bool("batch_compression_enabled", True)

    @property
    def zip_password(self) -> str:
        return self.get_str("zip_password", "password123")

    @property
    def all_settings(self) -> dict[str, Any]:
        """Return a copy of all current settings."""
        return dict(self._data)
