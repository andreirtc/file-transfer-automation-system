# Recorded performance and network checks — October 2, 2026

These are measurements on the development PC using the approved test sources. They are not capacity guarantees for the company server. Source files were retained and checked before/after. Test copies were placed in new `FTAS-test-...` namespaces under the approved destinations.

## Local generated-file comparison

Each row copies the same 1 GiB file to **three** separate job destinations. Timing includes copying and the application's full SHA-256 verification. These measurements precede the reusable-buffer improvement; the file was exactly 1 GiB, so it used the smaller copy chunk.

| Active job limit | Seconds for all three copies | Effective MiB/s | Peak process RAM | Average process CPU / machine capacity | Verified |
| --- | ---: | ---: | ---: | ---: | --- |
| 1 | 11.755 | 261.33 | 174.64 MiB | 12.10% | Yes |
| 2 | 10.647 | 288.53 | 181.66 MiB | 16.93% | Yes |
| 3 | 7.691 | 399.43 | 186.93 MiB | 30.68% | Yes |

The separate 256 MiB sample comparison also verified all nine copies. Full test JSON is retained under `.audit/local-256m-final` and `.audit/local-1g` in the development checkout.

## Network large-file comparison before buffer improvement

Selected one approximately 1.03 GiB stable file from the approved `2big` share. Each row again makes **three** copies, preserving its selected relative subfolders. Original source collection: 38 files, approximately 35.3 GiB; the entire collection was not copied nine times.

| Active job limit | Seconds for all three copies | Effective MiB/s | Baseline / peak process RAM | Average process CPU / machine capacity | Verified |
| --- | ---: | ---: | ---: | ---: | --- |
| 1 | 13.625 | 232.67 | 170.71 / 205.20 MiB | 11.27% | Yes |
| 2 | 38.665 | 81.99 | 176.38 / 245.04 MiB | 4.41% | Yes |
| 3 | 50.522 | 62.75 | 186.40 / 287.99 MiB | 5.37% | Yes |

Network/disk/SMB caches and changing conditions affect these runs. Effective throughput is a payload/worker-time calculation, **not raw network-wire throughput**. These results show why more concurrency should not be assumed to improve speed. They do not establish a universal best setting.

## Reusable-buffer result in the final portable executable

The copy loop now uses `readinto` with one reusable buffer, avoiding simultaneous old/new large chunk allocations. The final frozen executable copied the same selected network file with **three active jobs**, verified every destination, and confirmed that the original source remained unchanged.

| Measurement | Result |
| --- | --- |
| Worker copy/verification time | 5.944 seconds |
| Baseline / peak process RAM | 165.68 / 214.23 MiB |
| RAM increase above baseline | 48.55 MiB |
| Average process CPU / machine capacity | 29.48% |
| Observed simultaneous jobs | 3 |
| Full verification | Passed |

The earlier three-job RAM increase was approximately 101.59 MiB. The new measured increase is about half of that; baselines differ between processes. The faster time in this repeat has a strong cache/conditions effect and must not be attributed entirely to the buffer change. It is not a network bandwidth guarantee.

The first frozen attempt stopped during source readiness preparation at its short timeout; it made no copies. The helper now allows up to 120 seconds for readiness and reports readiness/permission diagnostics. The final frozen retry passed with the stability checks retained. One extra source-mode buffer retry also passed.

## Entire multilevel folder

All **357 files** in the approved `BIG` share, approximately **2.31 GiB**, were copied to a new namespace under the approved local BIG destination. The relative directory structure was preserved, every destination hash matched, and original source metadata/hashes were revalidated.

- Worker copy/verification time: **217.88 seconds** (3 minutes 38 seconds).
- Effective payload rate: **10.87 MiB/s**.
- Baseline / peak process RAM: **167.30 / 187.09 MiB**.
- Average process CPU / machine capacity: **2.59%**.
- Completed within the five-minute worker-phase target.

Initial source hashing, extra independent destination comparisons and final source revalidation add time outside the worker phase. The entire helper operation takes longer than the reported copy/verification interval, especially on a network with many files.

## Real clock-based schedule check

Three independent local scheduled jobs with full verification were monitored without pressing manual Sync. At the configured end minute, **17:59 on October 2**, all three started at approximately **17:59:00.60**. All finished and verified; observed concurrent jobs reached three. This checks the actual scheduler clock path, rather than a mocked clock. The schedule requests work at window end; it does not promise completion by that time.

## UI and regression validation

- Full automated suite: **135 passed**, no warnings, in 59.37 seconds.
- After increasing readiness diagnostics: 17 affected tests passed.
- Workspace tested across repeated wide/short resizes: action and batch buttons remain in bounds, job selector remains 32 logical pixels high, all ten records remain in the model, and the table has a useful viewport. The detail/statistics area scrolls separately on short windows.
- Empty files and partial final copy chunks pass byte-for-byte checks after the buffer change.
- Recursive same-basename files in different branches remain separate.
- Final portable performance entry point passed the real network three-job test.

Read [the performance guide](PERFORMANCE_GUIDE.md) for repeating tests, measurement limits and supported single-server deployment. Detailed logs/results stay under `.audit` in the developer checkout; they can contain private network paths and should be reviewed before sharing.
