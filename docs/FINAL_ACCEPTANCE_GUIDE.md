# Final test: start here

Use `OPEN_FINAL_TEST.bat` in the project or the distribution’s TestTools folder. Press **1** in the menu to open the separate Final-Test app and interactive checklist.

Follow one numbered item at a time. Each says what to click and what you should see. Choose **Pass**, **Fail**, **Pending**, or **Not run**, enter notes, then **Export results CSV** to keep your evidence. Progress is saved in the current browser; export a separate copy before handing it over.

You do not need to create the crossover, conflict, growing-file, ZIP or three-job samples yourself. Start with those small supplied files. The first batch test leaves monitoring OFF: **Transfer Batch Files** still copies the chosen batch manually; automatic monitoring would copy stable files from other dates too. **Target Batch Only** filters visible rows; it does not select files for transfer.

The checklist covers navigation/resizing, selected batches, duplicates, conflicts, stability, schedules, three jobs, ZIP, reports, network copying, performance, job/settings validation, failures/recovery, history/restart and reset/delete. Reset/delete tests come last so earlier evidence stays available.

Your shared folders are already configured as disabled jobs:

- **06 Network BIG**: `\\192.168.80.48\c$\Users\MUS1\Music\BIG`; 357 files, about 2.31 GiB at setup.
- **07 Network 2big**: `\\192.168.80.48\c$\Users\MUS1\Music\2big`; 38 files, about 35.3 GiB at setup.

Enable them only at their checklist step. Copies go into new `Final-Test-<timestamp>` folders under the approved `C:\Users\RTC1\Music\BIG` and `C:\Users\RTC1\Music\2big` destinations. Keep source cleanup OFF. Menu **7** independently compares SHA-256 hashes after network jobs finish; hashing the large collection takes time.

Menu **5** benchmarks one existing large network file with three jobs and concurrency limits 1, 2 and 3: up to nine copies, about 9.3 GiB. Menu **6** opens setup for a timed start. Save results before repeating: copies are retained but the latest summary replaces the previous one. CPU/RAM describe the benchmark process and caching affects speed. A completion target is measured, rather than enforced as a cutoff.

Keep the generated session in its original location because its job paths are absolute. Production settings/history are separate. Close an older demo before opening this session so you can identify the correct window.

The automated suite passed **135 tests** on 2026-10-02 in 53.90 seconds, with one pytest cache-permission warning. This does not mark manual checks as passed: they all begin **Not run**. Retention-day, actual backup restoration and company deployment checks remain Pending until performed. A short test cannot establish indefinite maintenance-free operation.

Developers can create another fresh session by running `prepare_final_acceptance.py` in the tested project Python environment. It uses the current `dist` runtime and never loads company job history.


## Alphabetical concurrent groups

Jobs run in case-insensitive alphabetical groups. With jobs 5, 6, 7, 8 and 9 and Max Concurrent Jobs set to 3, the first group is 5/6/7. Jobs 8/9 wait until that group finishes. Slower initial scans or stability checks cannot let later jobs overtake it. Within a group, completion order depends on file sizes and device speed. An earlier growing or locked file can hold later groups; stop that job if the operator chooses to release its place. Disabled jobs and future scheduled windows do not reserve places. New work arriving after a group starts waits for a later group; running transfers are not preempted.

Max Concurrent Jobs controls how many jobs run together. Transfer Threads controls files inside each job: 1 means one file at a time; a larger value allows parallel direct copies. A batch is the group of files submitted by one job, not a single giant write. Robocopy-style describes streaming and safe copying; the app uses Python workers, not robocopy.exe.

Practice launchers are grouped in **TestTools** beside the portable executable: CREATE_DEMO.bat, TEST_PERFORMANCE.bat and OPEN_FINAL_TEST.bat. Existing DemoLab sessions retain their original paths so saved history and source/destination links continue to work.
