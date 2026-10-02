# Operator guide

## Before starting a shift

1. Open the company's installed application. Keep it running while backups are expected.
2. On **Dashboard**, confirm the required jobs, source/destination paths and monitoring states. Check the activity feed for failures or connectivity errors.
3. Verify the machine is awake, the network shares are available under your Windows account, and the destination has enough space.
4. Identify the operational batch date from the backup process. Do not assume it is today's calendar date.

## Navigate the application

| Sidebar / control | Purpose |
| --- | --- |
| Dashboard | All configured job cards, progress, counts and activity feed |
| Workspace | Selected job's file table and batch actions |
| Report | TFSPH Excel checklist for a chosen batch date |
| Add Job / Edit Job | Configure names, source/destination, automatic monitoring and schedule |
| History | Recorded transfers for the selected job |
| Logs | Application, transfer and error logs |
| Settings | Transfer mode, cycle hours, verification, concurrency, stability and cleanup |
| Guide | These operator, demo, IT and audit documents |

## Batch date and midnight crossover

Batch assignment uses the **source file's last modification time**, in the PC's local timezone. It does not read the date from the filename or database-backup contents.

For the default operational cycle of 18:00 to 12:00:

| Source last modified | Assigned batch |
| --- | --- |
| September 15, 23:15 | September 15 |
| September 16, 02:30 | September 15 |
| September 16, 11:59 | September 15 |
| September 16, exactly 12:00 or later | September 16 |

For an overnight cycle, times strictly before the end cutoff belong to the previous date; all other times belong to the current date. This also assigns files in the afternoon gap to the current date, even though the displayed nominal cycle begins at 18:00. The cycle label is a reference window; selection uses the batch-assignment rule above. For a same-day cycle, the file's calendar date is its batch date.

The operational cycle in **Settings** controls batch tagging. The per-job schedule in **Edit Job** controls when automatic transfer is requested. They are separate settings. Persisted batch tags are retained when global cycle hours change; ask IT before changing hours while work is pending.

## Transfer a selected batch or backlog

1. Open the job's **Workspace** and confirm its source and destination.
2. Choose **Target Batch Date**. Read the displayed cycle reference.
3. Optionally turn on **Target Batch Only** to filter the visible table. This is a display filter, not a transfer request. Status filters further restrict visible rows.
4. Click **Transfer Batch Files**. The scan requests untransferred files assigned to that batch only. Files still changing appear as **PROCESSING** and wait until safe.
5. Watch for **READY → QUEUED → TRANSFERRING / VERIFYING → COMPLETED**. A repeat request shows a notification counting unchanged files already transferred and skipped using saved history. If all matching files are duplicates, it says **Nothing new to transfer**. This history check does not re-check old destinations; use the company's recovery procedure if a destination was removed or damaged. A matching direct destination is separately verified and reported as **Matching file already exists**, without copying again.
6. Confirm copied files in the destination and review the chosen batch in **Report**.

**Sync All Dates** requests every untransferred source file for the selected job, across batch dates, irrespective of the table filter. Use it only when that broader scope is intended. Both manual buttons bypass the schedule but retain safety checks. A scan message is not a completion message.

The workspace opens with a default date calculated at startup. It does not automatically change a manually selected date at midnight. Check it on each shift. **Switch to [date]** selects the suggested date from loaded records; it does not transfer files.

## Automatic monitoring and schedule

**Start Monitoring** watches for new/modified files. Continuous jobs transfer stable files. Window jobs request accumulated files at their configured end minute on the selected calendar weekdays. For an overnight job, enabled weekdays refer to the calendar day on which the end trigger runs; configure Monday night's Tuesday-morning end accordingly.

If the application is closed/asleep, or the end minute is missed, recover with **Transfer Batch Files**. Files that finish after that end trigger may need a manual request or the next scheduled trigger. Starting the app does not guarantee replay of a missed window.

**Stop Monitoring** in the workspace pauses discovery/stability timers; an already running transfer may finish. Dashboard job pause and **Stop All** also request worker cancellation. A direct file already copying or verifying can take time to finish. Wait for the active state to settle before editing, deleting, resetting or closing. Closing waits for active work to settle safely.

## Status and error recovery

