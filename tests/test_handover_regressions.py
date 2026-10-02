"""Handover regressions: operator requests, safety, backlog and UI event delivery."""
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QDate

from core.models import FileStatus, TransferJob, TransferRecord
from core.transfer_manager import JobController, TransferWorker, TransferManager
from core.compression_worker import compress_files
from services.report_service import ReportService


def make_controller(config, test_db, tmp_source_dir, tmp_dest_dir):
    config.set('report_auto_generate', False)
    config.set('automatic_monitoring', False)
    config.set('stability_check_interval', 0)
    job = TransferJob(name='Operator Test', source_folder=str(tmp_source_dir), destination_folder=str(tmp_dest_dir))
    test_db.save_job(job)
    return JobController(job, config, test_db)


def wait_for(qapp, predicate, timeout=10):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        qapp.processEvents()
        if predicate():
            return
        time.sleep(.02)
    assert predicate(), 'Qt workflow did not finish within timeout'


def test_sync_growing_file_never_ready(config, test_db, tmp_source_dir, tmp_dest_dir, qapp):
    ctrl = make_controller(config, test_db, tmp_source_dir, tmp_dest_dir)
    f = tmp_source_dir / 'growing.dmp'
    f.write_bytes(b'a')
    for i in range(4):
        f.write_bytes(b'a' * (i + 2))
        ready, processing = ctrl.sync_now()
        assert not ready
        assert len(processing) == 1
    ctrl.sync_now()
    ready, _ = ctrl.sync_now()
    assert len(ready) == 1
    assert ready[0].file_size == 5


@pytest.mark.parametrize('status', [FileStatus.QUEUED, FileStatus.TRANSFERRING, FileStatus.VERIFYING, FileStatus.CONFLICT])
def test_sync_leaves_live_records_alone(status, config, test_db, tmp_source_dir, tmp_dest_dir, qapp):
    ctrl = make_controller(config, test_db, tmp_source_dir, tmp_dest_dir)
    f = tmp_source_dir / 'live.txt'
    f.write_text('live')
    r = TransferRecord(job_id=ctrl.job.id, source_path=str(f), file_name=f.name, status=status)
    ctrl._active_records[str(f)] = r
    ready, processing = ctrl.sync_now()
    assert not ready and not processing
    assert r.status == status


def test_source_unavailable_does_not_mark_deleted(config, test_db, tmp_source_dir, tmp_dest_dir, qapp):
    ctrl = make_controller(config, test_db, tmp_source_dir, tmp_dest_dir)
    r = TransferRecord(job_id=ctrl.job.id, source_path=str(tmp_source_dir / 'missing'), status=FileStatus.PROCESSING)
    ctrl._active_records[r.source_path] = r
    tmp_source_dir.rmdir()
    with pytest.raises(OSError):
        ctrl.sync_now()
    assert r.status == FileStatus.PROCESSING


def test_nested_files_keep_paths(config, test_db, tmp_source_dir, tmp_dest_dir, qapp):
    ctrl = make_controller(config, test_db, tmp_source_dir, tmp_dest_dir)
    for name in ('a', 'b'):
        folder = tmp_source_dir / name
        folder.mkdir()
        (folder / 'backup.dmp').write_text(name)
    ctrl.sync_now()
    ctrl.sync_now()
    ready, _ = ctrl.sync_now()
    worker = TransferWorker(ready, ctrl._engine, test_db, config, ctrl.job)
    worker.run()
    assert (tmp_dest_dir / 'a' / 'backup.dmp').read_text() == 'a'
    assert (tmp_dest_dir / 'b' / 'backup.dmp').read_text() == 'b'


@pytest.mark.parametrize('policy, expected', [('ask', FileStatus.CONFLICT), ('skip', FileStatus.SKIPPED), ('overwrite', FileStatus.COMPLETED)])
def test_overwrite_policy_is_enforced(policy, expected, config, test_db, tmp_source_dir, tmp_dest_dir, qapp):
    ctrl = make_controller(config, test_db, tmp_source_dir, tmp_dest_dir)
    config.set('overwrite_policy', policy)
    source = tmp_source_dir / 'same.txt'
    source.write_text('new')
    dest = tmp_dest_dir / source.name
    dest.write_text('old')
    rec = TransferRecord(source_path=str(source), destination_path=str(dest), file_name=source.name, file_size=3)
    result = ctrl._engine.transfer_file(rec)
    assert rec.status == expected
    assert result.was_conflict == (policy == 'ask')
    assert dest.read_text() == ('new' if policy == 'overwrite' else 'old')


