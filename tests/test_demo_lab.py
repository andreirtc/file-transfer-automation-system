"""Validate practice data and the operator's independent verification tool."""
import json
import shutil
from datetime import datetime
from pathlib import Path

import pytest

from core.demo_lab import prepare_lab, checked_lab, grow_file, verify_lab, PASSWORD
from core.compression_worker import compress_files
from services.configuration_service import ConfigurationService
from services.database_service import DatabaseService
from services.report_service import ReportService


def test_lab_crossover_timestamps_and_safe_jobs(tmp_path):
    root = prepare_lab(tmp_path / 'practice')
    _, manifest = checked_lab(root)
    config = ConfigurationService(root / 'App/config/config.json')
    jobs = DatabaseService(root / 'App/database/transfer_history.db').get_jobs()
    assert len(jobs) == 5
    assert not config.automatic_monitoring
    assert not config.get_bool('auto_cleanup_enabled')
    assert all(not job.auto_monitor for job in jobs)
    assert all(Path(job.source_folder).is_relative_to(root) for job in jobs)
    selected = []
    for entry in manifest['files']:
        stamp = datetime.fromtimestamp((root / entry['source']).stat().st_mtime)
        assert stamp.isoformat(sep=' ') == entry['modified']
        assert ReportService.resolve_operational_batch_date(stamp) == entry['batch']
        if entry['job'] == '01 Crossover' and entry['batch'] == manifest['batch']:
            selected.append(entry)
    assert len(selected) == 6
    assert any('0000' in entry['source'] for entry in selected)
    assert not any('120000' in entry['source'] for entry in selected)


def test_first_batch_verifier_requires_copies_and_excludes_other_dates(tmp_path):
    root = prepare_lab(tmp_path / 'practice')
    _, data = checked_lab(root)
    assert not verify_lab(root, True)
    for entry in data['files']:
        if entry['job'] == '01 Crossover' and entry['batch'] == data['batch']:
            destination = root / entry['destination']
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root / entry['source'], destination)
    assert verify_lab(root, True)
    extra = next(e for e in data['files'] if '120000' in e['source'])
    shutil.copy2(root / extra['source'], root / extra['destination'])
    assert not verify_lab(root, True)
    assert 'UNEXPECTED OTHER BATCH COPY' in (root / 'VERIFY_RESULTS.txt').read_text()


def test_repeat_setup_never_overwrites_session(tmp_path):
    root = prepare_lab(tmp_path / 'practice')
    before = (root / 'App/config/config.json').read_bytes()
    with pytest.raises(FileExistsError):
        prepare_lab(root)
    assert (root / 'App/config/config.json').read_bytes() == before
    data = json.loads((root / 'manifest.json').read_text())
    data['root'] = 'not this folder'
    (root / 'manifest.json').write_text(json.dumps(data))
    with pytest.raises(ValueError):
        grow_file(root, duration=0)


def test_growth_and_zip_verification(tmp_path):
    root = prepare_lab(tmp_path / 'practice')
    growing = root / 'Files/03/Source/growing.dmp'
    before = growing.stat().st_size
    grow_file(root, duration=.02, interval=.03)
    assert growing.stat().st_size > before
    sources = [root / 'Files/05/Source/zip_sample.dmp', root / 'Files/05/Source/nested/zip_sample.dmp']
    compress_files([str(p) for p in sources], ['', 'nested'], str(root / 'Files/05/Destination/demo.zip'), PASSWORD)
    verify_lab(root)
    result = (root / 'VERIFY_RESULTS.txt').read_text()
    assert result.count('ZIP MATCH') == 2
    sources[0].write_bytes(b'changed after transfer')
    verify_lab(root)
    assert 'ZIP DIFFERENT' in (root / 'VERIFY_RESULTS.txt').read_text()


def test_generated_lab_selected_batch_button(qapp, tmp_path, monkeypatch):
    """Exercise the six crossover samples using the same button as the demo."""
    import time
    from PySide6.QtCore import QDate
    from gui.main_window import MainWindow
    from qfluentwidgets import InfoBar
    notifications = []
    monkeypatch.setattr(InfoBar, 'info', lambda **kwargs: notifications.append(kwargs))
    root = prepare_lab(tmp_path / 'practice')
    _, data = checked_lab(root)
    config = ConfigurationService(root / 'App/config/config.json')
    db = DatabaseService(root / 'App/database/transfer_history.db')
    window = MainWindow(config, db)
    try:
        window._dashboard._calendar_picker.setDate(QDate.fromString(data['batch'], 'yyyy-MM-dd'))
        window._dashboard._btn_transfer_batch.click()
        until = time.monotonic() + 25
        while time.monotonic() < until:
            qapp.processEvents()
            if not window._syncing_jobs and not window._manager._active_workers and verify_lab(root, True):
                break
            time.sleep(.1)
        assert verify_lab(root, True)
        window._dashboard._btn_transfer_batch.click()
        until = time.monotonic() + 5
        while window._syncing_jobs and time.monotonic() < until:
            qapp.processEvents()
            time.sleep(.05)
        assert not window._syncing_jobs
        assert verify_lab(root, True)
        assert any('6 file(s) already transferred' in item['content'] and
                   'Nothing new to transfer' in item['content'] for item in notifications)
        assert window._manager.get_controller(window._manager.current_job.id).last_sync_summary == {
            'matched': 6, 'already_transferred': 6, 'in_progress': 0, 'unreadable': 0}
        window._dashboard._calendar_picker.setDate(QDate(1900, 1, 1))
        window._dashboard._btn_transfer_batch.click()
        until = time.monotonic() + 5
        while window._syncing_jobs and time.monotonic() < until:
            qapp.processEvents()
            time.sleep(.05)
        assert any('No source files match this batch' in item['content'] for item in notifications)
    finally:
        window._manager.shutdown()
        window.close()


def test_identical_destination_notifies_without_copy(qapp, tmp_path, monkeypatch):
    from core.models import TransferRecord
    from gui.main_window import MainWindow
    from qfluentwidgets import InfoBar
    root = prepare_lab(tmp_path / 'practice')
    config = ConfigurationService(root / 'App/config/config.json')
    db = DatabaseService(root / 'App/database/transfer_history.db')
    window = MainWindow(config, db)
    notifications = []
    monkeypatch.setattr(InfoBar, 'info', lambda **kwargs: notifications.append(kwargs))
    try:
        job = next(job for job in db.get_jobs() if job.name == '02 Conflicts')
        source = Path(job.source_folder) / 'matching.dmp'
        dest = Path(job.destination_folder) / source.name
        before = dest.stat().st_mtime_ns
        ctrl = window._manager.get_controller(job.id)
        record = TransferRecord(job_id=job.id, source_path=str(source), destination_path=str(dest), file_name=source.name)
        result = ctrl._engine.transfer_file(record)
        assert result.success and result.destination_already_matched
        assert dest.stat().st_mtime_ns == before
        window._on_job_transfer_completed(job.id, record.id, result)
        assert any('Verified without copying again' in item['content'] for item in notifications)
    finally:
        window._manager.shutdown()
        window.close()
