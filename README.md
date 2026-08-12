# File Transfer Automation System

A desktop application that automates one-way file copying between a source folder and a destination folder, with robust incomplete-file detection, integrity verification, and persistent transfer history.

**This is a local prototype** designed to demonstrate that automated file transfer between source and destination locations is feasible while preventing unsafe transfers of files that are still being written.

---

## Features

- **Automatic file detection** — Monitors source folders using OS-native filesystem events (watchdog)
- **Incomplete file protection** — Never copies files that are still being downloaded, written, or modified
- **SHA-256 integrity verification** — Every transferred file is verified by comparing cryptographic hashes
- **Safe copy strategy** — Copies to a temporary file first, verifies, then renames to the final filename
- **Duplicate detection** — Already-transferred files are not copied again; modified files are recognized as new versions
- **Destination conflict handling** — Detects when a destination file differs from the source and prompts the user
- **Persistent transfer history** — SQLite database survives application restarts
- **Manual & automatic sync** — Start/stop monitoring or trigger manual synchronization
- **Retry mechanism** — Failed transfers are retried with configurable attempts and delay
- **Responsive GUI** — Background workers keep the interface responsive during large file transfers
- **Detailed logging** — Separate log files for application events, transfers, and errors

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    PySide6 GUI                          │
│  ┌──────────┐ ┌──────────────┐ ┌──────────────────────┐│
│  │ Dashboard │ │ Transfer     │ │ Dialogs              ││
│  │ (stats,   │ │ Table        │ │ (conflict, warnings, ││
│  │  controls)│ │ (file list)  │ │  settings, logs)     ││
│  └─────┬─────┘ └──────┬───────┘ └──────────┬───────────┘│
└────────┼──────────────┼────────────────────┼────────────┘
         │              │                    │
         └──────────────┼────────────────────┘
                        │  Qt Signals
         ┌──────────────┴───────────────┐
         │      Transfer Manager        │
         │  (orchestrator / coordinator) │
         └──┬───────┬────────┬──────┬───┘
            │       │        │      │
   ┌────────┴┐ ┌───┴─────┐ ┌┴─────┐┌┴──────────┐
   │File     │ │File     │ │Trans-││Integrity  │
   │Monitor  │ │Safety   │ │fer   ││Verifier   │
   │(watchdog│ │Checker  │ │Engine││(SHA-256)  │
   │+recon)  │ │(stable?)│ │(copy)││           │
   └─────────┘ └─────────┘ └──────┘└───────────┘
                        │
         ┌──────────────┴───────────────┐
         │         Services             │
         │  ┌──────────┐ ┌───────────┐  │
         │  │ Database  │ │ Config    │  │
         │  │ (SQLite)  │ │ (JSON)    │  │
         │  └──────────┘ └───────────┘  │
         └──────────────────────────────┘
