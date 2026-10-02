# IT handover

For performance measurements, timed requests, network tests and the supported server deployment model, read [Performance and central server operation](PERFORMANCE_GUIDE.md). The application is a desktop process, not a central multi-client service. Run one instance on the server with its SQLite database on local disk; remotely access that running session. Do not run shared-folder copies from multiple laptops against the same database.

## Deployment and first configuration

Deploy the entire release folder to a writable directory such as `C:\Apps\FileTransferAutomationSystem`. The executable stores `config`, `database`, `logs` and `reports` beside itself. Avoid protected Program Files locations unless IT grants appropriate permissions. No Python installation is needed for the portable release.

The user needs source read access and destination create/write/replace access. Cleanup, if approved, also needs source delete access. Prefer UNC paths to mapped drives. Validate share access using the same Windows account/session that runs the app. Configure logon startup for this GUI application and keep the PC awake; do not assume an unattended service exists.

On first launch create jobs, verify unique names and paths, select transfer mode and verification policy, configure batch cycle and per-job schedules, and map the corporate checklist. Use an approved ZIP password; the development default is not a company secret. Passwords are stored as plaintext configuration: restrict access to the application folder. A blank password intentionally creates an unencrypted ZIP. ZIP mode creates ZIP archives; RAR in a checklist is a configured label, not conversion into RAR.

Default stability is 5 seconds between checks, 2 unchanged checks. New files first enter tracking, so normal readiness takes roughly 10–15 seconds, plus scan/queue delays. Default job concurrency is 1 and file threads per job are 4. Do not enable unlimited concurrency until tested on actual disks/shares. A shared destination across different jobs may create filename collisions; avoid overlapping destinations.

## Architecture and lifecycle

`app.py` sets logging, config, database, Qt and the main window. Each `JobController` owns a monitor, safety checker and transfer engine. Watchdog events plus reconciliation find files. Qt timers request safety checks, retries and schedule evaluation. The manager queues batches alphabetically by job name and dispatches QThread workers up to the configured job concurrency. Direct workers copy files in parallel; ZIP workers invoke an isolated subprocess. Signals return status updates to Qt. Workspace updates are debounced. History is SQLite with connection-per-call writes and a lock; the schema adds batch-date fields for older databases.

Manual scan completion is delivered via a Qt signal, not a timer in a Python thread. Batch requests do not requeue live queued/copying/verifying records. Source-relative subfolders are retained in direct mode. Temporary files are verified before `os.replace` commits them. Conflict policy is Ask, Overwrite or Skip. Ask requires an operator; approved overwrite is scoped to the chosen record.

ZIP encryption errors fail rather than silently producing unencrypted output. Archive members are decrypted/read back and fully hashed against sources, and an archive hash is recorded. This increases archive verification I/O; large backup performance must be measured. Source deletions during compression can restart with remaining files. Empty/missing/failed archives must be investigated through logs.

Cleanup is opt-in, defaults off, and checks recorded verification, source size/mtime, full source hash and full destination hash. It conservatively retains legacy/sampled records whose full hashes cannot be established. Do not assume every eligible-looking old file will be removed. Destination hash checks confirm recorded archive bytes; recovery keys/passwords must also be retained.

## Files to preserve and backup

| Path beside executable | Purpose |
| --- | --- |
| `database/transfer_history.db` | Jobs AND transfer records, including duplicate signatures |
| `config/config.json` | Global transfer/report settings and checklist mappings; NOT job definitions |
| `templates/TFSPH_Daily_Backup_Checklist_Template.xlsx` | Master corporate report workbook |
| `reports/` | Generated daily workbooks |
| `logs/` | Rotating application, transfer and error logs |
| `docs/` | In-app and standalone handover documents |

Stop the app and wait for active workers before copying the SQLite database; include any remaining `-wal`/`-shm` companions in a complete cold backup. Keep database/config/report backups outside the release folder. Do not send config publicly because it can contain passwords and internal paths.

Upgrade: close the old app; back up data; replace executable, `_internal`, templates and docs with the approved tested release; preserve the live database, config, reports and logs; restart and complete a small transfer check. Do not overwrite the production config with a developer's copy. Reverting binaries after a schema change needs a verified compatible database backup.

## Settings changes

Stability checker instances and several timer/monitor settings are created when controllers start. Stop work and restart the application after changing stability, reconciliation, retry, network or concurrency settings to get a consistent configuration. Cycle labels refresh on settings save, but existing persisted batch tags remain historical tags. Do not change operational hours mid-batch.

