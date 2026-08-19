# File Transfer Automation System

An enterprise-grade desktop application that automates secure, one-way file copying between source and destination directories with active stability checks, end-to-end SHA-256 cryptographic verification, sequential queue dispatching, batch ZipCrypto archive encryption, dual-verification source cleanup, and persistent SQLite transfer history.

Designed with a Windows 11 Fluent interface for high-throughput server backups, network share synchronization, and unattended scheduled batch transfers.

---

## Key Features

- **Concurrent Multi-Job Monitoring** — Simultaneously monitors multiple source folders using OS-native filesystem events (`watchdog`) and scheduled reconciliation polling.
- **Sequential Global Transfer Queue** — Dispatches file batches across multiple jobs through a central FIFO queue to eliminate disk thrashing, lock contention, and OS thread freezes.
- **Live Real-Time Progress Bars** — Provides dynamic visual progress bars on each job overview card, streaming real-time status across compression, copy throughput (`XX MB / YY MB`), and SHA-256 hash checks.
- **Incomplete File Protection** — Actively watches file sizes and Windows locks across consecutive stability checks to guarantee incomplete or growing files are never transferred prematurely.
- **Scheduled Transfer Windows** — Supports continuous mode and scheduled transfer windows (e.g., overnight backups). Files accumulate safely throughout the day and automatically transfer in a consolidated batch at the configured window end-time.
- **Batch ZipCrypto Archive Encryption** — Automatically bundles queued files into password-protected ZIP archives compatible with native Windows Explorer (no third-party extraction tools required).
- **Isolated Compression Subprocess** — Runs archive compression in an isolated child process to ensure zero Python Global Interpreter Lock (GIL) contention and 100% smooth UI responsiveness.
- **Dual-Verified Source File Retention** — Configurable retention policy (1 to 365 days) that safely deletes source files only after confirming successful transfer and destination existence.
- **End-to-End SHA-256 Verification** — Every transferred file is verified by computing and matching full cryptographic checksums before marking as completed.
- **Safe Copy Strategy** — Writes to hidden temporary files first (`.filename.transfer_tmp`), verifies integrity, and atomically commits to the final destination path.
- **Duplicate & Modification Detection** — Recognizes already-transferred files to prevent redundant transfers while detecting modified files as new versions.
- **Persistent SQLite Database** — Stores all transfer jobs and file-level history across application restarts with automatic crash-state recovery.
- **Standalone Windows Executable (`.exe`)** — Ships with 1-click compiler (`build_exe.bat`) and portable distribution (`dist/FileTransferAutomationSystem/`) requiring zero Python installation on target machines.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                   Windows 11 Fluent UI (PySide6)                        │
│  ┌─────────────────────────┐  ┌──────────────────────────────────────┐  │
│  │ Main Dashboard          │  │ Job Workspace                        │  │
│  │ (KPIs, Multi-Job Cards, │  │ (File-Level Transfer Table, Filter,  │  │
│  │  Live Activity Feed)    │  │  Retry & Window Override Actions)    │  │
│  └────────────┬────────────┘  └──────────────────┬───────────────────┘  │
└───────────────┼──────────────────────────────────┼──────────────────────┘
                │ Qt Multi-Job Signals & Live Bus  │
┌───────────────┴──────────────────────────────────┴──────────────────────┐
│                    Transfer Manager (Central Orchestrator)              │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │ Sequential Global Transfer Queue (FIFO Batch Execution)           │  │
│  └─────────────────────────────────┬─────────────────────────────────┘  │
│                                    │ Dispatches Active Job              │
│  ┌─────────────────────────────────┴─────────────────────────────────┐  │
│  │ TransferWorker (QThread)                                          │  │
│  │  ├── Isolated Compression Worker (Subprocess: ZipCrypto)          │  │
│  │  ├── Transfer Engine (Chunked Copy + Temp Commit)                 │  │
│  │  └── Integrity Verifier (Chunked SHA-256 Hash Verification)       │  │
│  └───────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
┌────────────────────────────────────┴────────────────────────────────────┐
│ Multi-Job Controllers: Concurrent Watchdog Monitors + Safety Checkers   │
│ Persistence: SQLite Database (WAL) + JSON Configuration Service         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Requirements