```

### Module Responsibilities

| Module | Responsibility |
|--------|---------------|
| `core/transfer_manager.py` | Central orchestrator — coordinates all components |
| `core/file_monitor.py` | Watches source folder for new/changed files |
| `core/file_safety.py` | Determines if files are safe to copy (not still being written) |
| `core/transfer_engine.py` | Performs safe copy with temp file + atomic rename |
| `core/integrity.py` | SHA-256 hashing and post-transfer verification |
| `core/models.py` | Data models, enums, and type definitions |
| `services/database_service.py` | SQLite persistence for jobs and transfer history |
| `services/configuration_service.py` | JSON configuration loading and saving |
| `services/logging_service.py` | Structured logging with rotating file handlers |
| `gui/main_window.py` | Main application window with menu, toolbar, status bar |
| `gui/dashboard.py` | Dashboard with stats cards, warning banner, transfer table |
| `gui/transfer_table.py` | Sortable/filterable file transfer status table |
| `gui/job_dialog.py` | Create/edit transfer job dialog |
| `gui/dialogs.py` | Processing warning, conflict, settings, log viewer dialogs |

### Design Decisions

1. **Copy, never move** — Source files are always preserved. The system never deletes source files.
2. **Safe copy strategy** — Files are copied to `.filename.transfer_tmp` first, then renamed after verification. This prevents partial files from appearing under the real filename.
3. **Connection-per-call database** — Each database method opens and closes its own SQLite connection, making it safe to call from any thread without external locking.
4. **Single-threaded transfer queue** — Files are transferred one at a time to avoid race conditions. The architecture supports future parallel transfers.
5. **Conflicts pause in automatic mode** — When auto-monitoring detects a destination conflict, the file is flagged in the dashboard rather than blocking with a modal dialog.

---

## Requirements

- **Python 3.12+** (tested on 3.13)
- **Windows** (tested on Windows 10/11)
- **PySide6** >= 6.8 (Qt for Python)
- **watchdog** >= 4.0 (filesystem monitoring)
- **pytest** >= 8.0 (testing, development only)

---

## Installation

1. **Clone or download** the project:
   ```
   cd C:\Users\<your_user>\Documents
   git clone <repository_url> FileTransferAutomationSystem
   cd FileTransferAutomationSystem
   ```

2. **Create a virtual environment**:
   ```
   python -m venv .venv
   ```

3. **Activate the virtual environment**:
   ```
   .venv\Scripts\activate
   ```

4. **Install dependencies**:
   ```
   pip install -r requirements.txt
   ```

---

## Running the Application

```
.venv\Scripts\python.exe app.py
```

Or with the venv activated:
```
python app.py
```

The application will:
1. Initialize logging (creates `logs/` directory)
2. Load configuration from `config/config.json`
3. Initialize the SQLite database (creates `database/transfer_history.db`)
4. Open the main window
5. Load any previously configured transfer job
6. Auto-start monitoring if configured

---

## Configuring a Transfer Job

1. Click **"+ Add Job"** in the toolbar (or **Jobs → Add Transfer Job**)
2. Enter a **Job Name** (e.g., "Local Test Transfer")
3. Click **Browse** to select the **Source Folder**
4. Click **Browse** to select the **Destination Folder**
5. Check **Enabled** and **Automatic Monitoring** as desired
6. Click **Save**

Example:
```
Job Name:    Local Test Transfer
Source:      C:\Users\<user>\Documents\FileTransferAutomationSystem\demo\source
Destination: C:\Users\<user>\Documents\FileTransferAutomationSystem\demo\destination
```

---

## Automatic Monitoring

When monitoring is active:

1. The system watches the source folder for new files
2. New files are detected and enter the safety check pipeline
3. Files are checked for size stability, modification time, and accessibility
4. Once confirmed safe, files are automatically copied and verified
5. Transfer history is recorded in the database

**Start monitoring**: Click **"▶ Start Monitoring"**
**Stop monitoring**: Click **"■ Stop Monitoring"**

The periodic reconciliation scan runs every 30 seconds (configurable) to catch any files that were missed by filesystem events.

---

## Manual Synchronization

Click **"🔄 SYNC NOW"** to perform a manual sync:

1. The system scans the source folder
2. Identifies new/changed files
3. Checks file safety
4. If any files are still being processed, shows a warning dialog:
   - **Transfer Ready Files** — Copy only the safe files
   - **Wait for All Files** — Don't copy anything yet
   - **Cancel** — Cancel the sync operation
5. Ready files are transferred and verified
6. Results are shown in the dashboard

---

## File Safety Mechanism

The system uses a multi-check approach to ensure files are safe to copy:

### 1. Size Stability
The file size is recorded and checked at intervals (default: 5 seconds). The file must remain unchanged for a configurable number of consecutive checks (default: 2).

### 2. Modification Time
The file's last-modified timestamp is tracked. Changes reset the stability counter.

### 3. File Accessibility
The system attempts to open the file for reading. Files locked by other processes (e.g., a browser downloading) will fail this check.

### 4. Final Pre-Copy Check
Immediately before copying begins, the file is re-checked. This prevents copying a file that changed between becoming "READY" and the actual copy operation.

### File States

```
DETECTED     → File found in source folder
PROCESSING   → File is still being written/modified
READY        → File is stable and safe to copy
QUEUED       → File is waiting in the transfer queue
TRANSFERRING → File is being copied
VERIFYING    → Copy is being verified (SHA-256)
COMPLETED    → Transfer successful, verified
FAILED       → Transfer failed (will retry)
SKIPPED      → File skipped (duplicate or user choice)
CONFLICT     → Destination file differs from source
```

---

## Integrity Verification

After every file copy:

1. ✅ Confirm the destination file exists
2. ✅ Compare file sizes (source vs destination)
3. ✅ Calculate SHA-256 hash of both files
4. ✅ Compare hashes

Files are read in 64 KB chunks so even multi-gigabyte files never load entirely into RAM.

Only when all checks pass is the transfer marked as **COMPLETED**.

---

## Error Handling

The system gracefully handles:

- Source folder doesn't exist → Creates it or warns
- Destination folder doesn't exist → Creates it automatically
- Permission denied → Marks as FAILED with message
- File becomes unavailable during transfer → Cleans up temp file
- Disk full → Marks as FAILED, cleans up temp file
- Hash verification failure → Removes partial copy
- Application crash → Stale states are cleaned up on restart
- Filesystem watcher failure → Reconciliation scan continues working

One failed file never crashes the entire application.

### Retry Mechanism

Failed transfers are automatically retried:
- Default: 3 attempts with 10-second delay
- Configurable in Settings
- After max retries, the file stays as FAILED for manual review

---

## Database

Transfer history is stored in `database/transfer_history.db` (SQLite).

**Tables:**
- `transfer_jobs` — Job configurations (name, source, destination, enabled)
- `transfer_records` — Individual file transfer history (status, hashes, timestamps, errors)

**Persistence:** Data survives application restarts. Previously transferred files are recognized and not re-copied.

**Modified file detection:** If a source file changes (different size or modification time), it is recognized as a new version and transferred again.

---

## Testing

### Run All Tests
```
.venv\Scripts\python.exe -m pytest tests/ -v
```

### Test Coverage

| Test File | What It Tests |
|-----------|--------------|
| `test_file_safety.py` | File stability detection, growing files, accessibility |
| `test_integrity.py` | SHA-256 hashing, file comparison, transfer verification |
| `test_transfer_engine.py` | Safe copy, source preservation, conflict detection |
| `test_database.py` | CRUD, duplicate detection, persistence, statistics |
| `test_transfer_manager.py` | Full pipeline integration, error handling |

**48 automated tests** covering file safety, integrity, transfers, database, and integration.

---

## Demo Procedure

### Setup

Run the demo script:
```
.venv\Scripts\python.exe demo/create_test_files.py
```

Choose option **1** to create demo directories.

### Test 1 — Normal File Transfer

1. Start the application: `.venv\Scripts\python.exe app.py`
2. Create a job pointing to `demo/source` and `demo/destination`
3. Start monitoring
4. In the demo script, choose option **2** (create small file)
5. Watch the dashboard: `DETECTED → READY → TRANSFERRING → VERIFYING → COMPLETED`

### Test 2 — Large/In-Progress File

1. In a separate terminal, run the demo script and choose option **4** (simulate growing file)
2. The application should show the file as **PROCESSING**
3. After the script finishes writing (~20 seconds), the file should become **READY**
4. If auto-monitoring is on, it will be transferred automatically

### Test 3 — Manual Sync While Processing

1. Have both a ready file and a growing file in source
2. Click **SYNC NOW**
3. The warning dialog should appear with 3 options
4. Choose **Transfer Ready Files** — only the ready file transfers

### Test 4 — Duplicate Detection

1. Run sync again after a successful transfer
2. Already-transferred files should be recognized
3. No unnecessary copies are made

### Test 5 — Integrity / Conflict

1. Modify a file in `demo/destination` manually (e.g., edit it in Notepad)
2. Run sync
3. The **Destination Conflict** dialog should appear
4. Choose Overwrite, Skip, or Cancel

---

## Configuration

Configuration is stored in `config/config.json`:

| Setting | Default | Description |
|---------|---------|-------------|
| `stability_check_interval` | 5 | Seconds between file stability checks |
| `required_stable_checks` | 2 | Consecutive stable checks required for READY |
| `max_retries` | 3 | Maximum retry attempts for failed transfers |
| `retry_delay` | 10 | Seconds between retry attempts |
| `hash_algorithm` | "sha256" | Hash algorithm for integrity verification |
| `hash_chunk_size` | 65536 | Bytes per chunk when hashing (64 KB) |
| `automatic_monitoring` | true | Auto-start monitoring on launch |
| `reconciliation_interval` | 30 | Seconds between full folder scans |
| `overwrite_policy` | "ask" | How to handle conflicts: "ask", "overwrite", "skip" |

Settings can also be edited via **View → Settings** in the application.

---

## Future Network-Drive Deployment

The system is designed so that local paths can be replaced by network paths:

```
Current (local):
  Source:      C:\Users\User\Downloads\TestSource
  Destination: C:\Users\User\Desktop\TestDestination

