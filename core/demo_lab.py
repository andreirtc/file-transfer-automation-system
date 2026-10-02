"""Disposable operator practice sessions; never load the installed job database."""
from __future__ import annotations

import csv
import hashlib
import html
import json
import os
import shutil
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

from core.models import TransferJob
from services.configuration_service import ConfigurationService
from services.database_service import DatabaseService
from services.report_service import ReportService

MARKER = "FTAS operator demo v1"
PASSWORD = "DemoOnly-2026!"


def checked_lab(path: Path) -> tuple[Path, dict]:
    root = path.resolve()
    data = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if data.get("marker") != MARKER or data.get("root") != str(root):
        raise ValueError("Use the original generated demo folder; recreate it after moving it.")
    return root, data


def prepare_lab(path: Path, portable_dir: Path | None = None) -> Path:
    """Create a new session only. Existing sessions/configurations are never reset."""
    root = path.resolve()
    if root.exists():
        raise FileExistsError("Demo folder already exists. Create a new session instead.")
    if portable_dir is not None:
        portable_dir = portable_dir.resolve()
        if not (portable_dir / "FileTransferAutomationSystem.exe").is_file() or not (portable_dir / "_internal").is_dir():
            raise FileNotFoundError("Build the portable application before creating a demo.")
    root.mkdir(parents=True)
    app = root / "App"
    app.mkdir()
    if portable_dir is not None:
        shutil.copy2(portable_dir / "FileTransferAutomationSystem.exe", app)
        shutil.copytree(portable_dir / "_internal", app / "_internal")
        for name in ("docs", "templates", "assets"):
            if (portable_dir / name).is_dir():
                shutil.copytree(portable_dir / name, app / name)

    config = ConfigurationService(app / "config/config.json")
    settings = {
        "automatic_monitoring": False, "auto_cleanup_enabled": False,
        "transfer_mode": "direct", "batch_compression_enabled": False,
        "overwrite_policy": "ask", "smart_verification_enabled": False,
        "stability_check_interval": 2, "required_stable_checks": 2,
        "operational_cycle_start": "18:00", "operational_cycle_end": "12:00",
        "zip_password": PASSWORD, "report_checked_by": "",
        "report_operator_name": "DEMO OPERATOR", "report_repository_tag": "LOCAL DEMO ONLY",
    }
    for key, value in settings.items():
        config.set(key, value)
    db = DatabaseService(app / "database/transfer_history.db")
    names = ["01 Crossover", "02 Conflicts", "03 Growing File", "04 Scheduled", "05 ZIP Practice"]
    schedule_end = datetime.now() + timedelta(minutes=10)
    jobs = []
    for index, name in enumerate(names, 1):
        folder = root / "Files" / f"{index:02}"
        source, dest = folder / "Source", folder / "Destination"
        source.mkdir(parents=True)
        dest.mkdir()
        job = TransferJob(name=name, source_folder=str(source), destination_folder=str(dest),
                          auto_monitor=False, schedule_mode="window" if index == 4 else "continuous",
                          window_start=(datetime.now() - timedelta(minutes=1)).strftime("%H:%M"),
                          window_end=schedule_end.strftime("%H:%M"))
        db.save_job(job)
        jobs.append(job)
    config.set("checklist_systems", [dict(no=i, job_name=job.name, pattern="DEMO sample",
               file_type="FILE", description="Synthetic demo payload only", expected_location=job.destination_folder)
               for i, job in enumerate(jobs, 1)])
    config.save()

    base = (datetime.now() - timedelta(days=2)).replace(hour=0, minute=0, second=0, microsecond=0)
    next_day = base + timedelta(days=1)
    entries = []

    def sample(job_number: int, relative: str, stamp: datetime, note: str):
        source = Path(jobs[job_number - 1].source_folder) / relative
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes((f"SYNTHETIC DEMO ONLY; NOT A RESTORABLE DATABASE BACKUP\n{relative}\n{note}\n").encode() + b"DEMO DATA\n" * 16384)
        os.utime(source, (stamp.timestamp(), stamp.timestamp()))
        entries.append(dict(job=jobs[job_number - 1].name, source=str(source.relative_to(root)),
                            destination=str((Path(jobs[job_number - 1].destination_folder) / relative).relative_to(root)),
                            modified=stamp.isoformat(sep=" "), batch=ReportService.resolve_operational_batch_date(stamp),
                            note=note))
        return source

    for relative, stamp, note in [
        ("01_evening_2315.dmp", base.replace(hour=23, minute=15), "Evening: selected batch"),
        ("02_crossover_0000.dmp", next_day, "Midnight crossover: previous day's batch"),
        ("03_crossover_0230.dmp", next_day.replace(hour=2, minute=30), "02:30 crossover: previous day's batch"),
        ("04_before_cutoff_115959.dmp", next_day.replace(hour=11, minute=59, second=59), "One second before noon: previous day's batch"),
        ("05_exact_cutoff_120000.dmp", next_day.replace(hour=12), "Exactly noon: next batch"),
        ("06_afternoon_1500.dmp", next_day.replace(hour=15), "Afternoon gap: current calendar batch"),
        ("07_next_evening_2315.dmp", next_day.replace(hour=23, minute=15), "Next evening: next batch"),
        ("Branch A/backup.dmp", next_day.replace(hour=2), "Same basename; preserve Branch A"),
        ("Branch B/backup.dmp", next_day.replace(hour=3), "Same basename; preserve Branch B"),
        ("older_backlog.dmp", (base - timedelta(days=1)).replace(hour=23), "Older backlog: Sync All Dates"),
    ]:
        sample(1, relative, stamp, note)
    same = sample(2, "matching.dmp", base.replace(hour=23), "Already identical at destination")
    shutil.copy2(same, Path(jobs[1].destination_folder) / same.name)
    for name in ("choose_overwrite.dmp", "choose_skip.dmp"):
        sample(2, name, base.replace(hour=23), "Destination differs; exercise Ask conflict choice")
        (Path(jobs[1].destination_folder) / name).write_text("Existing destination: retain unless approved overwrite", encoding="utf-8")
    sample(3, "growing.dmp", datetime.now(), "Use menu option 3 before syncing; keeps changing for 45 seconds")
    sample(4, "scheduled.dmp", datetime.now(), "Start this job; wait for configured end minute")
    sample(5, "zip_sample.dmp", base.replace(hour=23), "Switch global Settings to ZIP before this job")
    sample(5, "nested/zip_sample.dmp", next_day.replace(hour=2), "ZIP should preserve nested member path")
    data = dict(marker=MARKER, root=str(root), batch=base.date().isoformat(),
                next_batch=next_day.date().isoformat(), schedule_end=schedule_end.strftime("%H:%M"), files=entries)
    (root / "manifest.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    with (root / "EXPECTED_FILES.csv").open("w", newline="", encoding="utf-8-sig") as output:
        writer = csv.DictWriter(output, fieldnames=list(entries[0]))
        writer.writeheader()
        writer.writerows(entries)
    write_walkthrough(root, data)
    return root


def write_walkthrough(root: Path, data: dict):
    """Refresh instructions without changing files, settings or history."""
    rows = "".join("<tr>" + "".join(f"<td>{html.escape(str(entry[k]))}</td>" for k in ("job", "source", "modified", "batch", "note")) + "</tr>" for entry in data["files"])
    guide = f"""<!doctype html><html><meta charset="utf-8"><title>Operator demo lab</title>
<style>body{{font:16px Segoe UI,sans-serif;max-width:1200px;margin:32px auto;padding:20px;color:#203040}}table{{border-collapse:collapse;width:100%}}td,th{{padding:10px;border:1px solid #ccc;text-align:left}}li{{margin:14px 0}}code{{background:#eee;padding:3px}}</style>
<h1>Operator demo lab</h1><p>Independent app, settings, history and synthetic local files. No production jobs are loaded. Keep this folder in its current location. Double-click <b>DEMO_MENU.bat</b> to launch the app, grow a file or verify copies.</p>
<h2>Start here: two separate windows</h2>
<p><b>Demo app</b> is the window with Dashboard and Workspace. <b>Demo menu</b> is the black window opened by DEMO_MENU.bat. When a step says “press 5”, click the black window and press the number 5 on your keyboard. It is a test helper, not a button inside the app.</p>
<p><b>Already started?</b> You can keep your current session for the later exercises. For a clean first-batch test, close the old demo app and run CREATE_DEMO.bat again. That keeps your old session and creates a new one. Keep each session in its original folder.</p>
<h2>A. Main demo: follow these steps in order</h2><ol>
<li><b>Open the app.</b> In the black demo menu, press <b>1</b>. In the app, click <b>Workspace</b> and select <b>01 Crossover</b>. Do not click Start or Start All yet: continuous monitoring would copy every stable batch.</li>
<li><b>Pick the first batch.</b> Set the Workspace batch date to <b>{data['batch']}</b>. Click <b>Transfer Batch Files</b> once. Wait until the six requested rows show <b>COMPLETED</b>; file safety checks usually take 4–8 seconds.</li>
<li><b>Check those six copies.</b> Return to the black demo menu and press <b>5</b>. Expected last line: <b>FIRST BATCH CHECK: PASS</b>. This means the six requested files match their sources, and the four files from other batches were left out. Close neither window; press any key to return to the menu. Do this check before step 6.</li>
<li><b>Try the same request again.</b> Return to the app, leave the date at <b>{data['batch']}</b>, and click <b>Transfer Batch Files</b> again. Expected notification: <b>6 file(s) already transferred</b> and <b>Nothing new to transfer</b>. No extra copies are created.</li>
<li><b>Try the view filters (optional).</b> Turn on <b>Target Batch Only</b>: it only hides rows from other dates. Pick COMPLETED in the status filter: it only shows completed rows. These controls do not copy files. Restore the status filter to All and turn Target Batch Only off before continuing.</li>
<li><b>Copy the next batch.</b> Set the date to <b>{data['next_batch']}</b>, then click <b>Transfer Batch Files</b>. Expected: three more files complete (exactly noon, afternoon and next evening). The older backlog is still waiting.</li>
<li><b>Copy the older backlog.</b> Click <b>Sync All Dates</b>. Expected: older_backlog.dmp completes, giving ten crossover files in total. Menu check 5 is only for the earlier six-file stage; after this step, use menu <b>4</b>.</li>
<li><b>Show a report.</b> Open <b>Report</b>, choose <b>{data['batch']}</b>, generate Excel, then use Open Reports Folder. Show History, Logs and Guide. Other demo jobs may still be pending because you have not tested them yet.</li>
</ol><h2>B. Additional exercises: one job at a time</h2><ol>
<li><b>Conflicts:</b> In the app, select <b>02 Conflicts</b> and click <b>Sync All Dates</b>. matching.dmp is already identical: expect a matching-file notification. When the conflict dialog names choose_overwrite.dmp, choose Overwrite. When it names choose_skip.dmp, choose Skip. Menu <b>4</b> will report the intentionally skipped file as DIFFERENT; that is expected.</li>
<li><b>Growing file:</b> Select <b>03 Growing File</b> in the app first. In the black menu press <b>3</b>, then immediately return to the app and click <b>Sync All Dates</b>. Expected: PROCESSING while the helper appends data for 45 seconds, then COMPLETED after the file stops changing. The black menu is occupied until growth finishes; you can still use the app window.</li>
<li><b>Scheduled transfer:</b> Select <b>04 Scheduled</b>. Edit its job: set window end to 2–3 minutes ahead of your current clock, retain Everyday, and save. Click Start for ONLY this job. Do not click Sync All Dates or Transfer Batch Files here: those are manual requests. Expected: transfer starts at the end minute. Stop the job after completion.</li>
<li><b>ZIP:</b> Stop all jobs. Open Settings, select ZIP mode, set password <code>{PASSWORD}</code>, and save. Select <b>05 ZIP Practice</b> and click <b>Sync All Dates</b>. Wait for completion. In the black menu press <b>4</b>: expect two ZIP MATCH lines. Raw copies may say NOT COPIED because this job produces a ZIP instead. Switch Settings back to Direct when finished.</li>
<li><b>Read verification results:</b> Menu <b>4</b> checks all demo jobs. MATCH means source and destination contents are equal. NOT COPIED means that scenario has not been run yet, or ZIP was used. DIFFERENT is expected only for the conflict you deliberately skipped. ZIP MATCH means an archive member was decrypted and matched to its source. The helper never extracts over your originals.</li>
<li><b>Job controls:</b> Use a new temporary demo job to try Add, Edit, Cancel, Start, Stop, Reset and Delete. Reset clears duplicate tracking; deleting a job keeps its files. Do not reset/delete 01 Crossover while following section A.</li>
<li><b>Unavailable source:</b> Stop a demo job. In Explorer rename its Source folder, request Sync All Dates, and expect a clear error. Restore the exact original folder name and retry.</li>
<li><b>Company acceptance:</b> Use the full checklist in Guide for locks, network failures, large backups, closing during transfers and restore checks. The small synthetic demo does not validate those conditions.</li>
</ol><p>Cleanup is disabled; verification uses full hashes. Create a new session by running CREATE_DEMO.bat in the main distribution again. Existing sessions are retained. Do not move a session: preconfigured job paths are absolute.</p>
<h2>Expected timestamps and batch dates</h2><p>Default cycle: 18:00–12:00. Classification uses LastWriteTime, not the filename. Exactly 12:00 belongs to the next batch.</p>
<table><tr><th>Job</th><th>Source file</th><th>LastWriteTime</th><th>Expected batch</th><th>Purpose</th></tr>{rows}</table></html>"""
    (root / "START_HERE.html").write_text(guide, encoding="utf-8")
    (root / "DEMO_MENU.bat").write_text(r'''@echo off
cd /d "%~dp0"
:menu
cls
echo OPERATOR DEMO - separate local practice app
echo 1. Open demo app
echo 2. Open instructions and expected timestamps
echo 3. Grow sample file for 45 seconds
echo 4. Check copies from all jobs - pending jobs are normal
echo 5. Check the FIRST six crossover files - BEFORE later batches
echo 6. Open sample folders
echo 0. Exit
choice /c 1234560 /n /m "Choose: "
if errorlevel 7 exit /b
if errorlevel 6 goto folders
if errorlevel 5 goto first
if errorlevel 4 goto verify
if errorlevel 3 goto grow
if errorlevel 2 goto guide
start "Demo app" "App\FileTransferAutomationSystem.exe"
goto menu
:guide
start "" "START_HERE.html"
goto menu
:folders
start "" "Files"
goto menu
:grow
start "Growing file - wait 45 seconds" /wait "App\FileTransferAutomationSystem.exe" --demo-grow "%cd%"
type "GROW_RESULT.txt"
pause
goto menu
:first
start "" /wait "App\FileTransferAutomationSystem.exe" --demo-verify-first "%cd%"
goto result
:verify
start "" /wait "App\FileTransferAutomationSystem.exe" --demo-verify "%cd%"
:result
type "VERIFY_RESULTS.txt"
pause
goto menu
''', encoding="utf-8")


def grow_file(path: Path, duration: float = 45, interval: float = 1):
    root, _ = checked_lab(path)
    target = root / "Files/03/Source/growing.dmp"
    until = time.monotonic() + duration
    while time.monotonic() < until:
        with target.open("ab") as output:
            output.write(b"GROWING DEMO BLOCK\n" * 1024)
            output.flush()
            os.fsync(output.fileno())
        time.sleep(interval)
    (root / "GROW_RESULT.txt").write_text("Growth finished. The app must now observe stable size/mtime before copying.\n", encoding="utf-8")


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def verify_lab(path: Path, first_batch_only: bool = False) -> bool:
    root, data = checked_lab(path)
    lines = [f"Demo verification: {datetime.now():%Y-%m-%d %H:%M:%S}", "MATCH = full SHA-256 equal; NOT COPIED may simply mean you have not run that job."]
    okay = True
    for entry in data["files"]:
        if first_batch_only and entry["job"] != "01 Crossover":
            continue
        source, dest = root / entry["source"], root / entry["destination"]
        if first_batch_only and entry["batch"] != data["batch"]:
            status = "UNEXPECTED OTHER BATCH COPY" if dest.exists() else "CORRECTLY EXCLUDED"
            okay &= not dest.exists()
        else:
            status = "NOT COPIED" if not dest.is_file() else "MATCH" if source.is_file() and digest(source) == digest(dest) else "DIFFERENT / SOURCE MISSING"
            okay &= status == "MATCH"
        lines.append(f"{status}: {entry['source']}")
    if not first_batch_only:
        import pyzipper
        for archive in sorted((root / "Files").glob("*/Destination/*.zip")):
            try:
                job_folder = archive.parent.parent
                with pyzipper.AESZipFile(archive) as zipped:
                    zipped.setpassword(PASSWORD.encode())
                    for member in zipped.infolist():
                        if member.is_dir():
                            continue
                        source = job_folder / "Source" / member.filename
                        # Never extract archive paths; constrain read-back source lookup.
                        source.resolve().relative_to((job_folder / "Source").resolve())
                        value = hashlib.sha256()
                        with zipped.open(member) as payload:
                            for chunk in iter(lambda: payload.read(1024 * 1024), b""):
                                value.update(chunk)
                        match = source.is_file() and value.hexdigest() == digest(source)
                        lines.append(f"ZIP {'MATCH' if match else 'DIFFERENT'}: {archive.name} / {member.filename}")
                        okay &= match
            except Exception as exc:
                lines.append(f"ZIP ERROR: {archive.name}: {exc}")
                okay = False
    lines.append("FIRST BATCH CHECK: " + ("PASS" if okay else "NOT YET PASS") if first_batch_only else "Review pending/skipped files above; these are intentional until their scenario is completed.")
    (root / "VERIFY_RESULTS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return okay


def run_cli(action: str, path: str) -> int:
    target = Path(path)
    try:
        if action == "--demo-setup":
            portable = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent / "dist/FileTransferAutomationSystem"
            prepare_lab(target, portable)
        elif action == "--demo-grow":
            grow_file(target)
        else:
            verify_lab(target, action == "--demo-verify-first")
        return 0
    except Exception as exc:
        # Windowed executables have no console: leave a readable diagnostic.
        target.parent.mkdir(parents=True, exist_ok=True)
        (target.parent / "DEMO_ERROR.txt").write_text(f"{action}: {exc}\n", encoding="utf-8")
        return 1
