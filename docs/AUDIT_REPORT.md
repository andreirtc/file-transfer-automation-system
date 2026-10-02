# Audit and handover findings

Reviewed October 2, 2026. This audit covers the local Python source, job/date/queue workflow, operator UI wiring, SQLite persistence, report generation, deployment scripts and documentation. Production acceptance on the company's actual shares and a database restore remain required.

## Verified issues corrected

| Finding | Correction |
| --- | --- |
| Duplicate manager sync definition hid the batch-aware API | One public sync method retains target batch support |
| Background sync used a thread-local Qt timer with no event loop | Qt signal delivers success/error to the main thread and clears busy state |
| Manual and scheduled requests promoted changing files directly to ready | Requests retain stability checks; schedule override does not override file safety |
| Repeated scans could reset in-flight file states | Live states are preserved; active worker records excluded from requeue |
| Initial scan raced with Stop Monitoring | Scan captures/validates its monitor instance |
| Direct nested files were flattened to one destination basename | Preserve source-relative destination paths |
| Configured destination overwrite policy was not applied in direct workers | Ask/Skip/Overwrite enforced, including parallel-result conflict propagation |
| Destination replacement deleted the previous file before commit | Atomic replace retains old destination on failure |
| Transfer failure could retain the preflight success flag | Only completed verified operations report transfer success |
| Archive encryption fallback could produce unencrypted output | Password requests require AES and fail on encryption errors |
| Archives were marked verified without member/source comparison | Read and hash each member against source; store source/archive hashes |
| Archive errors could escape without persisted failure state | Persist failure and notify operators; cleanup temporary archive |
| Historical ZIP/report naming used the current calendar date | Single-batch archives and auto reports use recorded batch dates |
| Cleanup ignored the enable switch and could delete changed sources | Require opt-in, verified history, matching metadata and full hashes |
| Job dialog validation mutated the live job before acceptance | Edit a copy until Save is accepted |
| Invalid cycle hours could crash range labels | Validate settings hours; malformed stored hours use default range |
| Legacy table filter ignored custom cycle configuration | Resolve legacy display tags using current cycle settings |
| Sidebar labels and one-row batch controls were crowded | Short readable navigation labels and two-row batch controls |
| Generic Sync Now concealed multi-date scope | Rename to Sync All Dates and add scope tooltip |
| History reset had no confirmation | Explain duplicate-tracking loss and confirm reset; guard active work |
| Close could destroy a live QThread | Wait for scans and workers before closing |
| Error log did not collect app/transfer warnings | Root warning/error handler writes the advertised error log |
| Reports overstated automated checks | Unknown verification stays pending; naming, expected size and escalation require review |
| Documentation overclaimed guarantees and misstated job storage | Consolidated operator/demo/IT guides, same source loaded in-app |
| Frozen Qt launch failed when a foreign Poppler ICU DLL was selected from PATH | Canonical spec excludes incompatible foreign ICU binaries; compression startup does not initialize GUI |
| Build/setup scripts could announce success after failure | Check exit status; bundle guides; omit developer config from new releases |

## Test evidence

The original suite passed 97 tests in the local virtual environment. Added handover regressions exercise actual batch button handling through Qt, repeat requests, errors, midnight tagging, live-state protection, growing-file safety, nested paths, destination policy, atomic replacement failure, cleanup retention, encryption failure, historical reporting, legacy filters, job cancellation isolation and guide loading.

Final suite results and release checks are recorded below after execution. Screenshots are generated with Qt widget rendering using an isolated configuration/database; production jobs are not used for those UI checks.

## Remaining acceptance work and limits

- Test the final executable on the company Windows account and actual UNC shares, including disk full, disconnect/reconnect, file locks, large representative backups and Excel locks.
- Complete the demo checklist; not every physical mouse/menu/native file-picker interaction or Windows scaling combination is automated.
- Scheduling runs only while the desktop app is active and awake. Missed end minutes need manual recovery. Enabled weekdays refer to the end-trigger calendar day.
- Source timestamp batch tagging does not inspect backup filenames/content. Afternoon-gap files use the current date; the nominal cycle label is not an exact inclusion interval.
- File readability/stability is a heuristic, not proof of producer completion. A restore rehearsal remains mandatory under company procedures.
- Smart large-file direct verification samples blocks. Full-file hashes require disabling smart verification. Source cleanup conservatively retains records without full matching hashes.
- Direct cancellation may wait for a current file copy/verification to finish. Do not force-close the process during work.
- Different jobs should not write overlapping destination paths. Concurrency and verification I/O require performance validation on real infrastructure.
- History is duplicate tracking, not continuous monitoring of destination health. Loss/removal of old destinations requires approved recovery.
- Reports are recorded-result snapshots, not supervisor approval or automated incident escalation. Capacity checks do not replace checking every destination.
- ZIP passwords reside in JSON; default/example credentials must be replaced and folder permissions restricted.
- Assign an IT owner for storage, network, startup policy, restore tests and release backups. Maintenance-free or error-free production operation cannot be guaranteed.

## Executed validation

- Full automated suite: **122 passed**, no warnings, in 22.34 seconds. Command: `.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp=.audit_handover_final --junitxml=.audit/test-results.xml`.
- Python compilation checks and `git diff --check` passed (Git reports normal LF/CRLF conversion notices).
- Qt rendered Dashboard, Workspace, Report and Guide using isolated test data. Inspected standard and smaller 1024-pixel logical width layouts at the current Windows scaling; dashboard action rows and sidebar labels were corrected after this inspection. Tables/long reports retain scrolling.
- Tested runtime: Python 3.13.14 (64-bit), PySide6 6.11.1, Fluent Widgets 1.11.3, watchdog 6.0.0, pyzipper 0.4.0, pyminizip 0.2.6, openpyxl 3.1.5, pytest 9.1.1, PyInstaller 6.22.2.
- The verified release from `.audit/release/FileTransferAutomationSystem` now also replaces the executable and runtime in `dist/FileTransferAutomationSystem`. Existing configuration, database and logs are preserved. Complete the target-environment checklist before production use.