Future (network):
  Source:      \\SERVER\SharedFolder\Source
  Destination: \\SERVER\SharedFolder\Destination
```

The transfer engine works with generic `pathlib.Path` objects and does not assume any specific drive or path format. The configuration stores paths as strings that can point to any accessible location.

**Considerations for network deployment:**
- Watchdog may have limitations with UNC paths on some Windows versions
- The reconciliation scan provides a reliable fallback
- Network latency may require increasing stability check intervals
- Authentication/credentials are not handled in this prototype

---

## Known Limitations

1. **Single job focus** — The GUI focuses on one job at a time, though the database supports multiple jobs
2. **No parallel transfers** — Files are transferred one at a time (safe default; architecture supports future parallel transfers)
3. **No recursive folder monitoring** — Only files directly in the source folder are monitored (subdirectories are ignored)
4. **File locking detection** — Windows file locking behavior varies between applications; the accessibility check catches most cases but not all
5. **No network authentication** — The prototype does not handle network drive credentials
6. **No drag-and-drop** — Files must be placed in the source folder through normal file operations
7. **Hash performance** — SHA-256 verification on very large files (10+ GB) may take noticeable time
8. **Watchdog on network drives** — OS-level filesystem events may not fire reliably on network shares; the reconciliation scan mitigates this