def test_failed_atomic_replace_preserves_existing(config, test_db, tmp_source_dir, tmp_dest_dir, qapp, monkeypatch):
    ctrl = make_controller(config, test_db, tmp_source_dir, tmp_dest_dir)
    config.set('overwrite_policy', 'overwrite')
    source = tmp_source_dir / 'same.txt'
    source.write_text('new')
    dest = tmp_dest_dir / source.name
    dest.write_text('old')
    rec = TransferRecord(source_path=str(source), destination_path=str(dest), file_name=source.name)
    def fail(*args):
        raise PermissionError('Destination locked')
    monkeypatch.setattr('core.transfer_engine.os.replace', fail)
    assert not ctrl._engine.transfer_file(rec).success
    assert dest.read_text() == 'old'
    assert not (tmp_dest_dir / '.same.txt.transfer_tmp').exists()


@pytest.mark.parametrize('enabled', [False, True])
def test_cleanup_preserves_modified_source(enabled, config, test_db, tmp_source_dir, tmp_dest_dir, qapp):
    ctrl = make_controller(config, test_db, tmp_source_dir, tmp_dest_dir)
    config.set('auto_cleanup_enabled', enabled)
    source = tmp_source_dir / 'same.txt'
    source.write_text('original')
    dest = tmp_dest_dir / source.name
    rec = TransferRecord(job_id=ctrl.job.id, source_path=str(source), destination_path=str(dest), file_name=source.name, file_size=source.stat().st_size, source_modified=source.stat().st_mtime)
    ctrl._engine.transfer_file(rec)
    rec.transfer_completed = datetime.now() - timedelta(days=30)
    test_db.save_record(rec)
    source.write_text('replacement')
    ctrl._run_auto_cleanup()
    assert source.read_text() == 'replacement'


def test_aes_failure_never_creates_unencrypted_fallback(tmp_path, monkeypatch):
    source = tmp_path / 'secret.txt'
    source.write_text('confidential')
    def fail(*args, **kwargs):
        raise RuntimeError('AES unavailable')
    monkeypatch.setattr('pyzipper.AESZipFile', fail)
    with pytest.raises(RuntimeError):
        compress_files([str(source)], [''], str(tmp_path / 'archive.zip'), 'secret')
    assert not (tmp_path / 'archive.zip').exists()


def test_invalid_cycle_does_not_crash_range():
    start, end = ReportService.get_cycle_range_for_date('2026-09-15', '99:00', '12:00')
    assert start == datetime(2026, 9, 15, 18)
    assert end == datetime(2026, 9, 16, 12)


def test_edit_dialog_does_not_mutate_job(config, test_db, tmp_source_dir, tmp_dest_dir, qapp):
    from gui.job_dialog import JobDialog
    from PySide6.QtWidgets import QWidget
    ctrl = make_controller(config, test_db, tmp_source_dir, tmp_dest_dir)
    parent = QWidget()
    dialog = JobDialog(ctrl.job, parent)
    dialog._name_edit.setText('Changed')
    assert dialog.validate()
    dialog.reject()
    assert ctrl.job.name == 'Operator Test'
    dialog.deleteLater()
    parent.deleteLater()


