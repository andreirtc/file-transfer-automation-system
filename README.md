# File Transfer Automation System

Windows desktop tool for batch operators to copy backup files from configured source folders to destination folders, track results in SQLite, and generate the TFSPH daily Excel checklist. It copies files; it does not create database backups or prove that a database restore will succeed.

## Start here

- [Operator guide](docs/OPERATOR_GUIDE.md): daily workflow, batch dates, buttons and recovery.
- [Demo and acceptance checklist](docs/DEMO_CHECKLIST.md): safe practice steps and company sign-off.
- [IT handover](docs/IT_HANDOVER.md): deployment, architecture, settings, persistence and support.
- [Audit findings](docs/AUDIT_REPORT.md): changes, test evidence and remaining acceptance work.

The same guides are available in the application's **Guide** sidebar page. Keep the `docs` folder with the application distribution.

For hands-on practice, double-click **CREATE_DEMO.bat**. It creates a separate portable demo app with preconfigured jobs and timestamped crossover samples. The generated walkthrough and menu cover selected-batch transfer, duplicate protection, conflicts, growing files, scheduling, ZIP and hash verification. Your installed job database and configuration are not copied into the demo.

For large files, network paths and concurrent jobs, use **TEST_PERFORMANCE.bat** and the [performance guide](docs/PERFORMANCE_GUIDE.md). The setup form accepts existing files or recursive folders, separate destinations and start/completion targets. This desktop app must run on the server itself for server-based 24/7 operation; opening its shared EXE on a laptop runs it on that laptop. Keep SQLite local to the running host, not shared among laptop processes.

## Run from source

Windows 10/11, 64-bit Python 3.10 or newer. Use the included virtual environment for this checkout, or run `setup.bat` to create one and install `requirements.txt`. Then run `run_app.bat` or:

```powershell
.\.venv\Scripts\python.exe app.py
```

For automated checks in restricted environments:

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp=.test-temp
```

Use a disposable `--basetemp` directory: pytest clears it. Tests use temporary job databases, folders and report output; the test fixture redirects generated Excel workbooks away from the working application reports.

## Portable Windows release

Run `build_exe.bat`. Copy the entire `dist/FileTransferAutomationSystem` folder to a writable location on the company PC. Keep `_internal`, `templates`, `docs`, and the executable together. Python is bundled. Existing releases must be rebuilt after source changes. The build does not copy development job history or custom configuration into a new release.

Read [INSTALLATION_GUIDE.txt](INSTALLATION_GUIDE.txt) and the IT handover before production setup. Back up the existing database/configuration before replacing a release.

## Main behavior

- Continuous monitoring discovers files and checks unchanged size and modification time before transfer.
- Scheduled jobs collect files and request transfer at the configured **window end minute**, on enabled days. Files still changing wait for safety checks.
- **Transfer Batch Files** selects files by their source modification timestamp's operational batch date. **Sync All Dates** requests all untransferred source files for that job.
- Manual requests bypass the schedule; file stability checks still apply.
- Direct copying preserves relative subfolders and writes a temporary destination file. It verifies the copy and uses `os.replace` to commit it.
- Direct verification uses full SHA-256 up to 2 GB; with smart verification enabled, larger files use equal-size plus head/middle/tail block hashes. Turn smart verification off for full-file hashing.
- ZIP mode streams files into a ZIP64 archive. A configured password uses WinZip AES encryption. Encryption failure fails the transfer. Each member is read back and compared with a full source SHA-256 before completion.
- Source cleanup is optional and disabled by default. It requires matching source metadata, a recorded verified result, and matching full source/destination hashes; uncertain candidates are retained.
- History survives application restarts. Duplicate detection matches job, path, size and modification timestamp; it does not continually re-validate old destination copies.
- Reports summarize recorded transfer results. Operators still check actual backup naming, expected sizes, restoration requirements and escalation.

## Project map

| Location | Responsibility |
| --- | --- |
| `app.py` | Startup and frozen executable compression-worker entry point |
| `gui/main_window.py` | Navigation, actions, Qt signal handling, lifecycle |
| `gui/main_dashboard.py` | Job cards and activity feed |
| `gui/dashboard.py`, `gui/transfer_table.py` | Workspace, batch picker, filters, file statuses |
| `gui/job_dialog.py`, `gui/dialogs.py` | Job validation, settings, conflict/history/log dialogs |
| `gui/report_page.py`, `gui/docs_page.py` | Report and handover guide screens |
| `core/transfer_manager.py` | Job controllers, scheduling, queue, workers, retries and cleanup |
| `core/transfer_engine.py`, `core/integrity.py` | Direct copying, destination policy and verification |
| `core/file_monitor.py`, `core/file_safety.py` | Watchdog/reconciliation and stability checks |
| `core/compression_worker.py` | Isolated archive subprocess |
| `core/models.py` | Job, record, result and status models |
| `services/database_service.py` | SQLite schema, migrations, history and statistics |
| `services/configuration_service.py`, `services/logging_service.py` | JSON configuration and rotating logs |
| `services/report_service.py` | Excel template output and checklist aggregation |
| `tests/` | Automated core, reporting, batch and UI regressions |
| `demo/`, `generate_test_files.py` | Development sample file utilities |

## Operating limits

The application must be running and the PC awake for monitoring and scheduled triggers. It is a desktop application, not a Windows service. A missed end minute is not automatically replayed: use the batch date request after verifying the source backup is complete. Times use the workstation's local clock. Windows share permissions, disk capacity, backup production and occasional operational review remain the company's responsibility.

A green transfer result confirms the recorded copy verification; it does not certify a restore or future media health. No test suite can guarantee every production network failure or maintenance-free operation. Complete the acceptance checklist on the actual company environment before unattended use.


The portable release keeps practice launchers in **TestTools/**. Concurrency now runs alphabetical groups: with a limit of three, jobs 5/6/7 finish their group before 8/9 start. File threads within each job are a separate setting. See the operator guide for waiting-file behavior.