JSON configuration can be edited with the app closed. Invalid JSON falls back to defaults and is logged. UI validates operational hours as HH:MM; malformed hand-edited hours use default cycle calculations. Keep a known-good config backup.

## Scheduling and operational support

The trigger checks the end minute while the app runs. No persistent catch-up scheduler or service is included. Enabled weekdays are evaluated on the end trigger's calendar day. Use batch sync to recover missed runs. App close waits for active work; direct copy/verification can take time after a cancellation request. Do not force-kill it except under IT incident procedures.

File access checks test readability and unchanged metadata; they cannot guarantee that an external backup process has logically finished or that data is restorable. Coordinate producer completion, retention, restore rehearsals and backup monitoring with existing company procedures. There is no built-in alert delivery to email/chat, centralized authentication, service supervision or automatic upgrade mechanism.

Reports are a snapshot of application history plus some filesystem checks. Manual naming/size/escalation checks remain Pending until reviewed outside the app. Repository capacity currently samples an accessible configured destination; confirm capacity on every actual target. Checklist mapping and default supervisor metadata need explicit company validation.

Assign an IT owner for share availability, storage capacity, workstation startup/sleep policy, passwords, periodic restore tests and release backups. The tool reduces repeated operator work; it cannot eliminate operational support or promise zero maintenance.

## Troubleshooting

| Symptom | Check / recover |
| --- | --- |
| No files for selected batch | Last-modified time, overnight cutoff, selected job, table/status filters and completed history |
| PROCESSING stays visible | Producer still writing, readable permissions, stability interval and changing mtime |
| Queue stays waiting | Active workers, concurrency limit, paused job and destination latency |
| FAILED | Error column, `logs/transfer.log` and `logs/error.log`; share access, disk free space, file locks |
| CONFLICT | Approved overwrite policy and operator decision; do not erase history to bypass it |
| Report Pending | Batch date, checklist linked job, incomplete/unverified records and manually reviewed checks |
| Report save fails | Close Excel; confirm reports directory permissions and `_latest` fallback availability |
| Duplicate not recopied | History matches size/mtime; restoring a lost destination requires approved history reset/recovery |
| Application will not start | Complete `_internal` directory, writable install location, Windows architecture, logs and endpoint protection |

## Developer continuation

Run the README test command. Add regression tests for changed safety/queue/report behavior. Tests use temporary storage; do not point them at real source/destination folders. Build using `build_exe.bat` only after tests pass. Test both direct and encrypted ZIP transfers on the packaged release. See README project map and the audit report for coverage limits. Legacy `gui/help_dialog.py` is retained but the main window routes help to the consolidated Guide page.

Build troubleshooting: use the canonical PyInstaller spec through build_exe.bat. The spec excludes foreign ICU binaries found on PATH, because Qt expects the Windows native ICU ABI. Do not manually re-add a Poppler/Conda ICU DLL to the release. Validate the final executable on the company Windows version.

For reproducible developer setup, requirements-tested.txt records exact package versions from the validated Windows/Python 3.13 environment. Install those into a fresh virtual environment and rerun tests. Other Python/Windows versions still require validation.


## Alphabetical concurrent groups

Jobs run in case-insensitive alphabetical groups. With jobs 5, 6, 7, 8 and 9 and Max Concurrent Jobs set to 3, the first group is 5/6/7. Jobs 8/9 wait until that group finishes. Slower initial scans or stability checks cannot let later jobs overtake it. Within a group, completion order depends on file sizes and device speed. An earlier growing or locked file can hold later groups; stop that job if the operator chooses to release its place. Disabled jobs and future scheduled windows do not reserve places. New work arriving after a group starts waits for a later group; running transfers are not preempted.

Max Concurrent Jobs controls how many jobs run together. Transfer Threads controls files inside each job: 1 means one file at a time; a larger value allows parallel direct copies. A batch is the group of files submitted by one job, not a single giant write. Robocopy-style describes streaming and safe copying; the app uses Python workers, not robocopy.exe.

Practice launchers are grouped in **TestTools** beside the portable executable: CREATE_DEMO.bat, TEST_PERFORMANCE.bat and OPEN_FINAL_TEST.bat. Existing DemoLab sessions retain their original paths so saved history and source/destination links continue to work.
