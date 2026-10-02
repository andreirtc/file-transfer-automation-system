"""Create an isolated, operator-led acceptance session from the current build."""
from __future__ import annotations
import csv
import html
import json
from datetime import datetime
from pathlib import Path

from core.demo_lab import prepare_lab
from core.models import TransferJob
from core.performance_lab import prepare as prepare_performance
from services.database_service import DatabaseService
from services.configuration_service import ConfigurationService

PROJECT = Path(__file__).resolve().parent
BIG = Path(r"\\192.168.80.48\c$\Users\MUS1\Music\BIG")
TWO_BIG = Path(r"\\192.168.80.48\c$\Users\MUS1\Music\2big")


def create() -> Path:
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    root = prepare_lab(PROJECT / 'dist/FileTransferAutomationSystem/DemoLab' / ('Final-Test-' + stamp),
                       PROJECT / 'dist/FileTransferAutomationSystem')
    db = DatabaseService(root / 'App/database/transfer_history.db')
    config = ConfigurationService(root / 'App/config/config.json')
    # Every seed job has auto_monitor=False; later operator checks can enable it.
    config.set('automatic_monitoring', True)
    config.set('report_auto_generate', False)
    config.set('transfer_threads', 1)
    config.set('max_concurrent_transfers', 3)
    config.save()
    destination_big = Path(r'C:\Users\RTC1\Music\BIG') / ('Final-Test-' + stamp)
    destination_large = Path(r'C:\Users\RTC1\Music\2big') / ('Final-Test-' + stamp)
    for name, source, dest in [('06 Network BIG', BIG, destination_big),
                               ('07 Network 2big', TWO_BIG, destination_large)]:
        db.save_job(TransferJob(name=name, source_folder=str(source), destination_folder=str(dest),
                                enabled=False, auto_monitor=False))
    for index in range(1, 4):
        folder = root / 'Files' / ('Parallel-' + str(index))
        (folder / 'Source').mkdir(parents=True)
        (folder / 'Destination').mkdir()
        (folder / 'Source/sample.bin').write_bytes((b'FINAL ACCEPTANCE SAMPLE\n' * 65536))
        db.save_job(TransferJob(name=f'08 Parallel {index}', source_folder=str(folder / 'Source'),
                                destination_folder=str(folder / 'Destination'), auto_monitor=False))
    scratch = root / 'Files/Scratch'
    (scratch / 'Source').mkdir(parents=True)
    (scratch / 'Destination').mkdir()
    (scratch / 'Source/scratch.txt').write_text('Disposable acceptance file.\n', encoding='utf-8')
    data = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
    first, second = data['batch'], data['next_batch']
    steps: list[tuple[str, str, str]] = []
    def step(phase, action, expected):
        steps.append((phase, action, expected))

    step('1 — Open and inspect', 'Open FINAL_TEST_MENU.bat. Press 1. Use ONLY this Final-Test app for these steps.', 'Five sample jobs, two disabled network jobs and three parallel jobs. Monitoring OFF. Production history is separate.')
    step('1 — Open and inspect', 'Open Dashboard, Workspace, Report, History, Logs, Settings and Guide; close each dialog normally.', 'Every page/dialog opens without an exception. Guide sections load. History starts empty.')
    step('1 — Open and inspect', 'Maximize, restore, resize, then maximize again. In Workspace scroll the upper job details and the file table separately.', 'Job name stays readable. Start Monitoring, Stop Monitoring and Sync All Dates stay accessible. Table has room for multiple rows once populated.')
    step('2 — First selected batch', f'Workspace → 01 Crossover. Leave monitoring OFF. Choose {first}; click Transfer Batch Files once.', 'Exactly SIX files complete with verification Passed. Monitoring OFF means automatic copying is stopped; the manual batch button still works.')
    step('2 — First selected batch', 'In the black menu press 2 BEFORE copying any other dates.', 'FIRST BATCH CHECK: PASS. Six copies match; four files from other dates are correctly excluded.')
    step('2 — First selected batch', 'Click Transfer Batch Files again with the same date.', 'Notification says six already transferred / nothing new. No additional copies or duplicate completion records.')
    step('2 — First selected batch', 'Turn Target Batch Only ON, then OFF. Try All Statuses and COMPLETED. Click column headings and scroll horizontally.', 'These switches filter the table only. They do not select files or start a transfer. Sorting and scrolling work.')
    step('2 — First selected batch', f'Choose {second}; click Transfer Batch Files. Then click Sync All Dates.', 'Three more files, then the older backlog: TEN total. Exactly noon belongs to the next batch. Branch A and Branch B retain separate backup.dmp copies.')
    step('2 — First selected batch', 'Press menu 3 and inspect the Crossover lines; repeat the resize exercise with ten rows.', 'Ten Crossover MATCH lines. Other untested jobs can be NOT COPIED. Scrolling reveals every row; counts agree with history.')
    step('3 — Conflicts', 'Select 02 Conflicts; click Sync All Dates. Overwrite choose_overwrite.dmp and Skip choose_skip.dmp.', 'matching.dmp is recognized as identical. Overwrite completes and matches. Skip preserves the different destination and is SKIPPED.')
    step('3 — Conflicts', 'Reset ONLY 02 Conflicts using its Dashboard reset button; confirm. Sync again. Cancel a conflict dialog when shown.', 'Cancel does not replace that destination. Inspect its final status/message. Reset clears this job history, not files.')
    step('3 — Conflicts', 'With monitoring stopped, Settings → Always skip → Save. Reset 02 Conflicts and sync; inspect the remaining different file.', 'Different destination stays unchanged without an Ask dialog. Identical files need no recopy.')
    step('3 — Conflicts', 'Settings → Always overwrite → Save. Reset 02 Conflicts and sync. Restore Ask afterward.', 'All three destinations now match. No conflict dialog for overwrite policy. The earlier deliberately skipped file no longer differs.')
    step('4 — Stability and monitoring', 'Select 03 Growing File. Press menu 4, then immediately click Sync All Dates in the app.', 'File remains PROCESSING while the helper writes for 45 seconds. It completes only after growth ends and stability checks pass.')
    step('4 — Stability and monitoring', 'Dashboard → 08 Parallel 1: Start Monitoring, then Stop Monitoring. Open Workspace from its card and repeat Start/Stop there.', 'Monitoring indicator changes on both pages. Stable sample completes; stopping monitoring is not a delete action.')
    step('4 — Stability and monitoring', 'After all transfers finish, Dashboard: Refresh, expand/collapse recent activity, Clear Feed, open each parallel job Workspace.', 'Cards refresh; activity expands and clears. Clear Feed does not erase transfer history or copied files.')
    step('5 — Schedule', 'Edit 04 Scheduled. Click Weekdays, Everyday, Weekends and individual days. Restore Everyday. Set window start to one minute ago and END to 2–3 minutes ahead; Save.', 'Day presets and hours save correctly. Window END is the transfer trigger; it is not a completion deadline.')
    step('5 — Schedule', 'Start Monitoring ONLY 04 Scheduled. Do not click either sync button. Wait until the end minute.', 'Stable file waits for the window, then transfers automatically at the end minute. Record the actual time. Stop Monitoring afterward.')
    step('5 — Schedule', 'Reset only 04 Scheduled. Set its end 3 minutes ahead and Start Monitoring. When WAITING_FOR_WINDOW appears, right-click that row → Force Start Transfer.', 'Manual override starts this stable file before the scheduled end. Stop afterward.')
    step('5 — Schedule', 'Reset only 04 Scheduled; edit its days to exclude today, with end 2 minutes ahead. Start, wait past end, then Stop.', 'No automatic transfer on an excluded day. Restore Everyday. A manual sync would bypass this test.')
    step('6 — Three jobs', 'Stop All. Disable jobs 01–05 temporarily; network jobs 06–07 remain disabled. Keep only the three 08 Parallel jobs enabled. Settings → Max Concurrent Jobs 3 → Save.', 'Start All will operate only on the three local parallel samples, not the large network folders.')
    step('6 — Three jobs', 'Reset the three parallel jobs individually if already completed. Dashboard → Start All. Wait for completion, then Stop All.', 'All three enabled jobs are monitored and finish with Passed. Small samples may finish too fast to observe overlap; menu performance tests measure overlap separately.')
    step('6 — Three jobs', 'Restore enabled status of jobs 01–05. Keep 06–07 disabled until the network phase. Stop All.', 'Local jobs are available again. No network transfer starts automatically.')
    step('7 — ZIP', 'Stop All. Settings → Batch ZIP Archive, password DemoOnly-2026! → Save. Select 05 ZIP Practice → Sync All Dates.', 'Two source files complete into encrypted archive(s); nested/zip_sample.dmp remains distinct from zip_sample.dmp.')
    step('7 — ZIP', 'Press menu 3 and read ZIP MATCH lines. Try opening an archive using your installed archive tool with a wrong password, then DemoOnly-2026!.', 'Two decrypted members match their source hashes. Wrong password fails. Do not extract over the sources. Raw ZIP-job destinations may say NOT COPIED.')
    step('7 — ZIP', 'Reset only 05 ZIP Practice and repeat its ZIP sync. Restore Direct mode afterward.', 'Existing archive handling remains safe; any conflict is visible. Direct/Batch Compression controls agree when Settings is reopened.')
    step('8 — Reports', f'Report → choose {first}; enter your operator name and a test repository tag; Refresh.', 'The six original Crossover files belong to this date. Other completed jobs can also contribute; do not assume the entire report total is six.')
    step('8 — Reports', 'Configure Checklist → add a temporary system, choose linked job 01 Crossover, edit pattern/type/description/location and Checked By; Save.', 'Mapping and sign-off values appear in report and persist. Linked job prevents unrelated files from satisfying the row.')
    step('8 — Reports', 'Configure Checklist → change values → Cancel. Reopen. Delete the temporary system and Save.', 'Cancel leaves saved values unchanged. Delete removes only the selected checklist row.')
    step('8 — Reports', 'Generate Excel → Open Reports Folder → open the workbook. Review file status, batch date, verification and sign-off.', 'Excel opens correctly and agrees with app history. Unrun/failed files are not presented as verified successes.')
    step('8 — Reports', 'Leave Excel open; Generate Excel again for the same date.', 'If Excel locks the existing workbook, an alternative report filename is created or a clear error appears; the UI remains usable.')
    step('8 — Reports', 'Configure Checklist → turn automatic reports on; Save. Run a scratch transfer later and inspect reports/logs. Restore automatic reports off afterward.', 'Automatic report generation is observable; any generation error is visible. Manual generation remains available.')
    step('8 — Reports', 'Configure Checklist → Reset Defaults → Cancel; reopen and inspect. Test Reset Defaults → Save only at the end of all report checks.', 'Cancel preserves mappings. Saving defaults changes checklist configuration, not copied files or history.')
    step('9 — Network BIG', f'Settings: Direct, full hash (Smart Verification OFF), cleanup OFF, Network Drive Mode ON. Edit 06 Network BIG → Enabled ON → Save. Inspect destination: {destination_big}.', 'Source is your original shared BIG; destination is a new Final-Test folder, keeping existing copies separate.')
    step('9 — Network BIG', 'Select 06 Network BIG → Sync All Dates. Note start and finish times. Wait for all rows; browse the destination tree.', 'At setup inventory: 357 files (~2.31 GiB). Every copied file is COMPLETED/Passed, nested paths stay intact. Live source changes can change the count.')
    step('9 — Network BIG', 'Repeat Sync All Dates. Stop and disable 06 when finished.', 'Already-transferred notification; no new completion records for unchanged files. Original shared files remain present.')
    step('9 — Network 2big', f'For the entire large collection, enable ONLY 07 Network 2big, then Sync All Dates. Destination: {destination_large}.', 'At setup inventory: 38 files (~35.3 GiB). This needs at least that much additional free space and may take time. Every completed row shows Passed; originals remain. Disable this job afterward.')
    step('9 — Network verification', 'Press menu 7 after the network jobs finish; wait while it hashes source and destination files.', 'NETWORK CHECK: PASS for both copied folders. Missing/unrun network jobs report NOT YET PASS. Hashing 35 GiB over the network takes time.')
    step('10 — Measured performance', 'Close the Final-Test app normally. Press menu 5 for the prepared ONE-large-file comparison.', 'Three jobs per run, concurrency limits 1, 2, 3: up to nine copies (~9.3 GiB). Separate benchmark destinations and database; originals retained.')
    step('10 — Measured performance', 'Read Performance-Large/RESULT.txt and RESULT.json when finished.', 'Each run reports duration, CPU, peak RAM, throughput, observed concurrency and hash verification. A target time is measured, not enforced cancellation. Cache affects speed.')
    step('10 — Measured performance', f'Save a copy of Performance-Large/RESULT.txt and RESULT.json before another benchmark. Press menu 6; choose Use an existing file and paste {TWO_BIG / "BIG 1/BIG/4K 10 hours - Earth from Space & Space Wind Audio - Long Video - relaxing, meditation, nature (2).mp4"}. Set start 2–3 minutes ahead and your desired target. Keep the displayed test destination; accept and wait.', 'Actual start/end are recorded. A new run retains copies but replaces the summary results. Preparation may delay actual start; this is distinct from the app window-END schedule tested earlier.')
    step('11 — Add/Edit validation', f'Reopen app. Add Job with empty name/path, then identical source/destination, then destination inside source. Cancel after checking errors.', 'Invalid configurations are rejected. Browse dialogs open and Cancel leaves fields unchanged.')
    step('11 — Add/Edit validation', f'Add job named 09 Scratch using source {scratch / "Source"} and destination {scratch / "Destination"}; Auto Monitor OFF, Enabled ON, continuous → Save.', 'One new card and Workspace selection appear. No file creation required; scratch.txt is supplied.')
    step('11 — Add/Edit validation', 'Edit 09 Scratch: change its name → Cancel. Reopen, rename to 09 Scratch Test → Save. Disable then re-enable it.', 'Cancel preserves name; Save updates card/dropdown. Disabled job is excluded by Start All. Auto Monitor is independent of Enabled.')
    step('11 — Add/Edit validation', 'Settings: change a value → Cancel → reopen. Then enter invalid cycle 25:99 → Save; correct to 18:00/12:00.', 'Cancel preserves settings. Invalid hours are rejected with a readable message.')
    step('11 — Settings coverage', 'Stop All. Change threads, stability interval/checks, retry count/delay, reconciliation interval, network mode and concurrency; Save then reopen.', 'Values persist. Restore 1 thread, 2-second stability, 2 checks, concurrency 3 for this lab. Behavioral retry/stability/concurrency tests are separate steps, not proven solely by saving.')
    step('11 — Settings coverage', 'Smart Verification ON: save/reopen, then OFF again for the final transfer evidence.', 'Toggle persists. Full hashes are required for acceptance evidence. These 2big files are below 2 GiB, so they do not exercise the sampled >2 GiB branch.')
    step('12 — Error and recovery', '09 Scratch Test stopped: in Explorer rename its Source folder to Source-held. Click Sync All Dates. Restore name to Source; retry.', 'Unavailable-source error is visible. Existing history is retained; after restoration transfer completes.')
    step('12 — Modified source', 'Append a new line to scratch.txt in Source. Sync All Dates again; approve overwrite if asked.', 'Changed size/time causes a new transfer, with updated destination content and Passed verification.')
    step('12 — Locked source', 'Stop the scratch job. Reset only its history. Press menu 8 to hold scratch.txt exclusively for 45 seconds; immediately sync in the app.', 'No partial destination is accepted as completed while source is locked. After release, retry/sync completes safely.')
    step('12 — Failed destination', 'Stop scratch job; append another line to its source. Press menu 9 to hold the existing destination exclusively for 45 seconds; immediately sync and choose Overwrite.', 'An overwrite blocked by the OS cannot be reported as success. Existing destination stays intact until replace succeeds. After lock release retry/sync and verify Passed.')
    step('12 — Network unavailable', 'After saving results, disconnect THIS CLIENT from the network using normal Windows controls; request 06 sync, restore connection and retry.', 'Clear inaccessible-source error; no history deletion. Recovery works. Do not change the source laptop, shared-folder permissions or company network equipment.')
    step('13 — History, logs, restart', 'History: scroll and inspect completed, skipped and any failed records. Logs: choose each available log, Refresh and Close.', 'Readable file names/statuses/times/hash/error details. Logs refresh without crashes; absent logs are explained.')
    step('13 — History, logs, restart', 'Stop All; close app and reopen it. Inspect jobs, edited settings, history and reports; repeat an unchanged scratch sync.', 'Configuration/history survive restart. No automatic monitoring was requested for the network jobs. Unchanged source is duplicate-protected.')
    step('13 — Auto monitor', 'Set only 09 Scratch Test Auto Monitor ON, Save; close and reopen.', 'This job starts monitoring on launch according to its enabled/auto-monitor settings. Stop it, restore Auto Monitor OFF and Save.')
    step('13 — Close during work', 'Use 07 Network 2big only if you still need its first copy, or reset ONLY that lab job for a matching-destination run. Start sync, close the window during active work, then reopen after shutdown.', 'App waits for active scans/transfers according to its shutdown behavior; does not falsely record partial work as verified. Reopen and sync to recover. Do not force-kill it.')
    step('14 — Reset/Delete LAST', '09 Scratch Test: Reset → Cancel, then Reset → Confirm. Inspect source and destination in Explorer.', 'Cancel preserves history. Confirm clears only job history/duplicate tracking; both files remain.')
    step('14 — Reset/Delete LAST', '09 Scratch Test: Delete → Cancel, then Delete → Confirm.', 'Cancel preserves job. Confirm removes job/card; source and destination files remain.')
    step('14 — Reset/Delete LAST', 'After exporting results and recording report evidence, Dashboard → Reset All → Cancel, then Confirm.', 'Cancel preserves all history. Confirm clears history for this disposable session only; jobs and copied files remain. This intentionally invalidates earlier on-screen counts.')
    step('15 — Long-duration/company checks', 'Keep Source Cleanup OFF on shared sources. Review the automated cleanup regression evidence; if live retention testing is required, use a separate disposable source and wait at least one configured day.', 'Retention is destructive and time-based. The short demo does not prove a full retention-day run; mark Pending unless actually performed.')
    step('15 — Long-duration/company checks', 'Company IT: test backup restoration, server login/startup, sleep/logoff behavior, overnight weekday boundaries and account access using the intended deployment.', 'These environment and restore checks require company validation. Synthetic .dmp files are not real restorable backups. Mark Not run until verified.')
    step('15 — Record decision', 'Export this checklist. Attach benchmark results and report workbook. Review every Fail and Not run with the receiving operator/IT owner.', 'No silent green checkmarks: Pass only means you observed the expected behavior. An important untested scenario remains a handover limitation.')

    headers = ['id', 'phase', 'action', 'expected', 'result', 'notes']
    records = [dict(zip(headers, [f'T{i:02}', phase, action, expected, 'Not run', '']))
               for i, (phase, action, expected) in enumerate(steps, 1)]
    with (root / 'FINAL_TEST_RESULTS.csv').open('w', newline='', encoding='utf-8-sig') as out:
        writer = csv.DictWriter(out, headers); writer.writeheader(); writer.writerows(records)
    markdown = ['# Final acceptance test', '', 'Use the separate Final-Test app. Follow the steps in order. Mark Pass only after observing the expected result.', '',
                'The HTML checklist saves progress in this browser and exports a CSV. The supplied CSV starts with every manual test Not run.', '',
                'Target Batch Only is a display filter. Transfer Batch Files chooses files by batch date automatically; there are no file-selection checkboxes.', '',
                f'Session: `{root}`', '']
    for record in records:
        markdown.extend([f'## {record["id"]} · {record["phase"]}', '', record['action'], '', '**Expected:** ' + record['expected'], ''])
    (root / 'FINAL_TEST_GUIDE.md').write_text('\n'.join(markdown), encoding='utf-8')
    blocks = ''.join(f'<article data-id="{r["id"]}"><h3>{r["id"]} · {html.escape(r["phase"])}</h3><p>{html.escape(r["action"])}</p><p class="expected"><b>Expected:</b> {html.escape(r["expected"])}</p><label>Result <select><option>Not run</option><option>Pass</option><option>Fail</option><option>Pending</option></select></label><label> Notes <textarea rows="2"></textarea></label></article>' for r in records)
    page = r'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Final acceptance checklist</title>