| Status | Meaning / action |
| --- | --- |
| DETECTED / PROCESSING | File discovered; wait for unchanged size/time and readable access |
| WAITING_FOR_WINDOW | Stable file retained for scheduled end; right-click can request Force Start |
| READY / QUEUED | Eligible or waiting for a worker slot |
| TRANSFERRING / VERIFYING | Copy/archive work in progress |
| COMPLETED | Recorded verification succeeded |
| FAILED | Read Error column and Logs, fix the underlying issue, then request the batch again |
| CONFLICT | Destination has different contents; choose Overwrite, Skip or Cancel when prompted |
| SKIPPED | Omitted by policy/operator or missing before transfer; not a verified backup |

Automatic retries are bounded by the configured retry count while monitoring runs. Manual sync can request failed files again. A conflict needs an explicit decision; cancelling leaves it unresolved. The default **Ask** overwrite policy can interrupt unattended work. IT must choose an approved policy before unattended deployment.

Stability/readability checks reduce partial-copy risk but cannot prove a backup producer has completed its logical transaction. Use the backup producer's completion signal as well. Files intentionally hidden (dot-prefixed) and transfer temporary files are excluded from discovery.

## Daily report

1. Open **Report** and select the same batch date used for the transfer.
2. Confirm operator, repository tag, supervisor and checklist mappings. **Configure Checklist** links corporate systems to actual jobs; default sample names are not proof of a configured backup.
3. **Refresh Data** reloads recorded results. **Generate Report (.xlsx)** writes the checklist; **Open Reports Folder** locates it.
4. If Excel locks the primary report, the application attempts a `_latest.xlsx` fallback. Close Excel before regeneration; IT should compare and retain the correct version.
5. Read all Pending/Failed entries. Confirm actual filenames, expected backup sizes and escalation yourself. Generated supervisor names are metadata, not a signature or approval. The report does not send messages to IT.

Archive record sizes are original input-file sizes, not compressed ZIP size. Smart verification for direct files larger than 2 GB checks sampled blocks; it is not full-file SHA-256. A past Completed record is not continuous validation that the destination is still healthy.

## Actions requiring care

**Reset** clears transfer history and duplicate tracking. Existing sources may be copied again. It does not delete already copied destinations. **Delete Job** deletes its definition and history. Use these only with the company's approval; do not use them as routine troubleshooting.

Leave source cleanup disabled until IT approves the retention policy. Do not open/edit config/database files during transfers. Escalate unresolved access errors, missing backups, unexpected filenames and failed verification to the assigned IT owner with job name, batch date, timestamp and relevant log lines.


## Alphabetical concurrent groups

Jobs run in case-insensitive alphabetical groups. With jobs 5, 6, 7, 8 and 9 and Max Concurrent Jobs set to 3, the first group is 5/6/7. Jobs 8/9 wait until that group finishes. Slower initial scans or stability checks cannot let later jobs overtake it. Within a group, completion order depends on file sizes and device speed. An earlier growing or locked file can hold later groups; stop that job if the operator chooses to release its place. Disabled jobs and future scheduled windows do not reserve places. New work arriving after a group starts waits for a later group; running transfers are not preempted.

Max Concurrent Jobs controls how many jobs run together. Transfer Threads controls files inside each job: 1 means one file at a time; a larger value allows parallel direct copies. A batch is the group of files submitted by one job, not a single giant write. Robocopy-style describes streaming and safe copying; the app uses Python workers, not robocopy.exe.

Practice launchers are grouped in **TestTools** beside the portable executable: CREATE_DEMO.bat, TEST_PERFORMANCE.bat and OPEN_FINAL_TEST.bat. Existing DemoLab sessions retain their original paths so saved history and source/destination links continue to work.


## Stop Monitoring

Workspace Stop Monitoring and Dashboard Stop now use the same cancellation path. Monitoring switches OFF immediately and active direct transfers check cancellation during copy and hash progress. Incomplete temporary copies are removed; an existing destination is retained and the interrupted record remains retryable. The app does not force-kill a direct worker during a filesystem operation: a blocked Windows/SMB read may delay worker exit. Stop All applies this to every job. Use Start Monitoring or manual Sync again to resume safely.