- **Operating System:** Windows 10 or Windows 11 (64-bit)
- **Python Runtime:** Python 3.10+ (tested on Python 3.12 and 3.13)
- **Core Dependencies:**
  - `PySide6` >= 6.8 (Qt6 GUI Framework)
  - `PySide6-Fluent-Widgets` >= 1.11.3 (Windows 11 Fluent Design System)
  - `watchdog` >= 4.0 (OS Filesystem Event Monitoring)
  - `pyminizip` >= 0.2.6 (Standard ZipCrypto Archive Compression)
  - `Pillow` >= 10.0 (High-Resolution Icon Rendering)
  - `pyinstaller` >= 6.0 (Standalone Binary Compilation)
  - `pytest` >= 8.0 (Automated Test Suite)

---

## Quick Start & Installation

### Option 1: Running Standalone Executable (No Python Required)
1. Copy the `dist/FileTransferAutomationSystem/` folder to the target PC.
2. Double-click **`FileTransferAutomationSystem.exe`**.

### Option 2: 1-Click Environment Setup & Launch
1. Clone or extract the project repository.
2. Double-click **`setup.bat`** (automatically builds `.venv` and installs all dependencies).
3. Double-click **`run_app.bat`** to launch the application.

### Option 3: Manual Python Execution
```powershell
# Create virtual environment
python -m venv .venv
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Launch application
python app.py
```

---

## Standalone Binary Compilation

To compile a fresh Windows executable with embedded application icons and dependencies:

```powershell
# Double-click build_exe.bat or run:
.\build_exe.bat
```

The compiled binary distribution will be generated in:
```
dist/FileTransferAutomationSystem/
  ├── FileTransferAutomationSystem.exe
  └── _internal/
```

---

## Execution States Reference

| State Badge | Execution Behavior |
| :--- | :--- |
| **`TRANSFERRING`** | Active byte transfer, archive compression, or SHA-256 checksum verification in progress. |
| **`QUEUED (IN LINE)`** | Files are ready and waiting in the Sequential FIFO Queue for the active transfer to finish. |
| **`MONITORING`** | File watcher is active and listening for filesystem events. |
| **`WAITING (OUTSIDE WINDOW)`** | Files are stabilized and holding until the configured window end-time. |
| **`IDLE / STOPPED`** | Monitoring is inactive or paused by the user. |

---

## Configuration Settings

Configuration values are stored in `config/config.json` and accessible via the in-app **Settings** dialog:

| Setting | Default | Description |
| :--- | :--- | :--- |
| `stability_check_interval` | `5` | Seconds between file stability checks. |
| `required_stable_checks` | `2` | Number of consecutive unchanged checks required for `READY` status. |
| `max_retries` | `3` | Maximum retry attempts for failed transfers. |
| `retry_delay` | `10` | Delay in seconds between retry attempts. |
| `hash_algorithm` | `"sha256"` | Cryptographic hashing algorithm for verification. |
| `hash_chunk_size` | `65536` | Chunk size (bytes) for streaming file reads (64 KB). |
| `automatic_monitoring` | `true` | Auto-starts monitoring on application launch. |
| `reconciliation_interval` | `30` | Seconds between full folder reconciliation scans. |
| `overwrite_policy` | `"ask"` | Conflict resolution policy: `"ask"`, `"overwrite"`, or `"skip"`. |
| `network_drive_mode` | `false` | Optimizes polling parameters for shared network drives / UNC paths. |
| `auto_cleanup_enabled` | `false` | Enables scheduled dual-verified deletion of old source files. |
| `auto_cleanup_days` | `7` | Retention period in days before transferred source files are eligible for cleanup. |
| `batch_compression_enabled` | `true` | Consolidates queued files into a password-protected ZIP archive. |
| `zip_password` | `"password123"` | Default password for encrypted zip archives. |

---

## Automated Test Suite

The project includes an extensive test suite covering safety checks, hashing, compression, database CRUD, sequential queue dispatching, and UI progress tracking.

Run the test suite via `pytest`:
```powershell
.venv\Scripts\python.exe -m pytest tests/ -v
```

**56 automated tests passing**:
- `tests/test_compression.py`: Batch compression, window end triggering, sequential FIFO queue execution, and UI progress bar updates.
- `tests/test_file_safety.py`: Stability detection, growing file handling, lock checking, and preflight verification.
- `tests/test_integrity.py`: SHA-256 deterministic hashing, corruption detection, and chunked verification.
- `tests/test_transfer_engine.py`: Safe copy, atomic temp rename, destination creation, and conflict handling.
- `tests/test_database.py`: Job persistence, transfer records, history queries, and stale-state cleanup.
- `tests/test_transfer_manager.py`: Full pipeline integration and concurrent multi-job monitoring.

---

## License

Enterprise Internal Tool — All rights reserved.
