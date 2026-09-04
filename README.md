# File Transfer Automation System

An enterprise-grade desktop application that automates secure, one-way file copying and encrypted archiving between source directories and destination network shares. Features active Windows lock detection, stability verification, multi-job concurrent worker pool execution, WinZip AES-256 encryption via `pyzipper`, end-to-end SHA-256 cryptographic verification, dual-verification source file cleanup, persistent SQLite transfer history, and an interactive in-app Administrator Documentation system.

Designed with a high-performance Windows 11 Fluent interface optimized for high-throughput server backups, network share synchronization (SMB/UNC), and unattended scheduled batch transfers.

---

## Key Features

- **Concurrent Multi-Job Monitoring** — Simultaneously monitors unlimited source folders using OS-native filesystem events (`watchdog`) and scheduled reconciliation polling.
- **Concurrent Worker Pool & Global Queue** — Dispatches file batches across multiple jobs concurrently up to `max_concurrent_transfers` (default: 3 simultaneous jobs) through a priority FIFO queue, eliminating disk thrashing and thread starvation.
- **Parallel Window-End Directory Sweeps** — When scheduled windows arrive, directory scans run in parallel across a thread pool, queuing jobs in strict alphabetical order and launching all concurrent workers simultaneously.
- **Batch WinZip AES-256 Archive Encryption** — Automatically bundles queued files into password-protected ZIP archives using `pyzipper` with native Zip64 support for archives exceeding 4 GB (up to terabytes), with seamless fallback to `pyminizip` and standard `zipfile`.
- **Isolated Compression Subprocess** — Runs archive compression in an isolated child process to bypass Python Global Interpreter Lock (GIL) contention, keeping the user interface smooth and responsive.
- **Real-Time Mid-Compression Deletion Safeguard** — Actively polls file existence every 500ms during compression. If an active file is deleted during compression, the partial archive is destroyed, an announcement is logged, and compression automatically restarts cleanly with remaining files.
- **Live 0-Second Progress Bars** — Precalculates batch byte sizes upfront and streams real-time stdout events (`PROGRESS_BYTES:X:Y`), updating job progress bars (`XX.X MB / YY.Y MB`) from millisecond 0.
- **Incomplete File Protection & Windows Locks** — Actively tests file sizes and low-level Windows locks (`msvcrt.locking`) across consecutive stability cycles to guarantee incomplete, growing, or open files are never transferred prematurely.
- **Scheduled Transfer Windows** — Supports continuous mode and scheduled transfer windows (e.g., overnight backups). Files accumulate safely during the day and automatically consolidate at the configured window end-time.
- **Corporate Daily Backup Checklist & Executive Reporting** — Standardized daily report generator matching official TFSPH Excel templates (`templates/TFSPH_Daily_Backup_Checklist_Template.xlsx`). Automatically populates batch dates, monitored systems, aggregate file sizes, completion times, repository tags, and automated daily control checks.
- **Automated SHA-256 Integrity Verification (Col I)** — Evaluates end-to-end cryptographic checksums and marks Column I as `Passed`, `Failed`, or `Not Applicable`.
- **Linked Job Mapping & Multi-File Aggregation** — Maps development or staging jobs (`001`–`006`) to official corporate systems (`TFS42PROD`, `CSE`, etc.), aggregates file sizes across multi-file batches (`sum(r.file_size)`), and records the latest completion timestamp.
- **Windows Excel File Lock Safeguard** — Automatically catches `[Errno 13] Permission denied` when workbooks are open in Microsoft Excel, writing to `..._latest.xlsx` fallback with in-app operator notifications.
- **600ms Debounced UI Event Pipeline** — Buffers high-frequency transfer signals to keep UI smooth and prevent GUI lockups under 8-thread multi-job loads.
- **Dual-Verified Source File Retention** — Configurable retention policy (1 to 365 days) that safely deletes source files only after confirming successful transfer, destination existence, and source presence.
- **End-to-End SHA-256 Verification** — Every transferred file and archive is verified by computing and matching full cryptographic checksums before marking as completed.
- **Safe Copy Strategy** — Writes to hidden temporary files first (`.filename.transfer_tmp`), verifies integrity, and atomically commits to the final destination path via `os.replace()`.
- **SMB / UNC Network Share Resilience** — Features root share reachability checks, 50ms existence debouncing, and rate-limited GUI signal throttling (100ms per thread) to prevent SMB socket credit exhaustion.
- **Interactive In-App Administrator Manual** — Built-in multi-topic documentation viewer accessible directly from the sidebar navigation, providing instant access to technical specs, transfer protocols, archiving libraries, and administrator FAQs.
- **Persistent SQLite Database** — Stores all transfer jobs and file-level history across application restarts with automatic crash-state recovery, thread-safe write locks, and Write-Ahead Logging (WAL).
- **Standalone Windows Executable (`.exe`)** — Ships with 1-click compiler (`build_exe.bat`) and portable distribution (`dist/FileTransferAutomationSystem/`) requiring zero Python installation on target machines.