The first default-temp pytest invocation encountered sandbox folder-permission errors. Workspace-local disposable `--basetemp` resolved this environment issue. Several original tests were updated to establish actual file stability before asserting immediate dispatch; the application now deliberately prevents those earlier bypasses.

After the dashboard layout changes, the 52 compression/UI workflow tests also passed. Final report columns use readable adjustable widths, horizontal scrolling and full-text tooltips.

## Portable executable checks

The corrected final PyInstaller build completed successfully. Its frozen `--compression-worker` entry point exited with code 0, created an AES-encrypted archive, and the decrypted member matched the original test payload. The actual windowed executable reached `Application window displayed` in its application log using a fresh empty job database. The hidden startup smoke process had no visible main-window handle, so it was terminated after startup with an empty job database and no transfers. Graceful packaged close remains an acceptance-checklist item. This is a startup/worker smoke test; production button-by-button acceptance on the company PC remains in the demo checklist.

The earlier frozen check exposed a real dependency packaging error: PyInstaller selected Poppler's `icuuc.dll` from the host PATH, which lacks the unversioned exports expected by Qt. The spec now excludes that foreign ICU and its data DLL, and build_exe.bat uses the same spec. No system installation or production configuration was changed.

The distributable ZIP omits startup-test config/database/log files. The `dist` executable, runtime and guides are updated to the verified release; its previous executable/runtime are backed up under `.audit/dist-backup-20261002`. Configuration/database hashes were checked before and after replacement. The updated `dist` compression worker also passed an AES archive round-trip check. Company acceptance is still required for actual operating conditions.

Report tests originally used the project reports directory; the shared fixture now redirects test workbooks into each test temporary directory. Earlier audit runs could have written dated sample workbooks there. Production job/configuration files were not used for UI/transfer regression tests.

Final run after report-output isolation: 122 passed with no warnings in 22.34 seconds. Exact developer dependencies are recorded in requirements-tested.txt.

## Ready-made demo lab

The portable executable now supports the CREATE_DEMO.bat launcher. Each invocation creates an independent application copy, clean configuration/database, five jobs and local synthetic samples. No production settings or histories are copied. The generated walkthrough, timestamp CSV and menu support crossover selection, nested paths, conflicts, growing files, scheduling, ZIP read-back and direct full-hash verification. Sessions are retained and use absolute paths; regenerate after relocating a session.

Validation after this addition: **127 tests passed** in 31.62 seconds. Tests cover timestamp boundaries, six-file selected-batch inclusion, exclusion of other dates, refusal to overwrite existing sessions, growing payloads, ZIP member comparisons, and the generated data through the actual Workspace button including a repeat request. The rebuilt frozen executable also created a session and ran the first-batch verifier. Synthetic local practice does not replace company share/performance/restore acceptance.

Follow-up operator feedback: manual sync now displays a visible scan-result notification, including unchanged already-transferred file counts, no matching files and nothing new to transfer. Matching direct destinations also notify after verification without copying again. Historical duplicate detection still relies on saved signatures, not a fresh destination-health check. The walkthrough now separates the app/menu windows and gives individual actions and expected outcomes; existing HTML instructions were refreshed without resetting sessions. Validation: **128 tests passed** in 48.02 seconds, including notification and no-recopy regressions. The duplicate notification was rendered and inspected at 1024 logical pixels and fit within the window. Existing running demo sessions retain their executable until closed; use a newly generated session for the updated app.

## Workspace resize and performance follow-up

Operator screenshots exposed a height-allocation problem missed by the earlier page renders: Workspace summary/banners could squeeze the selector, footer and table. Job details/statistics now scroll independently; batch and monitoring/sync controls remain outside that area, the selector has a fixed readable height, and the table has a minimum height. Resize tests retain all ten model rows and keep controls within the requested dimensions. The transfer engine now reuses one copy buffer to reduce RAM across concurrent large files.

The new TEST_PERFORMANCE.bat form accepts local/UNC files or recursive folders, separate destinations, timed starts and completion targets. It uses independent job data and the actual worker manager with full hashing and original-source retention. Real approved network tests copied/verifed the entire 357-file folder and separate large-file jobs; an actual clock test dispatched three scheduled jobs together. Full suite: **135 passed** in 59.37 seconds; 17 affected follow-up tests and the final portable network test passed. Read [performance results](PERFORMANCE_RESULTS.md) and [server deployment guidance](PERFORMANCE_GUIDE.md) for exact measurements and limits. The application is not a central multi-client service; keep SQLite local to one running host.


## Final alphabetical-group and stop correction

The queue previously sorted only ready submissions; later jobs with faster scans could overtake earlier jobs. Dispatch now reserves alphabetical groups including pending scans/stability checks. With a limit of three and jobs 5–9, the first group is 5/6/7 and the second 8/9 starts after the first group finishes. Regression coverage simulates reversed readiness and reversed completion. A stopped earlier job releases its reservation.

Workspace Stop Monitoring previously stopped only its controller monitor. It now requests worker cancellation through the same route as Dashboard Stop. Direct copy/verification and matching-destination hash progress honor cancellation, remove incomplete temp copies and preserve existing destinations. New regression checks cover workspace cancellation and interruption during an actual copy.


Final regression run including both corrections: **139 passed in 61.33 seconds**, no warnings. Evidence: `.audit/waves-stop-final.xml`. Manual operator and company deployment acceptance remain separate.
