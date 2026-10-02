"""Explicit disposable performance tests using the application's transfer manager."""
from __future__ import annotations
import ctypes
import hashlib
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from core.models import TransferJob, TransferRecord, FileStatus
from services.configuration_service import ConfigurationService
from services.database_service import DatabaseService

MARKER = 'FTAS performance lab v1'


def prepare(path: Path):
    root = path.resolve()
    root.mkdir(parents=True, exist_ok=False)
    plan = dict(marker=MARKER, root=str(root), source_file='', source_directory='', source_relative_root='', generated_file_mib=256,
                job_count=3, concurrency_limits=[1, 2, 3], destination_root=str(root/'Copies'),
                start_at_local='', target_duration_seconds=300)
    (root/'PLAN.json').write_text(json.dumps(plan, indent=2), encoding='utf-8')
    (root/'INSTRUCTIONS.txt').write_text(
        'PERFORMANCE TEST - separate test folders, no production history\n\n'
        '1. Edit PLAN.json, then save and close Notepad.\n'
        '2. Leave source_file empty for a generated 256 MiB sample. For your real file, enter its full local or UNC path.\n'
        '   Alternatively set source_directory to test every file recursively; keep source_file empty.\n'
        '   JSON backslashes must be doubled: "\\\\Laptop\\\\Share\\\\backup.dmp". Forward slashes also work on Windows.\n'
        '3. destination_root must be an approved test-only local or UNC folder. Each run creates NEW subfolders there.\n'
        '4. job_count=3 copies the same selected file/folder to three distinct destinations; concurrency_limits compares 1, 2, 3 active jobs.\n'
        '   source_relative_root may preserve parent subfolders for a selected file; blank uses its immediate parent.\n'
        '5. start_at_local may be empty or YYYY-MM-DD HH:MM:SS (this PC local clock). The helper waits until then before copying.\n'
        '6. target_duration_seconds is a performance target, NOT forced cancellation. Copy and verification may finish after it.\n'
        '7. Return to the launcher and continue. Wait for RESULT.json and RESULT.txt; no company job database is used.\n\n'
        'Memory is the benchmark process working set/private memory. CPU includes all its threads, normalized to logical CPUs.\n'
        'The real Qt transfer manager and hidden UI are instantiated; rendering a visible GUI, antivirus, SMB server CPU and other processes are not measured.\n'
        'Full SHA-256 verification is enabled. Reported speed includes copying and verification; disk caches affect later runs.\n'
        'This is Python chunked copying with safe temporary files and verification, NOT robocopy.exe.\n'
        'Concurrent jobs can increase memory and compete for network/disk bandwidth. No fixed low-resource guarantee.\n'
        'The app schedule triggers at WINDOW END, not start; it is not a deadline. Use the demo Scheduled job to test that UI trigger.\n'
        'Generated samples and copies are real disk data, retained until you remove your test folders.\n', encoding='utf-8')


def process_memory() -> tuple[float, float]:
    from ctypes import wintypes
    class Counters(ctypes.Structure):
        _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD)] + [
            (name, ctypes.c_size_t) for name in ('PeakWorkingSetSize', 'WorkingSetSize', 'QuotaPeakPagedPoolUsage',
            'QuotaPagedPoolUsage', 'QuotaPeakNonPagedPoolUsage', 'QuotaNonPagedPoolUsage',
            'PagefileUsage', 'PeakPagefileUsage', 'PrivateUsage')]
    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    get_memory = ctypes.WinDLL('psapi', use_last_error=True).GetProcessMemoryInfo
    get_memory.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    get_memory.restype = wintypes.BOOL
    if not get_memory(wintypes.HANDLE(-1), ctypes.byref(counters), counters.cb):
        raise ctypes.WinError(ctypes.get_last_error())
    return counters.WorkingSetSize / 1048576, counters.PrivateUsage / 1048576


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024*1024), b''):
            value.update(chunk)
    return value.hexdigest()


