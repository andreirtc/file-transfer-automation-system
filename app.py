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

    from PySide6.QtGui import QIcon
    icon_path = PROJECT_ROOT / "assets" / "app_icon.png"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    from qfluentwidgets import setTheme, Theme, setThemeColor
    
    # Set Fluent UI Theme
    setTheme(Theme.LIGHT)
    setThemeColor('#0078D4') # Windows default blue

    # Create and show main window
    window = MainWindow(config, db)
    if icon_path.exists():
        window.setWindowIcon(QIcon(str(icon_path)))
    window.show()

    logger.info("Application window displayed")

    # Run the event loop
    exit_code = app.exec()

    logger.info("Application exiting with code %d", exit_code)
    sys.exit(exit_code)


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--compression-worker":
        from core.compression_worker import compress_files
        import json
        config_path = sys.argv[2]
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            compress_files(
                data["src_paths"],
                data["prefixes"],
                data["zip_path"],
                data.get("password"),
                data.get("compression_level", 4),
            )
            sys.exit(0)
        except Exception as e:
            sys.stderr.write(f"Compression worker error: {e}\n")
            sys.exit(1)
    else:
        main()
