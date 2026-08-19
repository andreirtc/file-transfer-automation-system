"""
Logging service for the File Transfer Automation System.

Configures structured logging with three log files:
- application.log: General application events
- transfer.log: File transfer operations
- error.log: Errors and warnings only

Uses rotating file handlers to prevent unbounded log growth.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import sys


def get_app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def setup_logging(
    log_dir: str | Path | None = None,
    max_bytes: int = 5_242_880,
    backup_count: int = 3,
    console_level: int = logging.INFO,
) -> None:
    """
    Initialize the logging system with file and console handlers.

    Args:
        log_dir: Directory for log files. Defaults to logs/ in the project root.
        max_bytes: Maximum bytes per log file before rotation.
        backup_count: Number of rotated backups to keep.
        console_level: Logging level for console output.
    """
    if log_dir is None:
        log_dir = get_app_dir() / "logs"
    else:
        log_dir = Path(log_dir)

    log_dir.mkdir(parents=True, exist_ok=True)

    # Log format
    detailed_format = logging.Formatter(
        "%(asctime)s [%(levelname)-8s] %(name)-12s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    brief_format = logging.Formatter(
        "%(asctime)s [%(levelname)-8s] %(message)s",
        datefmt="%H:%M:%S",
    )

    # ---- Application logger ----
    app_logger = logging.getLogger("app")
    app_logger.setLevel(logging.DEBUG)
    _add_rotating_handler(
        app_logger,
        log_dir / "application.log",
        detailed_format,
        logging.DEBUG,
        max_bytes,
        backup_count,
    )

    # ---- Transfer logger ----
    transfer_logger = logging.getLogger("transfer")
    transfer_logger.setLevel(logging.DEBUG)
    _add_rotating_handler(
        transfer_logger,
        log_dir / "transfer.log",
        detailed_format,
        logging.DEBUG,
        max_bytes,
        backup_count,
    )

    # ---- Error logger (errors + warnings only) ----
    error_logger = logging.getLogger("error")
    error_logger.setLevel(logging.WARNING)
    _add_rotating_handler(
        error_logger,
        log_dir / "error.log",
        detailed_format,
        logging.WARNING,
        max_bytes,
        backup_count,
    )

    # ---- Console handler on root logger ----
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # Remove any existing handlers on the root logger to avoid duplicates
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(console_level)
    console_handler.setFormatter(brief_format)
    root_logger.addHandler(console_handler)


def _add_rotating_handler(
    logger: logging.Logger,
    file_path: Path,
    formatter: logging.Formatter,
    level: int,
    max_bytes: int,
    backup_count: int,
) -> None:
    """Add a rotating file handler to a logger, avoiding duplicates."""
    # Check if an identical handler already exists
    for handler in logger.handlers:
        if (
            isinstance(handler, RotatingFileHandler)
            and Path(handler.baseFilename).resolve() == file_path.resolve()
        ):
            return  # Already attached

    file_handler = RotatingFileHandler(
        str(file_path),
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)


def get_log_file_paths(log_dir: str | Path | None = None) -> dict[str, Path]:
    """Return paths to all log files for the log viewer."""
    if log_dir is None:
        log_dir = get_app_dir() / "logs"
    else:
        log_dir = Path(log_dir)

    return {
        "Application Log": log_dir / "application.log",
        "Transfer Log": log_dir / "transfer.log",
        "Error Log": log_dir / "error.log",
    }