def configure(path: Path) -> bool:
    """A small test setup form avoids requiring users to escape UNC paths in JSON."""
    from PySide6.QtWidgets import (QApplication, QDialog, QFormLayout, QVBoxLayout, QHBoxLayout,
        QLineEdit, QComboBox, QSpinBox, QCheckBox, QPushButton, QFileDialog, QDialogButtonBox, QLabel)
    app = QApplication.instance() or QApplication([])
    root = path.resolve()
    plan = json.loads((root/'PLAN.json').read_text(encoding='utf-8'))
    dialog = QDialog()
    dialog.setWindowTitle('File Transfer Performance Test - setup')
    dialog.resize(760, 450)
    layout = QVBoxLayout(dialog)
    introduction = QLabel('Choose test sources and a test-only destination. Original files are retained.\n'
        'Each job gets a separate destination; comparison runs create additional copies.')
    introduction.setWordWrap(True)
    layout.addWidget(introduction)
    form = QFormLayout()
    layout.addLayout(form)
    kind = QComboBox()
    kind.addItems(['Generate a sample file', 'Use an existing file', 'Use an entire folder (recursive)'])
    form.addRow('Source type:', kind)
    source = QLineEdit()
    source.setPlaceholderText('Paste a file/folder path here, or Browse. UNC paths can be pasted normally.')
    source_row = QHBoxLayout()
    browse = QPushButton('Browse…')
    source_row.addWidget(source)
    source_row.addWidget(browse)
    form.addRow('Source:', source_row)
    def choose_source():
        chosen = QFileDialog.getExistingDirectory(dialog, 'Choose a test source folder') if kind.currentIndex()==2 else QFileDialog.getOpenFileName(dialog, 'Choose a stable existing test file')[0]
        if chosen:
            source.setText(chosen)
    browse.clicked.connect(choose_source)
    size = QSpinBox()
    size.setRange(1, 4096)
    size.setValue(256)
    size.setSuffix(' MiB')
    form.addRow('Generated sample size:', size)
    destination = QLineEdit(plan['destination_root'])
    destination_row = QHBoxLayout()
    destination_browse = QPushButton('Browse…')
    destination_row.addWidget(destination)
    destination_row.addWidget(destination_browse)
    form.addRow('Test destination:', destination_row)
    def choose_destination():
        chosen = QFileDialog.getExistingDirectory(dialog, 'Choose a test-only destination')
        if chosen:
            destination.setText(chosen)
    destination_browse.clicked.connect(choose_destination)
    jobs = QSpinBox()
    jobs.setRange(1, 3)
    jobs.setValue(3)
    form.addRow('Copies / jobs per run:', jobs)
    choices = []
    row = QHBoxLayout()
    for count in (1, 2, 3):
        choice = QCheckBox(f'{count} active job(s)')
        choice.setChecked(True)
        row.addWidget(choice)
        choices.append(choice)
    form.addRow('Compare concurrency:', row)
    start = QLineEdit()
    start.setPlaceholderText('Blank = start now; otherwise YYYY-MM-DD HH:MM:SS, local clock')
    form.addRow('Start at (optional):', start)
    target = QSpinBox()
    target.setRange(1, 1440)
    target.setValue(5)
    target.setSuffix(' minutes (measured target, not forced cancellation)')
    form.addRow('Completion target:', target)
    description = QLabel('Full SHA-256 verification is included. Three concurrency settings × three jobs means nine copies.\n'
        'Results report time, throughput, CPU and RAM for this process. Server CPU and whole-PC usage are not measured.')
    description.setWordWrap(True)
    layout.addWidget(description)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)
    if not dialog.exec():
        return False
    plan.update(source_file=source.text().strip() if kind.currentIndex()==1 else '',
                source_directory=source.text().strip() if kind.currentIndex()==2 else '',
                generated_file_mib=size.value(), destination_root=destination.text().strip(),
                job_count=jobs.value(), concurrency_limits=[i+1 for i, c in enumerate(choices) if c.isChecked()],
                start_at_local=start.text().strip(), target_duration_seconds=target.value()*60)
    if kind.currentIndex() and not source.text().strip():
        raise ValueError('Choose a source file or folder before starting.')
    (root/'PLAN.json').write_text(json.dumps(plan, indent=2), encoding='utf-8')
    return True