---

## Architecture Overview

```
┌───────────────────────────────────────────────────────────────────────────────────┐
│                          Windows 11 Fluent UI (PySide6)                           │
│  ┌────────────────────────┐  ┌────────────────────┐  ┌─────────────┐  ┌────────┐  │
│  │ Main Dashboard         │  │ Job Workspace      │  │ Daily Report│  │ Docs   │  │
│  │ (KPIs, Multi-Job Cards,│  │ (File Table,       │  │ (Checklist, │  │ (IT    │  │
│  │  Live Activity Feed)   │  │  Override Actions) │  │  Live Table)│  │ Manual)│  │
│  └───────────┬────────────┘  └─────────┬──────────┘  └──────┬──────┘  └───┬────┘  │
└──────────────┼─────────────────────────┼────────────────────┼─────────────┼───────┘
               │ Qt Multi-Job Signals & Debounced Event Bus (600ms)         │
┌──────────────┴─────────────────────────┴────────────────────┴─────────────┴───────┐
│                       Transfer Manager (Central Orchestrator)                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐  │
│  │ Concurrent Worker Pool & FIFO Queue (max_concurrent_transfers: 3)           │  │
│  └──────────────────────────────────────┬──────────────────────────────────────┘  │
│                                         │ Dispatches Active Jobs                  │
│  ┌──────────────────────────────────────┴──────────────────────────────────────┐  │
│  │ Parallel TransferWorker Pool (QThreads, 8 Threads Default)                  │  │
│  │  ├── Isolated Compression Worker (Subprocess: pyzipper AES-256)             │  │
│  │  ├── 500ms Mid-Compression Deletion Watcher & Auto-Restart                  │  │
│  │  ├── Transfer Engine (Throttled Chunked Copy + Atomic Rename)               │  │
│  │  └── Integrity Verifier (Chunked SHA-256 Hash Verification)                 │  │
│  └─────────────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────┬─────────────────────────────────────────┘
                                          │
┌─────────────────────────────────────────┴─────────────────────────────────────────┐
│ Report Service (openpyxl): Template Preservation, Dynamic Rows, Excel Lock Fallback│
│ Multi-Job Controllers: Watchdog Monitors + Parallel Reconciliation                │
│ Persistence: Thread-Safe SQLite WAL Database + JSON Configuration                 │
└───────────────────────────────────────────────────────────────────────────────────┘
```

---

## Technical Specifications: Transfers & Compression

### What Do We Use to Transfer Files?
1. **Batch Mode (Default):** When `batch_compression_enabled` is true, all queued files are read in 64 KB binary streaming chunks and consolidated into an encrypted `.tmp_batch_...zip` archive directly in destination staging. After SHA-256 verification, the file is atomically renamed to its timestamped archive name (`YYYY-MM-DD_HHMMSS.zip`).
2. **Direct Mode:** When batch compression is disabled, files are copied individually via Python's native binary streaming engine with configurable parallel threads (`transfer_threads: 4`). Each thread writes to a hidden temporary file (`.filename.transfer_tmp`), computes SHA-256 on the fly, and atomically commits via `os.replace()`.
3. **Throttled GUI Progress:** Progress updates from worker threads are throttled to at most once every 100ms per thread, capping GUI signal traffic and preventing Qt event queue starvation.

