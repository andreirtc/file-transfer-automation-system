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

    # Apply application-wide stylesheet
    app.setStyleSheet(
        """
        QMainWindow {
            background-color: #FAFAFA;
        }
        QGroupBox {
            font-weight: bold;
            border: 1px solid #E0E0E0;
            border-radius: 6px;
            margin-top: 8px;
            padding-top: 16px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 12px;
            padding: 0 6px;
        }
        QTableView {
            gridline-color: #E0E0E0;
            selection-background-color: #BBDEFB;
            alternate-background-color: #F5F5F5;
        }
        QTableView::item {
            padding: 4px 8px;
        }
        QHeaderView::section {
            background-color: #EEEEEE;
            padding: 6px 8px;
            border: none;
            border-bottom: 1px solid #BDBDBD;
            font-weight: bold;
        }
        QToolBar {
            spacing: 6px;
            padding: 4px;
        }
        QStatusBar {
            background-color: #EEEEEE;
        }
        """
    )

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