def run(path: Path):
    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtWidgets import QApplication
    from gui.main_window import MainWindow
    from services.report_service import ReportService
    root = path.resolve()
    plan = json.loads((root/'PLAN.json').read_text(encoding='utf-8-sig'))
    if plan.get('marker') != MARKER or plan.get('root') != str(root):
        raise ValueError('Use the original performance session, not a moved folder.')
    count = int(plan['job_count'])
    limits = [int(n) for n in plan['concurrency_limits']]
    if count not in (1, 2, 3) or not limits or any(n not in (1, 2, 3) for n in limits):
        raise ValueError('Choose 1, 2 or 3 jobs/concurrency.')
    if float(plan['target_duration_seconds']) <= 0:
        raise ValueError('Duration target must be positive.')
    if plan.get('source_directory') and plan['source_file']:
        raise ValueError('Choose a source file OR a source directory, not both.')
    if plan.get('source_directory'):
        source_root = Path(plan['source_directory']).resolve(strict=True)
        if not source_root.is_dir():
            raise ValueError('Source directory must be a folder.')
        sources = sorted(p for p in source_root.rglob('*') if p.is_file())
        if not sources:
            raise ValueError('Source directory is empty.')
    elif plan['source_file']:
        source = Path(plan['source_file']).resolve(strict=True)
        if not source.is_file():
            raise ValueError('Select an existing FILE, not a folder.')
        sources = [source]
        source_root = Path(plan['source_relative_root']).resolve(strict=True) if plan.get('source_relative_root') else source.parent
        source.relative_to(source_root)
    else:
        source = root/'Source/payload.bin'
        source.parent.mkdir(exist_ok=True)
        size = int(plan['generated_file_mib'])
        if not 1 <= size <= 4096:
            raise ValueError('Generated file size must be 1–4096 MiB.')
        # Never silently truncate a prior generated payload.
        with source.open('xb') as output:
            for _ in range(size):
                output.write(os.urandom(1048576))
        sources = [source]
        source_root = source.parent
    destination_root = Path(plan['destination_root'])
    if not destination_root.is_absolute():
        raise ValueError('Destination must be an absolute local or UNC test path.')
    destination_root.mkdir(parents=True, exist_ok=True)
    # Unique run namespace; nothing is overwritten even when a network share is used.
    import uuid
    output_root = destination_root / ('FTAS-test-' + uuid.uuid4().hex[:12])
    output_root.mkdir(exist_ok=False)
    (root/'PROGRESS.txt').write_text('Reading source hashes before timing transfers.\n', encoding='utf-8')
    source_before = {p: (p.stat().st_size, p.stat().st_mtime_ns) for p in sources}
    source_digest = {}
    for index, source in enumerate(sources, 1):
        (root/'PROGRESS.txt').write_text(f'Reading initial source hashes: file {index}/{len(sources)}. Transfer timing has not started.\n', encoding='utf-8')
        source_digest[source] = sha256(source)
    total_bytes = sum(stat[0] for stat in source_before.values())
    app = QApplication.instance() or QApplication([])
    ReportService.reports_dir = root/'Reports'
    results = []
    start_text = plan.get('start_at_local', '').strip()
    start_at = datetime.strptime(start_text, '%Y-%m-%d %H:%M:%S') if start_text else None
    while start_at and datetime.now() < start_at:
        app.processEvents()
        time.sleep(.1)
    for run_number, limit in enumerate(limits, 1):
        config = ConfigurationService(root/f'Runs/{run_number}/config.json')
        for key, value in dict(automatic_monitoring=False, auto_cleanup_enabled=False,
                report_auto_generate=False, transfer_mode='direct', batch_compression_enabled=False,
                smart_verification_enabled=False, transfer_threads=1, max_concurrent_transfers=limit,
                stability_check_interval=1, required_stable_checks=2).items():
            config.set(key, value)
        config.save()
        db = DatabaseService(root/f'Runs/{run_number}/history.db')
        jobs = []
        for index in range(count):
            dest = output_root/f'Run-{run_number}-Concurrency-{limit}'/f'Job-{index+1}'
            dest.mkdir(parents=True, exist_ok=False)
            job = TransferJob(name=f'Performance {index+1}', source_folder=str(source_root),
                              destination_folder=str(dest), auto_monitor=False)
            db.save_job(job)
            jobs.append(job)
        window = MainWindow(config, db)  # Own hidden UI/database; no production app actions.
        manager = window._manager
        records = []
        for job in jobs:
            for source in sources:
                records.append(TransferRecord(job_id=job.id, source_path=str(source), file_name=source.name,
                    destination_path=str(Path(job.destination_folder)/source.relative_to(source_root)), file_size=source.stat().st_size,
                    source_modified=source.stat().st_mtime, status=FileStatus.READY))
        try:
            until = time.monotonic()+120
            while True:
                states = [manager.get_controller(job.id)._safety.check_file(source) for job in jobs for source in sources]
                if all(state == FileStatus.READY for state in states):
                    break
                (root/'PROGRESS.txt').write_text(f'Waiting for safe source files: {sum(state == FileStatus.READY for state in states)}/{len(states)} ready.\n', encoding='utf-8')
                if time.monotonic() > until:
                    diagnostics = [dict(job=job.name, source=str(source),
                        stable_checks=getattr(manager.get_controller(job.id)._safety._checks.get(str(source)), 'stable_count', 0),
                        accessible=getattr(manager.get_controller(job.id)._safety._checks.get(str(source)), 'is_accessible', False))
                        for job in jobs for source in sources]
                    raise RuntimeError('Source was not stable/readable within 120 seconds. Finish producing the backup and check permissions. Details: ' + json.dumps(diagnostics))
                app.processEvents()
                time.sleep(.1)
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            import gc
            gc.collect()
            baseline_rss, baseline_private = process_memory()
            peak_rss, peak_private = baseline_rss, baseline_private
            started_at = datetime.now().isoformat(sep=' ', timespec='milliseconds')
            start, cpu_start = time.monotonic(), time.process_time()
            observed_jobs = 0
            samples = []
            for job in jobs:
                selected = [record for record in records if record.job_id == job.id]
                db.save_records_batch(selected)
                manager.get_controller(job.id)._active_records.update({record.source_path: record for record in selected})
                manager.enqueue_job_batch(job.id, selected, auto_dispatch=False)
            manager._dispatch_next_batch()
            while manager._active_workers or manager._transfer_queue:
                app.processEvents()
                QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
                rss, private = process_memory()
                peak_rss, peak_private = max(peak_rss, rss), max(peak_private, private)
                observed_jobs = max(observed_jobs, len(manager._active_workers))
                samples.append(dict(elapsed_seconds=round(time.monotonic()-start, 3),
                                    rss_mib=round(rss, 2), private_mib=round(private, 2),
                                    active_jobs=len(manager._active_workers)))
                if len(samples) % 20 == 0:
                    (root/'PROGRESS.txt').write_text(f"Run {run_number}/{len(limits)}, concurrency {limit}: {time.monotonic()-start:.1f} seconds; "
                        f"{len(manager._active_workers)} active jobs; {sum(r.status == FileStatus.COMPLETED for r in records)}/{len(records)} files complete; "
                        f"RAM {rss:.1f} MiB\n", encoding='utf-8')
                time.sleep(.05)
            elapsed = time.monotonic()-start
            finished_at = datetime.now().isoformat(sep=' ', timespec='milliseconds')
            cpu_seconds = time.process_time()-cpu_start
            passed = all(record.status == FileStatus.COMPLETED and record.verification_passed for record in records)
            passed &= all(sha256(Path(record.destination_path)) == source_digest[Path(record.source_path)] for record in records)
            results.append(dict(concurrency_limit=limit, observed_concurrent_jobs=observed_jobs,
                started_at_local=started_at, finished_at_local=finished_at,
                independent_checks_complete_at_local=datetime.now().isoformat(sep=' ', timespec='milliseconds'),
                jobs=count, files_per_job=len(sources), total_mib=round(total_bytes*count/1048576, 2), seconds=round(elapsed, 3),
                effective_mib_per_second=round(total_bytes*count/1048576/elapsed, 2),
                baseline_rss_mib=round(baseline_rss, 2), peak_rss_mib=round(peak_rss, 2),
                peak_private_mib=round(peak_private, 2), cpu_seconds=round(cpu_seconds, 3),
                average_machine_cpu_percent=round(cpu_seconds/elapsed/(os.cpu_count() or 1)*100, 2),
                met_duration_target=elapsed<=float(plan['target_duration_seconds']), verified=bool(passed), samples=samples))
            (root/'RESULT.json').write_text(json.dumps(dict(plan=plan, output_root=str(output_root), runs=results), indent=2), encoding='utf-8')
        finally:
            manager.shutdown()
            while manager._active_workers:
                app.processEvents()
                time.sleep(.1)
            window.close()
            window.deleteLater()
            app.processEvents()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    for index, source in enumerate(sources, 1):
        (root/'PROGRESS.txt').write_text(f'Revalidating original sources: file {index}/{len(sources)}. Copies are finished; checking source integrity.\n', encoding='utf-8')
        if (source.stat().st_size, source.stat().st_mtime_ns) != source_before[source] or sha256(source) != source_digest[source]:
            raise RuntimeError('Source changed during the benchmark; results are not trustworthy.')
    lines = ['PERFORMANCE RESULTS (copy + full verification)', f'Source root: {source_root}', f'Test copies: {output_root}',
             'These measurements are this benchmark process, not the remote server or whole-PC resource use.',
             'Repeated runs may benefit from disk/network caches. Time target is not a forced stop.']
    for row in results:
        lines.append(f"Concurrency {row['concurrency_limit']}: {row['seconds']} s, {row['effective_mib_per_second']} MiB/s, "
                     f"peak RAM {row['peak_rss_mib']} MiB (baseline {row['baseline_rss_mib']}), "
                     f"CPU average {row['average_machine_cpu_percent']}% of machine, "
                     f"verified={row['verified']}, within target={row['met_duration_target']}")
    (root/'RESULT.txt').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    (root/'PROGRESS.txt').write_text('Finished. Read RESULT.txt and RESULT.json.\n', encoding='utf-8')


def run_cli(action: str, path: str) -> int:
    root = Path(path)
    try:
        if action == '--performance-setup':
            prepare(root)
        elif action == '--performance-configure':
            if not configure(root):
                return 2
        else:
            run(root)
        return 0
    except Exception as exc:
        root.parent.mkdir(parents=True, exist_ok=True)
        (root.parent/'PERFORMANCE_ERROR.txt').write_text(str(exc)+'\n', encoding='utf-8')
        return 1