### What Do We Use to Zip Files & Add Passwords?
1. **Primary Library: `pyzipper` (WinZip AES-256 / AES-128):**
   - Uses `pyzipper.AESZipFile` with `encryption=pyzipper.WZ_AES` and `allowZip64=True`.
   - Provides industry-standard AES-256 encryption.
   - Natively supports Zip64 extensions for archives exceeding 4 GB (tested up to 500 GB+).
2. **Fallback Library: `pyminizip` (Standard ZipCrypto):**
   - Falls back to `pyminizip.compress_multiple()` for standard ZipCrypto password encryption.
3. **Subprocess Isolation:**
   - Archive generation runs in a separate child process via `python -m core.compression_worker <config.json>`.
   - Bypasses the Python Global Interpreter Lock (GIL), maintaining 60 FPS UI fluidity even during peak CPU compression.
4. **Password Configuration:**
   - Default archive password can be configured in `config/config.json` (`zip_password`) or modified via the in-app **Settings** dialog.

---

## Requirements

- **Operating System:** Windows 10 or Windows 11 (64-bit)
- **Python Runtime:** Python 3.10+ (tested on Python 3.12 and 3.13)
- **Core Dependencies:**
  - `PySide6` >= 6.8 (Qt6 GUI Framework)
  - `PySide6-Fluent-Widgets` >= 1.11.3 (Windows 11 Fluent Design System)
  - `watchdog` >= 4.0 (OS Filesystem Event Monitoring)
  - `pyzipper` >= 0.3.6 (WinZip AES-256 Zip64 Encryption Engine)
  - `pyminizip` >= 0.2.6 (Fallback ZipCrypto Archive Compression)
  - `openpyxl` >= 3.1.2 (Corporate Excel Checklist Processing & Template Generation)
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

## Status & Lifecycle Reference Guide

The system tracks status at two distinct levels:
1. **Job-Level Execution State** (displayed as colored badges on the **Main Dashboard job cards**)
2. **File-Level Lifecycle Status** (displayed in the **Job Workspace table**, Transfer History, and database)

### Job-Level Execution States (Main Dashboard)

| State Badge | Execution Behavior |
| :--- | :--- |
| **`TRANSFERRING`** | Active byte transfer, archive compression, or SHA-256 checksum verification in progress. |
| **`QUEUED (IN LINE)`** | Files are ready and waiting in the FIFO Queue for an available worker slot. |
| **`MONITORING`** | File watcher is active and listening for filesystem events. |
| **`WAITING (OUTSIDE WINDOW)`** | Files are stabilized and holding until the configured window end-time. |
| **`IDLE / STOPPED`** | Monitoring is inactive or paused by the user. |

### File-Level Lifecycle Statuses (Job Workspace & History)

| File Status | Description & Lifecycle Meaning |
| :--- | :--- |
| **`DETECTED`** | New file discovered in the source folder; undergoing initial Windows lock and stability verification. |
| **`PROCESSING`** | File size is being monitored across consecutive intervals, or file is actively being packaged into an archive. |
| **`WAITING_FOR_WINDOW`** | File has stabilized and passed lock checks, holding until the scheduled backup window end-time. |
| **`READY`** | File is completely written, unlocked, and staged to transfer. |
| **`QUEUED`** | File has been batched in memory and is waiting for an active worker slot. |
| **`TRANSFERRING`** | Bytes are actively copying across the network or compressing into the destination archive. |
| **`VERIFYING`** | File copy finished; calculating and comparing SHA-256 cryptographic checksums. |
| **`COMPLETED`** | File transfer succeeded 100% and verified identical to source. |
| **`FAILED`** | Transfer error occurred (network disconnect, disk full, access denied). Actionable via "Retry Failed". |
| **`SKIPPED`** | Intentionally omitted (duplicate file already transferred previously, or deleted from source before transfer). |
| **`CONFLICT`** | Destination file exists with differing size/timestamp; handled per Overwrite Policy. |

