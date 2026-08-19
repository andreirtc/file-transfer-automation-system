"""
Filesystem monitor for the File Transfer Automation System.

Watches a source directory for new and modified files using the
watchdog library (native OS events). Also provides periodic
reconciliation scanning as a fallback for missed events.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Callable, Optional

from watchdog.events import FileCreatedEvent, FileModifiedEvent, FileSystemEventHandler
from watchdog.observers import Observer

logger = logging.getLogger("app")


class _FileEventHandler(FileSystemEventHandler):
    """
    Watchdog event handler that filters and debounces filesystem events.
    """

    def __init__(
        self,
        on_file_detected: Callable[[str], None],
        temp_suffix: str = ".transfer_tmp",
        debounce_seconds: float = 1.0,
    ):
        super().__init__()
        self._on_file_detected = on_file_detected
        self._temp_suffix = temp_suffix
        self._debounce_seconds = debounce_seconds
        self._last_event: dict[str, float] = {}
        self._lock = threading.Lock()

    def on_created(self, event: FileCreatedEvent) -> None:
        if not event.is_directory:
            self._handle_event(event.src_path)

    def on_modified(self, event: FileModifiedEvent) -> None:
        if not event.is_directory:
            self._handle_event(event.src_path)

    def _handle_event(self, src_path: str) -> None:
        """Filter and debounce a filesystem event."""
        path = Path(src_path)

        # Ignore temp files created by our own transfer engine
        if path.name.endswith(self._temp_suffix):
            return

        # Ignore hidden files (starting with .)
        if path.name.startswith("."):
            return

        # Debounce: ignore rapid-fire events for the same file
        now = time.time()
        with self._lock:
            last = self._last_event.get(src_path, 0)
            if now - last < self._debounce_seconds:
                return
            self._last_event[src_path] = now

        logger.info("File event detected: %s", path.name)
        try:
            self._on_file_detected(src_path)
        except Exception:
            logger.exception("Error in file detection callback for %s", path.name)


class FileMonitor:
    """
    Monitors a directory for new and modified files.

    Uses watchdog for real-time OS-level events, plus a periodic
    reconciliation scan as a fallback for missed events.
    """

    def __init__(
        self,
        source_folder: str | Path,
        on_file_detected: Callable[[str], None],
        reconciliation_interval: int = 30,
        temp_suffix: str = ".transfer_tmp",
    ):
        """
        Args:
            source_folder: Directory to monitor.
            on_file_detected: Callback invoked with the file path when
                a new/modified file is detected.
            reconciliation_interval: Seconds between full folder scans.
            temp_suffix: Suffix used by transfer engine for temp files
                (these are ignored).
        """
        self._source_folder = Path(source_folder)
        self._on_file_detected = on_file_detected
        self._reconciliation_interval = reconciliation_interval
        self._temp_suffix = temp_suffix

        self._observer: Optional[Observer] = None
        self._reconcile_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._is_running = False
        self._known_files: dict[str, tuple[float, int]] = {}

    @property
    def is_running(self) -> bool:
        return self._is_running

    @property
    def source_folder(self) -> Path:
        return self._source_folder

    def start(self) -> None:
        """Start monitoring the source folder."""
        if self._is_running:
            logger.warning("Monitor is already running")
            return

        if not self._source_folder.exists():
            try:
                self._source_folder.mkdir(parents=True, exist_ok=True)
                logger.info("Created source folder: %s", self._source_folder)
            except OSError as e:
                logger.error("Cannot create source folder: %s", e)
                raise

        self._stop_event.clear()

        # Start watchdog observer
        handler = _FileEventHandler(
            on_file_detected=self._on_file_detected,
            temp_suffix=self._temp_suffix,
        )
        self._observer = Observer()
        self._observer.schedule(handler, str(self._source_folder), recursive=True)
        self._observer.daemon = True
        self._observer.start()

        # Start reconciliation thread
        self._reconcile_thread = threading.Thread(
            target=self._reconciliation_loop,
            name="FileMonitor-Reconciliation",
            daemon=True,
        )
        self._reconcile_thread.start()

        self._is_running = True
        logger.info("File monitor started for: %s", self._source_folder)

    def stop(self) -> None:
        """Stop monitoring."""
        if not self._is_running:
            return

        self._stop_event.set()

        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=5)
            self._observer = None

        if self._reconcile_thread:
            self._reconcile_thread.join(timeout=5)
            self._reconcile_thread = None

        self._is_running = False
        logger.info("File monitor stopped")

    def scan_folder(self) -> list[str]:
        """
        Perform a one-time scan of the source folder.

        Returns a list of file paths found. This is used for manual
        sync and reconciliation.
        """
        if not self._source_folder.exists():
            logger.warning("Source folder does not exist: %s", self._source_folder)
            return []

        files = []
        try:
            for item in self._source_folder.rglob('*'):
                if item.is_file():
                    # Skip temp files and hidden files
                    if item.name.endswith(self._temp_suffix):
                        continue
                    if item.name.startswith("."):
                        continue
                    files.append(str(item))
        except OSError as e:
            logger.error("Error scanning folder: %s", e)

        return files

    def _scan_folder_metadata(self) -> dict[str, tuple[float, int]]:
        """Return a mapping of file path -> (mtime, size) for reconciliation."""
        metadata = {}
        for path_str in self.scan_folder():
            try:
                st = Path(path_str).stat()
                metadata[path_str] = (st.st_mtime, st.st_size)
            except OSError:
                metadata[path_str] = (0.0, 0)
        return metadata

    def _reconciliation_loop(self) -> None:
        """Periodically scan the folder to catch missed events."""
        while not self._stop_event.is_set():
            self._stop_event.wait(self._reconciliation_interval)
            if self._stop_event.is_set():
                break

            try:
                current_meta = self._scan_folder_metadata()
                changed_files = []

                for file_path, (mtime, size) in current_meta.items():
                    if file_path not in self._known_files:
                        changed_files.append(file_path)
                    elif self._known_files[file_path] != (mtime, size):
                        changed_files.append(file_path)

                self._known_files = current_meta

                for file_path in changed_files:
                    logger.info("Reconciliation found/changed: %s", Path(file_path).name)
                    try:
                        self._on_file_detected(file_path)
                    except Exception:
                        logger.exception("Error in reconciliation callback")

            except Exception:
                logger.exception("Error during reconciliation scan")

    def update_known_files(self) -> None:
        """Refresh the set of known files (e.g., after startup)."""
        self._known_files = self._scan_folder_metadata()
