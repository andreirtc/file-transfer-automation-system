"""
File Transfer Automation System — Application Entry Point

Initializes logging, configuration, database, and launches
the PySide6 desktop application.
"""

import sys
from pathlib import Path

# Ensure project root is on the path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtWidgets import QApplication

from gui.main_window import MainWindow
from services.configuration_service import ConfigurationService
from services.database_service import DatabaseService
from services.logging_service import setup_logging


def main():
    """Application entry point."""
    # Initialize logging first
    setup_logging()

    import logging
    logger = logging.getLogger("app")
    logger.info("=" * 60)
    logger.info("File Transfer Automation System starting")
    logger.info("=" * 60)

    # Load configuration
    config = ConfigurationService()
    logger.info("Configuration loaded")

    # Initialize database
    db = DatabaseService()
    logger.info("Database initialized")

    # Create Qt application
    app = QApplication(sys.argv)
    app.setApplicationName("File Transfer Automation System")
    app.setOrganizationName("FileTransferAutomation")

    # Load modern Fluent UI stylesheet
    style_path = PROJECT_ROOT / "gui" / "style.qss"
    if style_path.exists():
        app.setStyleSheet(style_path.read_text(encoding="utf-8"))
    else:
        logger.warning(f"Stylesheet not found at {style_path}")

    # Create and show main window
    window = MainWindow(config, db)
    window.show()

    logger.info("Application window displayed")

    # Run the event loop
    exit_code = app.exec()

    logger.info("Application exiting with code %d", exit_code)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