<style>body{font:17px Segoe UI,sans-serif;max-width:1000px;margin:auto;padding:24px;background:#f4f7fb;color:#203040}article{background:white;border:1px solid #ccd6e0;border-radius:10px;padding:20px;margin:20px 0}h3{margin-top:0}.expected{background:#eaf4ff;padding:12px}select,textarea,button{font:inherit;padding:8px}textarea{display:block;width:95%;margin-top:8px}header{position:sticky;top:0;background:#f4f7fb;padding:12px;border-bottom:1px solid #ccd6e0}button{cursor:pointer}p{line-height:1.5}</style>
<header><b id="progress"></b> <button id="export">Export results CSV</button> <button onclick="window.print()">Print</button><small id="storage"></small></header>
<h1>Final acceptance: follow one step at a time</h1><p>Open <b>FINAL_TEST_MENU.bat</b> and press <b>1</b> for the separate test app. Keep this guide open beside it. The menu numbers belong to the black helper window; they are not buttons in the app.</p><p><b>Pass</b> means you observed the expected result. Leave untested items <b>Not run</b>; use <b>Pending</b> for long-duration/company checks. Network jobs start disabled; enable them only at their numbered step. Source Cleanup stays OFF on your shared files.</p><p><b>Target Batch Only</b> changes which rows you see. <b>Transfer Batch Files</b> automatically requests files with the chosen batch date. You do not tick files individually.</p>''' + blocks + r'''<script>
const records=RECORDS, key=KEY, cards=[...document.querySelectorAll('article')];
let saved={};try{saved=JSON.parse(localStorage.getItem(key)||'{}')}catch(e){document.querySelector('#storage').textContent=' Browser saving unavailable; export CSV to keep results.'}
for(const c of cards){const s=saved[c.dataset.id];if(s){c.querySelector('select').value=s.result;c.querySelector('textarea').value=s.notes}}
function update(){const value={};for(const c of cards)value[c.dataset.id]={result:c.querySelector('select').value,notes:c.querySelector('textarea').value};try{localStorage.setItem(key,JSON.stringify(value))}catch(e){document.querySelector('#storage').textContent=' Export CSV to keep results.'}const vals=Object.values(value);document.querySelector('#progress').textContent=vals.filter(v=>v.result==='Pass').length+' / '+cards.length+' passed; '+vals.filter(v=>v.result==='Fail').length+' failed';return value}
for(const c of cards)c.addEventListener('input',update);update();
document.querySelector('#export').onclick=()=>{const value=update(),fields=['id','phase','action','expected','result','notes'];const quote=v=>'"'+String(v??'').replaceAll('"','""')+'"';const lines=[fields.map(quote).join(',')];for(const r of records)lines.push(fields.map(f=>quote(f==='result'||f==='notes'?value[r.id][f]:r[f])).join(','));const url=URL.createObjectURL(new Blob(['\ufeff'+lines.join('\r\n')],{type:'text/csv;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download='FINAL_TEST_RESULTS.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)};
</script></html>'''
    page = page.replace('RECORDS', json.dumps(records).replace('</', '<\\/')).replace('KEY', json.dumps(str(root)))
    (root / 'FINAL_TEST_GUIDE.html').write_text(page, encoding='utf-8')

    perf = root / 'Performance-Large'
    prepare_performance(perf)
    plan = json.loads((perf / 'PLAN.json').read_text())
    plan.update(source_file=str(TWO_BIG / 'BIG 1/BIG/4K 10 hours - Earth from Space & Space Wind Audio - Long Video - relaxing, meditation, nature (2).mp4'),
                source_relative_root=str(TWO_BIG), destination_root=str(destination_large / 'Benchmark'), concurrency_limits=[1, 2, 3])
    (perf / 'PLAN.json').write_text(json.dumps(plan, indent=2), encoding='utf-8')
    (root / 'NETWORK_PLAN.json').write_text(json.dumps([dict(source=str(BIG), destination=str(destination_big)),
              dict(source=str(TWO_BIG), destination=str(destination_large))], indent=2), encoding='utf-8')
    (root / 'VERIFY_NETWORK.ps1').write_text(r'''$ErrorActionPreference = 'Stop'
$plans = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'NETWORK_PLAN.json') -Raw | ConvertFrom-Json
$lines = [System.Collections.Generic.List[string]]::new()
$allOkay = $true
foreach ($plan in $plans) {
  try {
    $files = @(Get-ChildItem -LiteralPath $plan.source -Recurse -File)
    $count = 0; $bad = 0
    foreach ($file in $files) {
      $relative = $file.FullName.Substring($plan.source.Length).TrimStart('\')
      $dest = Join-Path $plan.destination $relative
      $status = 'MISSING'
      if (Test-Path -LiteralPath $dest -PathType Leaf) {
        $before = Get-Item -LiteralPath $file.FullName
        $hash = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash
        $destHash = (Get-FileHash -LiteralPath $dest -Algorithm SHA256).Hash
        $after = Get-Item -LiteralPath $file.FullName
        $status = if ($before.Length -ne $after.Length -or $before.LastWriteTimeUtc -ne $after.LastWriteTimeUtc) {'SOURCE CHANGED'} elseif ($hash -eq $destHash) {'MATCH'} else {'DIFFERENT'}
      }
      if ($status -ne 'MATCH') {$bad++}
      $count++
      Write-Host "$count / $($files.Count): $status $relative"
      $lines.Add("$status`: $($plan.source)\$relative")
    }
    $copies = if (Test-Path -LiteralPath $plan.destination) {@(Get-ChildItem -LiteralPath $plan.destination -Recurse -File | Where-Object {$_.FullName -notlike "$($plan.destination)\Benchmark\*"}).Count} else {0}
    $okay = $files.Count -gt 0 -and $bad -eq 0 -and $copies -eq $files.Count
    $allOkay = $allOkay -and $okay
    $lines.Add("Folder: $($plan.source); source files=$($files.Count); copies=$copies; mismatches/missing=$bad")
  } catch { $allOkay = $false; $lines.Add("ERROR: $($_.Exception.Message)") }
}
$lines.Add($(if ($allOkay) {'NETWORK CHECK: PASS'} else {'NETWORK CHECK: NOT YET PASS'}))
$lines | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'NETWORK_RESULTS.txt') -Encoding UTF8
Write-Host $lines[$lines.Count-1]
''', encoding='utf-8-sig')
    (root / 'HOLD_FILE.ps1').write_text(r'''param([ValidateSet('source','destination')][string]$Kind='source')
$ErrorActionPreference='Stop'
$folder = if ($Kind -eq 'source') {'Source'} else {'Destination'}
$target = Join-Path $PSScriptRoot "Files\Scratch\$folder\scratch.txt"
$stream = [System.IO.File]::Open($target,[System.IO.FileMode]::Open,[System.IO.FileAccess]::Read,[System.IO.FileShare]::None)
try {Write-Host "Exclusive $Kind lock active for 45 seconds. Test in the app now."; Start-Sleep -Seconds 45} finally {$stream.Dispose(); Write-Host 'Lock released.'}
''', encoding='utf-8-sig')
    menu = r'''@echo off
cd /d "%~dp0"
:menu
echo FINAL ACCEPTANCE - disposable test app
echo 1. Open test app and checklist
echo 2. Verify FIRST six crossover files - before other dates
echo 3. Verify local demo copies and ZIP members
echo 4. Grow sample for 45 seconds
echo 5. Run prepared one-large-file 1/2/3 concurrency benchmark
echo 6. Configure and run a scheduled benchmark
echo 7. Verify shared BIG and 2big copies with full hashes
echo 8. Lock scratch SOURCE for 45 seconds
echo 9. Lock scratch DESTINATION for 45 seconds
echo 0. Exit
choice /c 1234567890 /n /m "Choose: "
if errorlevel 10 exit /b
if errorlevel 9 goto lockdest
if errorlevel 8 goto locksource
if errorlevel 7 goto network
if errorlevel 6 goto scheduled
if errorlevel 5 goto performance
if errorlevel 4 goto grow
if errorlevel 3 goto verify
if errorlevel 2 goto first
start "" "FINAL_TEST_GUIDE.html"
start "" "App\FileTransferAutomationSystem.exe"
goto menu
:first
start "" /wait "App\FileTransferAutomationSystem.exe" --demo-verify-first "%cd%"
type "VERIFY_RESULTS.txt"
pause
goto menu
:verify
start "" /wait "App\FileTransferAutomationSystem.exe" --demo-verify "%cd%"
type "VERIFY_RESULTS.txt"
pause
goto menu
:grow
start "Growing sample" "App\FileTransferAutomationSystem.exe" --demo-grow "%cd%"
goto menu
:scheduled
start "" /wait "App\FileTransferAutomationSystem.exe" --performance-configure "%cd%\Performance-Large"
if errorlevel 1 goto menu
:performance
start "" /wait "App\FileTransferAutomationSystem.exe" --performance-run "%cd%\Performance-Large"
if exist "Performance-Large\RESULT.txt" type "Performance-Large\RESULT.txt"
if exist "PERFORMANCE_ERROR.txt" type "PERFORMANCE_ERROR.txt"
pause
goto menu
:network
powershell -NoProfile -ExecutionPolicy Bypass -File "%cd%\VERIFY_NETWORK.ps1"
pause
goto menu
:locksource
start "Source lock" powershell -NoProfile -ExecutionPolicy Bypass -File "%cd%\HOLD_FILE.ps1" source
goto menu
:lockdest
start "Destination lock" powershell -NoProfile -ExecutionPolicy Bypass -File "%cd%\HOLD_FILE.ps1" destination
goto menu
'''
    (root / 'FINAL_TEST_MENU.bat').write_text(menu.replace('\n', '\r\n'), encoding='utf-8')
    import shutil
    tools = PROJECT / 'dist/FileTransferAutomationSystem/TestTools'
    tools.mkdir(exist_ok=True)
    for name in ('OPEN_FINAL_TEST.bat', 'CREATE_DEMO.bat', 'TEST_PERFORMANCE.bat'):
        shutil.copy2(PROJECT / name, tools / name)
    (PROJECT / '.audit/FINAL_ACCEPTANCE_SESSION.txt').write_text(str(root), encoding='utf-8')
    return root


if __name__ == '__main__':
    print(create())