def test_workspace_batch_button_end_to_end(config, test_db, tmp_source_dir, tmp_dest_dir, qapp):
    from gui.main_window import MainWindow
    ctrl = make_controller(config, test_db, tmp_source_dir, tmp_dest_dir)
    source = tmp_source_dir / 'overnight.dmp'
    source.write_bytes(b'backup payload')
    stamp = datetime(2026, 9, 16, 2, 30).timestamp()
    os.utime(source, (stamp, stamp))
    other = tmp_source_dir / 'next_batch.dmp'
    other.write_text('leave for next batch')
    stamp2 = datetime(2026, 9, 16, 23).timestamp()
    os.utime(other, (stamp2, stamp2))
    window = MainWindow(config, test_db)
    try:
        window._dashboard._calendar_picker.setDate(QDate(2026, 9, 15))
        window._dashboard._btn_transfer_batch.click()
        wait_for(qapp, lambda: not window._syncing_jobs)
        wait_for(qapp, lambda: bool(test_db.check_already_transferred(ctrl.job.id, str(source), source.stat().st_size, source.stat().st_mtime)))
        wait_for(qapp, lambda: not window._manager._active_workers)
        assert (tmp_dest_dir / source.name).read_bytes() == source.read_bytes()
        assert not (tmp_dest_dir / other.name).exists()
        window._dashboard._batch_filter_switch.setChecked(True)
        qapp.processEvents()
        assert window._dashboard.transfer_table._proxy.rowCount() == 1
        # A second request must clear its busy flag and leave duplicate history alone.
        window._dashboard._btn_transfer_batch.click()
        wait_for(qapp, lambda: not window._syncing_jobs)
        assert len(test_db.get_records_by_job(ctrl.job.id)) == 1
    finally:
        window._manager.shutdown()
        wait_for(qapp, lambda: not window._manager._active_workers)
        window.close()


def test_sync_error_releases_busy_flag(config, test_db, tmp_source_dir, tmp_dest_dir, qapp):
    from gui.main_window import MainWindow
    ctrl = make_controller(config, test_db, tmp_source_dir, tmp_dest_dir)
    tmp_source_dir.rmdir()
    window = MainWindow(config, test_db)
    try:
        window._dashboard._btn_sync.click()
        wait_for(qapp, lambda: not window._syncing_jobs)
        table = window._main_dashboard._activity_table
        assert any('Sync failed' in table.item(row, 3).text() for row in range(table.rowCount()))
    finally:
        window.close()


def test_backlog_report_uses_record_batch(config, test_db, tmp_source_dir, tmp_dest_dir, qapp, monkeypatch):
    ctrl = make_controller(config, test_db, tmp_source_dir, tmp_dest_dir)
    config.set('report_auto_generate', True)
    manager = TransferManager(config, test_db)
    record = TransferRecord(job_id=ctrl.job.id, batch_date='2026-09-15', status=FileStatus.COMPLETED)
    worker = Mock()
    worker._records = [record]
    worker._cancel_requested = False
    manager._active_workers[ctrl.job.id] = worker
    called = []
    def generate(self, batch):
        called.append(batch)
        return Path('report.xlsx')
    monkeypatch.setattr(ReportService, 'generate_daily_report', generate)
    manager._on_worker_all_done(ctrl.job.id)
    wait_for(qapp, lambda: bool(called))
    assert called == ['2026-09-15']
    manager.shutdown()

def test_parallel_direct_worker_preserves_conflict_result(config, test_db, tmp_source_dir, tmp_dest_dir, qapp):
    ctrl = make_controller(config, test_db, tmp_source_dir, tmp_dest_dir)
    config.set('overwrite_policy', 'ask')
    records = []
    for name in ('a.txt', 'b.txt'):
        source = tmp_source_dir / name
        source.write_text('new')
        dest = tmp_dest_dir / name
        dest.write_text('old')
        records.append(TransferRecord(job_id=ctrl.job.id, file_name=name, source_path=str(source), destination_path=str(dest)))
    results = []
    worker = TransferWorker(records, ctrl._engine, test_db, config, ctrl.job)
    worker.transfer_completed.connect(lambda rid, result: results.append(result))
    worker.run()
    qapp.processEvents()
    assert len(results) == 2
    assert all(r.was_conflict for r in results)
    assert all(r.record.status == FileStatus.CONFLICT for r in results)


