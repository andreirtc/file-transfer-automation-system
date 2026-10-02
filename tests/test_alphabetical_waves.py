from PySide6.QtCore import QObject, Signal
from core.models import FileStatus, TransferJob, TransferRecord
from core.transfer_manager import TransferManager


def test_late_ready_earlier_jobs_and_out_of_order_completion(monkeypatch, tmp_path, test_db, config, qapp):
    """Late readiness of 5/6 must not let 8/9 overtake the first wave."""
    starts = []

    class Worker(QObject):
        transfer_started = Signal(str)
        transfer_progress = Signal(str, str, int, int)
        transfer_completed = Signal(str, object)
        finished = Signal()
        worker_event = Signal(str, str)

        def __init__(self, records, job, **kwargs):
            super().__init__(kwargs['parent'])
            self._records = records
            self.job = job
            self._cancel_requested = False

        def start(self):
            starts.append(self.job.name)

        def isRunning(self):
            return False

    monkeypatch.setattr('core.transfer_manager.TransferWorker', Worker)
    config.set('max_concurrent_transfers', 3)
    config.set('report_auto_generate', False)
    jobs = {}
    for name in ['9', '8', '7', '6', '5']:
        job = TransferJob(name=name, source_folder=str(tmp_path/name), destination_folder=str(tmp_path/('dest'+name)))
        test_db.save_job(job); jobs[name] = job
    manager = TransferManager(config, test_db)
    records = {}
    for name, job in jobs.items():
        rec = TransferRecord(job_id=job.id, source_path=str(tmp_path/name/'file.bin'),
                             status=FileStatus.PROCESSING, override_window=True)
        records[name] = rec
        manager.get_controller(job.id)._active_records[rec.source_path] = rec
    try:
        for name in ['9', '8', '7']:
            manager.enqueue_job_batch(jobs[name].id, [records[name]])
        assert starts == []
        for name in ['5', '6']:
            manager.enqueue_job_batch(jobs[name].id, [records[name]])
        assert starts == ['5', '6', '7']
        for name in ['7', '5']:
            records[name].status = FileStatus.COMPLETED
            manager._on_worker_all_done(jobs[name].id)
            assert starts == ['5', '6', '7']
        records['6'].status = FileStatus.COMPLETED
        manager._on_worker_all_done(jobs['6'].id)
        assert starts == ['5', '6', '7', '8', '9']
        assert len(manager._active_workers) == 2
    finally:
        manager.shutdown()


def test_workspace_stop_requests_worker_cancellation(tmp_path, test_db, config, qapp):
    from unittest.mock import Mock
    job = TransferJob(name='Stop test', source_folder=str(tmp_path/'source'), destination_folder=str(tmp_path/'dest'))
    test_db.save_job(job)
    manager = TransferManager(config, test_db)
    manager.set_job(job)
    worker = Mock()
    worker.isRunning.return_value = True
    manager._active_workers[job.id] = worker
    try:
        manager.stop_monitoring()
        worker.cancel.assert_called_once()
        assert job.id in manager._dispatch_paused_jobs
    finally:
        manager._active_workers.clear()
        manager.shutdown()


def test_cancel_mid_copy_keeps_existing_destination(tmp_path, config):
    from core.transfer_engine import TransferEngine
    from core.file_safety import FileSafetyChecker
    from core.integrity import IntegrityVerifier
    source = tmp_path/'source.bin'; destination = tmp_path/'dest.bin'
    source.write_bytes(b'NEW CONTENT'*1024*1024)
    destination.write_bytes(b'KEEP EXISTING DESTINATION')
    config.set('overwrite_policy', 'overwrite')
    safety = FileSafetyChecker(stability_interval=0, required_stable_checks=0)
    engine = TransferEngine(safety, IntegrityVerifier(), config=config)
    safety.check_file(source)
    record = TransferRecord(source_path=str(source), destination_path=str(destination), file_name=source.name)
    cancelled = [False]
    def progress(phase, current, total):
        if phase == 'copy':
            cancelled[0] = True
    result = engine.transfer_file(record, progress, cancel_check=lambda: cancelled[0])
    assert not result.success
    assert record.status == FileStatus.READY
    assert record.verification_passed is None
    assert destination.read_bytes() == b'KEEP EXISTING DESTINATION'
    assert source.exists()
    assert not list(tmp_path.glob('*.transfer_tmp'))


def test_stopped_earlier_job_does_not_hold_the_queue(monkeypatch, tmp_path, test_db, config, qapp):
    config.set('max_concurrent_transfers', 1)
    jobs = []
    for name in ['5', '6']:
        job = TransferJob(name=name, source_folder=str(tmp_path/name), destination_folder=str(tmp_path/('dest'+name)))
        test_db.save_job(job); jobs.append(job)
    manager = TransferManager(config, test_db)
    early = TransferRecord(job_id=jobs[0].id, source_path='early', status=FileStatus.PROCESSING, override_window=True)
    manager.get_controller(jobs[0].id)._active_records['early'] = early
    later = TransferRecord(job_id=jobs[1].id, source_path='later', status=FileStatus.READY)
    # Observe actual dispatch without starting disk I/O.
    starts = []
    monkeypatch.setattr('core.transfer_manager.TransferWorker.start', lambda worker: starts.append(worker._job.name))
    try:
        manager.enqueue_job_batch(jobs[1].id, [later])
        assert starts == []
        manager.stop_job_monitoring(jobs[0].id)
        manager._dispatch_next_batch()
        assert starts == ['6']
    finally:
        manager.shutdown()
