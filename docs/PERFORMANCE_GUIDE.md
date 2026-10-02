# Large-file, network and concurrency testing

See [recorded test results](PERFORMANCE_RESULTS.md) for measured local/network timings, RAM, CPU, multilevel-folder verification and the actual three-job schedule check.

## Run the test helper

1. Close other practice transfers. Double-click **TEST_PERFORMANCE.bat** in the portable TestTools folder (or in the project).
2. In the setup form choose a generated sample, an existing stable file, or an entire folder recursively. You may paste a UNC path directly, without escaping backslashes.
3. Choose an approved **test-only destination**. The helper creates a new `FTAS-test-...` folder and separate run/job subfolders. Existing files are not overwritten and original sources are retained. Folder tests preserve relative subfolders.
4. Choose one, two or three jobs per run. Each job copies the same selected data to its own destination. Select concurrency settings to compare. Three jobs and all three settings create **nine copies** of the data; check free space first.
5. Leave Start at blank to start immediately, or enter the local workstation date/time as `YYYY-MM-DD HH:MM:SS`. Stability checks and setup can delay actual copying; actual start/finish times are recorded.
6. Set a completion target in minutes. This measures whether each run finishes within the target; it **does not forcibly cancel** copies at the deadline.
7. Wait for the results window. `RESULT.txt` summarizes each run; `RESULT.json` includes resource samples. `PROGRESS.txt` gives progress during the test. The session is under `PerformanceLab` beside the executable.

The helper uses an independent configuration/database and the real direct transfer manager. Full SHA-256 verification is enabled, cleanup and automatic monitoring are disabled. It validates the source before and after testing. Do not change files during testing. Test copies remain available for inspection; remove your test namespace later under your company's procedures.

## Interpret results

| Measurement | Meaning |
| --- | --- |
| Effective MiB/s | Total copied payload divided by worker completion time, including ordinary copy verification and job dispatch |
| Verified | All requested records completed verification and destination SHA-256 matched the initial source digest |
| Baseline / peak RAM | This benchmark process working set, including a constructed hidden Qt UI and transfer workers |
| Peak private memory | Memory privately committed by this process |
| CPU average | CPU time across this process's threads divided by elapsed time and logical CPU count |
| Within target | Copy/verification time did not exceed the chosen completion target |

Initial file generation, baseline source hashing, stability preparation, an additional independent destination-hash pass, and final source validation are outside the timed worker phase. Total helper duration is therefore longer. Resource sampling is approximate, at about 50 ms plus event-processing time. It can miss short peaks. Network stalls can delay progress/stat calls. Server CPU, antivirus, visible GUI rendering and other processes' consumption are not measured. Repeated runs can benefit from disk, SMB and OS caches. A benchmark on a busy PC is not an isolated laboratory result.

The app uses Python chunked reads/writes and safe temporary files; it is not a wrapper around `robocopy.exe`. More workers can improve throughput or create contention, depending on disks and network bandwidth. Full verification rereads source/destination data and costs time and I/O. Do not assume three workers are always faster or always use the least resources.

## Test actual scheduling separately

In the demo app, edit **04 Scheduled**: set its window end a few minutes ahead, keep the desired end-day enabled, then Start that job only. Leave manual Sync/Transfer buttons alone. Watch for automatic dispatch at the end minute. Keep the app running and the PC awake. Record actual completion time and errors. The application's schedule triggers at **window end**; it is neither a promised completion deadline nor a persistent service with catch-up scheduling.

For real files, use a separate test installation/job and the approved UNC source. Make sure the backup producer has completed writing. Confirm the execution account's share permissions, destination free space, source/destination hashes, and restore suitability. The helper's Start at field tests a timed request; it does not replace testing the app's scheduled job UI.

## Central server operation

The current application is a desktop process with SQLite history beside the executable. Storing its portable folder on a server does not make it a central service. Opening that EXE from a laptop runs a new process on the laptop; closing/sleeping that laptop stops its work.

Use **one running instance on the server**, with the executable/config/database on the server's local disk. Operators can remotely access that server session under IT's approved remote-access policy. Keep the session/app running, prevent sleep and arrange approved startup/recovery after reboots. Logging out can end the desktop process. Do not start competing instances in different sessions against the same job database.

Do not have several laptops open the app against a SQLite database on an SMB share. This database uses WAL mode; [SQLite requires all WAL clients to be on the same host and does not support WAL over network filesystems](https://sqlite.org/wal.html). A web/client-server operator interface or a managed background service would require additional development; neither is included in this release.


## Alphabetical concurrent groups

Jobs run in case-insensitive alphabetical groups. With jobs 5, 6, 7, 8 and 9 and Max Concurrent Jobs set to 3, the first group is 5/6/7. Jobs 8/9 wait until that group finishes. Slower initial scans or stability checks cannot let later jobs overtake it. Within a group, completion order depends on file sizes and device speed. An earlier growing or locked file can hold later groups; stop that job if the operator chooses to release its place. Disabled jobs and future scheduled windows do not reserve places. New work arriving after a group starts waits for a later group; running transfers are not preempted.

Max Concurrent Jobs controls how many jobs run together. Transfer Threads controls files inside each job: 1 means one file at a time; a larger value allows parallel direct copies. A batch is the group of files submitted by one job, not a single giant write. Robocopy-style describes streaming and safe copying; the app uses Python workers, not robocopy.exe.

Practice launchers are grouped in **TestTools** beside the portable executable: CREATE_DEMO.bat, TEST_PERFORMANCE.bat and OPEN_FINAL_TEST.bat. Existing DemoLab sessions retain their original paths so saved history and source/destination links continue to work.
