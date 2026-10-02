# Demo and acceptance checklist

For the final test, use `OPEN_FINAL_TEST.bat` and its numbered interactive checklist. See [Final test: start here](FINAL_ACCEPTANCE_GUIDE.md). It supplies crossover samples and preconfigures shared BIG/2big jobs; manual results start Not run.

## Prepare a safe practice job

For ready-made practice, double-click **CREATE_DEMO.bat** in the project or portable distribution. It creates a fresh independent app with five preconfigured jobs, synthetic files, an HTML walkthrough, expected timestamp CSV, a growing-file simulator and full-hash/ZIP verification. Python is bundled in the portable app; no separate installation is needed. Follow the generated **START_HERE.html**, then use **DEMO_MENU.bat**. Sessions are kept in `dist/FileTransferAutomationSystem/DemoLab` (or `DemoLab` beside the portable executable).

The crossover set includes evening, exactly midnight, 02:30, 11:59:59, exactly 12:00, the afternoon gap, next evening, an older backlog, and identical basenames in different subfolders. It uses the default 18:00–12:00 cycle. Monitoring starts off so the first selected-batch test cannot accidentally transfer every date. Create another session to repeat from a clean state; close the old demo app first. Keep sessions in their generated location because job paths are absolute.

The generated walkthrough separates the main demo into individual actions with expected results. “Menu option 5” means press 5 in the black DEMO_MENU.bat window: it checks the first six copies and confirms that the other four crossover files have not been copied. Use it before transferring the next batch or Sync All Dates. After those steps, use option 4, which checks all jobs and may show normal pending or deliberately skipped files. On a repeat manual request, the app now shows an information notification with the count of unchanged files already transferred and skipped using saved history. An identical direct destination also produces a matching-file notification without being recopied.

ZIP mode is a global setting: stop other demo jobs before switching it. Verification reports missing raw destination files for ZIP jobs; use the **ZIP MATCH** member results for those jobs. A skipped conflict intentionally remains different. These helpers exercise local synthetic data; they do not simulate real network outages, low disk space, large-file performance or a database restore.

Use a separate local source/destination and an approved test job. Keep source cleanup disabled. For a fresh install, automatic monitoring can start enabled jobs: do not copy production job databases into a demo installation. Use direct mode first, Ask conflict policy, and normal stability settings. Record the tested release path and date.

Prepare files with representative backup names and distinct contents. A short PowerShell example inside your dedicated demo source:

```powershell
Set-Content -LiteralPath .\overnight.dmp -Value 'demo payload only'
(Get-Item -LiteralPath .\overnight.dmp).LastWriteTime = [datetime]'2026-09-16 02:30:00'
Set-Content -LiteralPath .\next_batch.dmp -Value 'next batch payload only'
(Get-Item -LiteralPath .\next_batch.dmp).LastWriteTime = [datetime]'2026-09-16 23:15:00'
```

These are demo text files, not real Oracle dumps. Select September 15 for the first transfer with the default overnight cycle.

## Practice before the company demo

Check each item and capture expected/actual results. A passed automated test is not a substitute for the target-PC acceptance steps.

| Check | Expected result |
| --- | --- |
| Launch and all sidebar pages | No exception; readable dashboard, workspace, report and guides |
| Add job, empty fields, same/nested source and destination | Invalid paths/name rejected; valid job created |
| Edit then Cancel | Original job unchanged |
| Job day presets and schedule fields | Weekdays/everyday/weekends and times save correctly |
| Start/stop job and Start All/Stop All | Monitoring state and activity update; active work settles safely |
| Choose batch September 15; Transfer Batch Files | Overnight file waits for stability then completes; next-batch file is absent from destination |
| Target Batch Only and status filter | Visible rows narrow; toggling filter does not transfer anything |
| Repeat selected batch transfer | Successful unchanged file not duplicated; scan remains usable |
| Select September 16 and transfer | Remaining file completes with September 16 tag |
| Sync All Dates | Requests any remaining untransferred files across dates |
| Same basename in two source subfolders | Separate relative destination subfolders; correct contents |
| Growing file | PROCESSING while changing; transferred only after stability |
| Source temporarily inaccessible | Clear error; history not marked as deleted solely because root is unavailable |
| Destination locked/unavailable | FAILED and clear error; source retained; retry after issue resolved |
| Different destination contents | Ask shows conflict; Skip preserves destination; approved Overwrite replaces it |
| Matching destination content | Completed verification; no unnecessary overwrite |
| Transfer History and Logs | Current job/history and relevant diagnostic messages accessible |
| Reset cancelled | No history erased |
| Reset confirmed, on demo job only | History cleared; operator understands duplicate protection is removed |
| Delete cancelled / confirmed, demo job only | Correct job/history retained or removed; source/destination files retained |
| Choose report batch and checklist job mappings | Report rows correspond to correct job and overnight batch |
| Generate Excel / Open Reports Folder | Workbook exists and opens; template layout retained |
| Excel primary report open, regenerate | Warning/fallback or clear save error; operator can find correct workbook |
| ZIP mode with approved demo password | ZIP decrypts; members and verification correct; source retained |
| Invalid password/ZIP error | Clear failure; no silently unencrypted archive |
| Scheduled end a few minutes ahead | Stable files request transfer at end minute; verify enabled end-day setting |
| Restart app after successful transfer | Jobs/history persist; unchanged successful sources not recopied |
| Close during demo transfer | Window waits for worker shutdown without QThread crash |
| Small company-screen resolution and Windows scaling | Buttons/labels reachable; tables can scroll; long paths readable |

For direct files, compare `Get-FileHash` SHA-256 on the source/destination after copying. For ZIP files, decrypt/extract to a separate verification folder and compare source/member hashes. Do not overwrite originals when extracting.

## Company environment acceptance

IT and an operator should test the final portable executable with the actual UNC shares and execution account, representative backup size, low-space/access-denied incidents, reboot/logon startup, sleep policy, a missed-window recovery, overnight weekday scheduling, Excel locks, and archive recovery. Measure full verification time for a large representative backup; finish a database restore using the company's restore procedure.

Record: release path/version or executable SHA-256, Windows account, source/destination, job schedule and end-day, cycle hours, transfer mode, verification mode, data size/duration, result, operator and IT approver. Assign the support owner and store a cold database/config backup.

## Suggested short demo sequence

1. Show Dashboard job paths and monitoring state.
2. Open Workspace, explain batch date from last modification time and the midnight cutoff.
3. Transfer the selected overnight batch; show that the next batch remains pending.
4. Show Completed verification and the destination file/hash.
5. Repeat the request to demonstrate duplicate protection.
6. Select the batch in Report, show checklist mapping and manual review items, then export.
7. Open Guide and show where operators recover errors and IT maintains the installation.

Do not claim maintenance-free operation or a guaranteed restore from a green copy badge. Show the tested scope and the named company owner.
