"""
Shared test fixtures for the File Transfer Automation System tests.
"""

import os
import tempfile
import time
from pathlib import Path

import pytest

from core.file_safety import FileSafetyChecker
from core.integrity import IntegrityVerifier
from core.transfer_engine import TransferEngine
from services.configuration_service import ConfigurationService
from services.database_service import DatabaseService


@pytest.fixture
def tmp_source_dir(tmp_path):
    """Create a temporary source directory."""
    source = tmp_path / "source"
    source.mkdir()
    return source


@pytest.fixture
def tmp_dest_dir(tmp_path):
    """Create a temporary destination directory."""
    dest = tmp_path / "destination"
    dest.mkdir()
    return dest


@pytest.fixture
def test_db(tmp_path):
    """Create a temporary database."""
    db_path = tmp_path / "test.db"
    return DatabaseService(db_path)


@pytest.fixture
def config(tmp_path):
    """Create a test configuration with fast intervals."""
    config_path = tmp_path / "config.json"
    svc = ConfigurationService(config_path)
    # Use fast intervals for testing
    svc.set("stability_check_interval", 1)
    svc.set("required_stable_checks", 2)
    svc.set("max_retries", 2)
    svc.set("retry_delay", 1)
    svc.save()
    return svc


@pytest.fixture
def safety_checker():
    """Create a safety checker with fast intervals for testing."""
    return FileSafetyChecker(stability_interval=0, required_stable_checks=2)


@pytest.fixture
def integrity_verifier():
    """Create an integrity verifier."""
    return IntegrityVerifier()


@pytest.fixture
def transfer_engine(safety_checker, integrity_verifier):
    """Create a transfer engine."""
    return TransferEngine(safety_checker, integrity_verifier)


@pytest.fixture
def sample_file(tmp_source_dir):
    """Create a small sample file in the source directory."""
    file_path = tmp_source_dir / "sample.txt"
    file_path.write_text("Hello, World! This is a test file.", encoding="utf-8")
    return file_path


@pytest.fixture
def large_sample_file(tmp_source_dir):
    """Create a larger sample file (1 MB) in the source directory."""
    file_path = tmp_source_dir / "large_sample.bin"
    # Write 1 MB of data
    data = b"x" * 1024
    with open(file_path, "wb") as f:
        for _ in range(1024):
            f.write(data)
    return file_path


@pytest.fixture(scope="session")
def qapp():
    """Create or retrieve QApplication instance for Qt tests."""
    import sys
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app