def test_report_unknown_verification_stays_pending(config, test_db, tmp_source_dir, tmp_dest_dir, qapp):
    ctrl = make_controller(config, test_db, tmp_source_dir, tmp_dest_dir)
    config.set('checklist_systems', [{'job_name': ctrl.job.name, 'linked_job': ctrl.job.id, 'pattern': 'demo', 'file_type': 'FILE'}])
    rec = TransferRecord(job_id=ctrl.job.id, file_name='demo.txt', source_path=str(tmp_source_dir / 'demo.txt'), status=FileStatus.COMPLETED, batch_date='2026-09-15', verification_passed=None)
    test_db.save_record(rec)
    row = ReportService(config, test_db).get_report_data('2026-09-15')['table_rows'][0]
    assert row['verification_status'] == 'Pending'
    assert row['integrity_check'] != 'Passed'


def test_cleanup_disabled_retains_unchanged_source(config, test_db, tmp_source_dir, tmp_dest_dir, qapp):
    ctrl = make_controller(config, test_db, tmp_source_dir, tmp_dest_dir)
    source = tmp_source_dir / 'old.txt'
    source.write_text('backup')
    rec = TransferRecord(job_id=ctrl.job.id, file_name=source.name, source_path=str(source), destination_path=str(tmp_dest_dir / source.name), file_size=source.stat().st_size, source_modified=source.stat().st_mtime)
    assert ctrl._engine.transfer_file(rec).success
    rec.transfer_completed = datetime.now() - timedelta(days=30)
    test_db.save_record(rec)
    ctrl._run_auto_cleanup()
    assert source.exists()
    config.set('auto_cleanup_enabled', True)
    ctrl._run_auto_cleanup()
    assert not source.exists()


def test_custom_cycle_legacy_table_filter(config, qapp):
    from gui.dashboard import DashboardWidget
    config.set('operational_cycle_start', '20:00')
    config.set('operational_cycle_end', '08:00')
    dash = DashboardWidget(config)
    stamp = datetime(2026, 9, 16, 10).timestamp()
    rec = TransferRecord(file_name='legacy.txt', source_modified=stamp)
    dash.set_records([rec])
    dash._calendar_picker.setDate(QDate(2026, 9, 16))
    dash._batch_filter_switch.setChecked(True)
    assert rec.batch_date == '2026-09-16'
    assert dash.transfer_table._proxy.rowCount() == 1
    dash.deleteLater()


def test_settings_job_presets_and_docs_smoke(config, test_db, tmp_source_dir, tmp_dest_dir, qapp, monkeypatch):
    from PySide6.QtWidgets import QWidget
    from gui.job_dialog import JobDialog
    from gui.dialogs import SettingsDialog
    from gui.docs_page import DocsPageWidget
    ctrl = make_controller(config, test_db, tmp_source_dir, tmp_dest_dir)
    parent = QWidget()
    settings = SettingsDialog(config, parent)
    assert settings.validate()
    job = JobDialog(ctrl.job, parent)
    job._window_check.setChecked(True)
    job._btn_weekdays.click()
    assert [d for d, c in job._day_checks.items() if c.isChecked()] == ['Mon', 'Tue', 'Wed', 'Thu', 'Fri']
    job._btn_weekends.click()
    assert [d for d, c in job._day_checks.items() if c.isChecked()] == ['Sat', 'Sun']
    job._btn_everyday.click()
    assert all(c.isChecked() for c in job._day_checks.values())
    docs = DocsPageWidget()
    for i in range(4):
        docs._list_widget.setCurrentRow(i)
        assert 'Guide unavailable' not in docs._content_browser.toPlainText()
        assert len(docs._content_browser.toPlainText()) > 500
    settings.deleteLater()
    job.deleteLater()
    docs.deleteLater()
    parent.deleteLater()

def test_last_job_removal_clears_workspace(config, test_db, tmp_source_dir, tmp_dest_dir, qapp):
    from gui.main_window import MainWindow
    ctrl = make_controller(config, test_db, tmp_source_dir, tmp_dest_dir)
    window = MainWindow(config, test_db)
    try:
        test_db.delete_job(ctrl.job.id)
        window._manager.reload_jobs()
        window._load_initial_jobs()
        assert window._manager.current_job is None
        assert not window._dashboard._btn_sync.isEnabled()
        assert not window._dashboard._btn_transfer_batch.isEnabled()
        assert window._dashboard._source_label.text() == '—'
        assert window._dashboard._monitor_status_label.text() == 'OFF'
    finally:
        window.close()