---

## Configuration Settings

Configuration values are stored in `config/config.json` and accessible via the in-app **Settings** dialog:

| Setting | Default | Description |
| :--- | :--- | :--- |
| `max_concurrent_transfers` | `3` | Maximum simultaneous job batch transfers (1 = sequential, 0 = unlimited). |
| `transfer_threads` | `8` | Parallel file transfer threads per job for direct transfers (optimal for gigabit LAN / NVMe). |
| `batch_compression_enabled` | `true` | Consolidates queued files into a password-protected ZIP archive. |
| `zip_password` | `"password123"` | Default password for encrypted zip archives. |
| `stability_check_interval` | `5` | Seconds between file stability checks. |
| `required_stable_checks` | `2` | Number of consecutive unchanged checks required for `READY` status. |
| `max_retries` | `3` | Maximum retry attempts for failed transfers. |
| `retry_delay` | `10` | Delay in seconds between retry attempts. |
| `hash_algorithm` | `"sha256"` | Cryptographic hashing algorithm for verification. |
| `hash_chunk_size` | `65536` | Chunk size (bytes) for streaming file reads (64 KB). |
| `automatic_monitoring` | `true` | Auto-starts monitoring on application launch. |
| `reconciliation_interval` | `30` | Seconds between full folder reconciliation scans. |
| `overwrite_policy` | `"ask"` | Conflict resolution policy: `"ask"`, `"overwrite"`, or `"skip"`. |
| `network_drive_mode` | `true` | Optimizes polling parameters for shared network drives / UNC paths. |
| `auto_cleanup_enabled` | `true` | Enables scheduled dual-verified deletion of old source files. |
| `auto_cleanup_days` | `7` | Retention period in days before transferred source files are eligible for cleanup. |
| `checklist_systems` | `[...]` (8 systems) | Monitored corporate systems array with job name, linked job alias, pattern, and description. |
| `report_checked_by` | `"Philip M. Bayudan"` | Default supervisor name for checklist sign-off in Section 3. |
| `report_repository_tag` | `"TFSPH-PRIMARY-REPO"` | Default backup repository identifier tag in corporate checklist. |
| `report_auto_generate` | `true` | Automatically compiles and exports daily report workbook upon transfer completion. |
| `report_operator_name` | `""` | Custom operator name override for Prepared By field (defaults to active Windows login). |

---

## Automated Test Suite

The project includes an extensive test suite covering safety checks, hashing, compression, database concurrency, multi-job worker pools, UI progress tracking, and corporate report generation.

Run the test suite via `pytest`:
```powershell
.venv\Scripts\python.exe -m pytest tests/ -v
```

**81 automated tests passing**:
- `tests/test_compression.py`: Batch compression, AES-256 encryption, mid-compression deletion handling, window end triggering, multi-job worker pool dispatching, and 0-second progress bar updates.
- `tests/test_file_safety.py`: Stability detection, growing file handling, Windows lock checking, and preflight verification.
- `tests/test_integrity.py`: SHA-256 deterministic hashing, corruption detection, and chunked verification.
- `tests/test_transfer_engine.py`: Safe copy, atomic temp rename, destination creation, and conflict handling.
- `tests/test_database.py`: Job persistence, transfer records, thread-safe concurrency, history queries, and stale-state cleanup.
- `tests/test_transfer_manager.py`: Full pipeline integration, multi-job concurrent monitoring, and SMB disconnect resilience.
- `tests/test_report.py`: Checklist data generation, corporate Excel template cloning, dynamic row expansion (8+ systems), multi-file size aggregation, linked job mapping, SHA-256 integrity mapping, and Excel lock fallback.

---

## License

Enterprise Internal Tool — All rights reserved.
