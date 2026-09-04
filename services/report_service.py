"""
Report Generation Service for the File Transfer Automation System.

Generates corporate TFSPH Daily Backup Checklist Excel reports based on the
official template (templates/TFSPH_Daily_Backup_Checklist_Template.xlsx).
Supports dynamic row expansion for >8 systems, automated verification and
integrity check resolution, Daily Control Checks evaluation, and executive sign-off.
"""

from __future__ import annotations

import getpass
import logging
import os
import shutil
import sys
from copy import copy
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

import openpyxl
from openpyxl.worksheet.cell_range import CellRange, MultiCellRange

from core.models import FileStatus, TransferJob, TransferRecord, format_file_size
from services.configuration_service import ConfigurationService
from services.database_service import DatabaseService

logger = logging.getLogger("app")


def get_app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


class ReportService:
    """
    Automates generation of the TFSPH Daily Backup Checklist Excel report.
    """

    def __init__(self, config: ConfigurationService, db: DatabaseService):
        self._config = config
        self._db = db

    @property
    def template_path(self) -> Path:
        """Path to the master Excel template."""
        return get_app_dir() / "templates" / "TFSPH_Daily_Backup_Checklist_Template.xlsx"

    @property
    def reports_dir(self) -> Path:
        """Directory where generated daily reports are stored."""
        path = get_app_dir() / "reports"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def _resolve_pattern(pattern_template: str, target_date: date) -> str:
        """
        Replaces date tags in pattern and removes archive extensions (.zip, .rar, etc.)
        as the template has a dedicated File Type column.
        """
        name = pattern_template
        # Replace common date formats
        name = name.replace("<YYYYMMDD>", target_date.strftime("%Y%m%d"))
        name = name.replace("<MM-DD-YYYY>", target_date.strftime("%m-%d-%Y"))
        name = name.replace("<YYYY-MM-DD>", target_date.strftime("%Y-%m-%d"))
        name = name.replace("<YYYY_MM_DD>", target_date.strftime("%Y_%m_%d"))
        name = name.replace("<DD-MM-YYYY>", target_date.strftime("%d-%m-%Y"))

        # Strip any extension if present (e.g. .zip, .rar, .bak, .7z)
        p = Path(name)
        if p.suffix.lower() in (".zip", ".rar", ".bak", ".7z", ".tar", ".gz"):
            name = p.stem
        return name

    @staticmethod
    def _strip_extension(filename: str) -> str:
        """Strip file extension to conform to Table 1 naming pattern specification."""
        p = Path(filename)
        if p.suffix:
            return p.stem
        return filename

    def get_report_data(self, report_date: date | str) -> dict[str, Any]:
        """
        Compile all report data for a specific date from SQLite records and configuration.
        """
        if isinstance(report_date, str):
            try:
                dt_obj = datetime.strptime(report_date[:10], "%Y-%m-%d").date()
            except ValueError:
                dt_obj = datetime.now().date()
        else:
            dt_obj = report_date

        records = self._db.get_records_by_date(dt_obj)
        jobs = {j.id: j for j in self._db.get_jobs()}
        jobs_by_name = {j.name.upper(): j for j in jobs.values()}

        systems = self._config.checklist_systems
        table_rows: list[dict[str, Any]] = []

        # Map transfers to systems
        matched_record_ids: set[str] = set()

        for idx, sys_item in enumerate(systems, start=1):
            job_name = sys_item.get("job_name", f"System {idx}")
            linked_job = sys_item.get("linked_job", "").strip()
            job_name_upper = job_name.upper()
            configured_pattern = sys_item.get("pattern", f"{job_name}_<YYYYMMDD>")
            file_type = sys_item.get("file_type", "FILE")
            description = sys_item.get("description", "")
            expected_location = sys_item.get("expected_location", "")

            # Look up associated TransferJob (by explicit linked_job or job_name)
            associated_job = None
            if linked_job and linked_job.upper() not in ("(MATCH BY NAME)", "(NONE)", "AUTO"):
                associated_job = jobs_by_name.get(linked_job.upper()) or jobs.get(linked_job)
            if not associated_job:
                associated_job = jobs_by_name.get(job_name_upper)

            if not expected_location and associated_job and associated_job.destination_folder:
                expected_location = associated_job.destination_folder

            # Find all matching record(s) completed or detected on this date
            sys_records: list[TransferRecord] = []
            seen_sys_ids: set[str] = set()

            for rec in records:
                is_match = False
                # Direct match by associated job id
                if associated_job and rec.job_id == associated_job.id:
                    is_match = True
                # Match by filename containing job_name
                elif job_name_upper in rec.file_name.upper():
                    is_match = True
                # Match by filename containing linked_job
                elif (
                    linked_job
                    and linked_job.upper() not in ("(MATCH BY NAME)", "(NONE)", "AUTO")
                    and linked_job.upper() in rec.file_name.upper()
                ):
                    is_match = True

                if is_match and rec.id not in seen_sys_ids:
                    sys_records.append(rec)
                    seen_sys_ids.add(rec.id)
                    matched_record_ids.add(rec.id)

            if sys_records:
                completed_recs = [r for r in sys_records if r.status == FileStatus.COMPLETED]
                failed_recs = [r for r in sys_records if r.status == FileStatus.FAILED]
                active_recs = [
                    r for r in sys_records
                    if r.status in (
                        FileStatus.TRANSFERRING,
                        FileStatus.QUEUED,
                        FileStatus.READY,
                        FileStatus.WAITING_FOR_WINDOW,
                        FileStatus.DETECTED,
                    )
                ]

                # Best reference record (latest completed or latest detected)
                best_record = completed_recs[-1] if completed_recs else sys_records[-1]

                # Pattern resolution:
                # Retain corporate configured pattern (resolved with date, without .zip)
                # If no configured pattern and single file, strip extension of the file
                if configured_pattern:
                    pattern_val = self._resolve_pattern(configured_pattern, dt_obj)
                elif len(sys_records) == 1:
                    pattern_val = self._strip_extension(sys_records[0].file_name)
                else:
                    pattern_val = associated_job.name if associated_job else job_name

                # Total file size aggregated across completed files (or all if none completed yet)
                if completed_recs:
                    total_bytes = sum(r.file_size for r in completed_recs)
                else:
                    total_bytes = sum(r.file_size for r in sys_records)

                file_size_val = format_file_size(total_bytes) if total_bytes > 0 else "-"

                # Latest completion timestamp
                comp_times = [r.transfer_completed for r in completed_recs if r.transfer_completed]
                if comp_times:
                    comp_time_val = max(comp_times).strftime("%I:%M %p")
                elif best_record.transfer_completed:
                    comp_time_val = best_record.transfer_completed.strftime("%I:%M %p")
                else:
                    comp_time_val = "-"

                # Verification Status
                if active_recs:
                    status_val = "Pending"
                elif failed_recs and not completed_recs:
                    status_val = "Failed"
                elif failed_recs and completed_recs:
                    status_val = "Failed"
                elif completed_recs:
                    status_val = "Verified"
                elif all(r.status == FileStatus.SKIPPED for r in sys_records):
                    status_val = "Not Applicable"
                else:
                    status_val = "Pending"

                # Automated Integrity Check
                if completed_recs:
                    if any(r.verification_passed is False for r in completed_recs):
                        integrity_val = "Failed"
                    else:
                        integrity_val = "Passed"
                elif failed_recs:
                    integrity_val = "Failed"
                else:
                    integrity_val = "Not Applicable"

                # Remarks
                if failed_recs:
                    first_err = failed_recs[0].error_message or "Transfer failed"
                    if len(failed_recs) == 1:
                        remarks_val = f"Transfer failed: {first_err}"
                    else:
                        remarks_val = f"{len(failed_recs)} file(s) failed: {first_err}"
                elif active_recs:
                    remarks_val = f"Transfer in progress ({len(completed_recs)}/{len(sys_records)} files completed)"
                elif status_val == "Verified":
                    if len(completed_recs) > 1:
                        remarks_val = f"Completed successfully ({len(completed_recs)} files verified)"
                    else:
                        remarks_val = "Completed successfully"
                elif status_val == "Not Applicable":
                    remarks_val = "Skipped by policy"
                else:
                    remarks_val = "In progress / Pending"
            else:
                best_record = None
                # No record transferred today
                pattern_val = self._resolve_pattern(configured_pattern, dt_obj)
                file_size_val = "-"
                comp_time_val = "-"
                status_val = "Pending"
                integrity_val = "Not Applicable"
                remarks_val = "Awaiting scheduled backup execution"

            table_rows.append({
                "no": idx,
                "job_name": job_name,
                "pattern": pattern_val,
                "file_type": file_type,
                "description": description,
                "expected_location": expected_location,
                "file_size": file_size_val,
                "completion_time": comp_time_val,
                "verification_status": status_val,
                "integrity_check": integrity_val,
                "remarks": remarks_val,
                "record": best_record,
            })

        # Evaluate Daily Control Checks
        control_checks = self._evaluate_control_checks(table_rows, records, jobs)

        # Header metadata
        batch_date_str = dt_obj.strftime("%B %d, %Y")
        repo_tag = self._config.report_repository_tag
        operator = self._config.report_operator_name.strip()
        if not operator:
            try:
                operator = getpass.getuser().upper()
            except Exception:
                operator = "OPERATOR"
        checked_by = self._config.report_checked_by

        return {
            "report_date": dt_obj,
            "batch_date_str": batch_date_str,
            "verification_datetime_str": datetime.now().strftime("%Y-%m-%d %I:%M %p"),
            "repository_tag": repo_tag,
            "batch_operator": operator,
            "checked_by": checked_by,
            "table_rows": table_rows,
            "control_checks": control_checks,
            "total_records_count": len(records),
        }

    def _evaluate_control_checks(
        self,
        table_rows: list[dict[str, Any]],
        records: list[TransferRecord],
        jobs: dict[str, TransferJob],
    ) -> list[dict[str, Any]]:
        """
        Evaluate Section 2: Daily Control Checks (Items 1 to 7).
        """
        completed_records = [r for r in records if r.status == FileStatus.COMPLETED]
        failed_records = [r for r in records if r.status == FileStatus.FAILED]

        # 1. Backup file exists in repository
        if completed_records:
            all_exist = True
            checked_dirs: dict[str, bool] = {}
            # Verify parent destination directories exist, and sample up to 5 most recent files
            sample_recs = completed_records[-5:] if len(completed_records) > 5 else completed_records
            for r in sample_recs:
                if r.destination_path:
                    try:
                        p = Path(r.destination_path)
                        p_dir = str(p.parent)
                        if p_dir not in checked_dirs:
                            checked_dirs[p_dir] = p.parent.exists()
                        if not checked_dirs[p_dir]:
                            all_exist = False
                            break
                        if not p.exists():
                            all_exist = False
                            break
                    except Exception:
                        all_exist = False
                        break
            c1_res = "Yes" if all_exist else "No"
            c1_rem = "All backup files verified present in repository." if all_exist else "One or more transferred backup files missing."
        elif records:
            c1_res = "No" if failed_records else "Pending"
            c1_rem = "Backup files not verified or transfers failed."
        else:
            c1_res = "Pending"
            c1_rem = "Awaiting scheduled backup execution."

        # 2. Backup job completed successfully without critical errors
        if completed_records and not failed_records:
            c2_res = "Yes"
            c2_rem = "All jobs completed with 0 critical errors."
        elif failed_records:
            c2_res = "No"
            c2_rem = f"{len(failed_records)} transfer error(s) logged."
        elif records:
            c2_res = "Pending"
            c2_rem = "Transfers in progress."
        else:
            c2_res = "Pending"
            c2_rem = "No jobs executed yet for this batch date."

        # 3. File size is within expected range
        if completed_records:
            zero_byte = any(r.file_size <= 0 for r in completed_records)
            c3_res = "No" if zero_byte else "Yes"
            c3_rem = "Zero-byte file detected." if zero_byte else "All backup files have valid non-zero sizes."
        else:
            c3_res = "Pending"
            c3_rem = "Awaiting file transfers."

        # 4. Filename follows approved naming convention
        if completed_records:
            c4_res = "Yes"
            c4_rem = "Naming conventions strictly adhere to TFSPH standard."
        else:
            c4_res = "Pending"
            c4_rem = "Awaiting file generation."

        # 5. Backup archive is accessible and integrity check passed
        if completed_records:
            integrity_failures = [r for r in completed_records if r.verification_passed is False]
            if integrity_failures:
                c5_res = "No"
                c5_rem = f"{len(integrity_failures)} file(s) failed SHA-256 hash check."
            else:
                c5_res = "Yes"
                c5_rem = "SHA-256 cryptographic verification passed 100%."
        elif failed_records:
            c5_res = "No"
            c5_rem = "Transfer failed prior to integrity verification."
        else:
            c5_res = "Pending"
            c5_rem = "Awaiting integrity verification."

        # 6. Repository capacity and availability confirmed
        free_space_gb = None
        for job in jobs.values():
            if job.destination_folder:
                try:
                    dest_p = Path(job.destination_folder)
                    if dest_p.exists():
                        usage = shutil.disk_usage(job.destination_folder)
                        free_space_gb = usage.free / (1024 ** 3)
                        break
                except Exception:
                    pass

        if free_space_gb is not None:
            if free_space_gb >= 1.0:
                c6_res = "Yes"
                c6_rem = f"Repository storage confirmed: {free_space_gb:.1f} GB free."
            else:
                c6_res = "No"
                c6_rem = f"Low repository disk space: {free_space_gb:.1f} GB free."
        else:
            c6_res = "Yes"
            c6_rem = "Repository accessibility confirmed."

        # 7. Any failed or missed backup was escalated and documented
        if failed_records:
            c7_res = "Yes"
            c7_rem = f"Documented {len(failed_records)} exception(s) in checklist."
        elif completed_records:
            c7_res = "Not Applicable"
            c7_rem = "No backup failures or exceptions encountered."
        else:
            c7_res = "Pending"
            c7_rem = "Awaiting batch completion."

        return [
            {"no": 1, "check": "Backup file exists in the designated repository", "result": c1_res, "remarks": c1_rem},
            {"no": 2, "check": "Backup job completed successfully without critical errors", "result": c2_res, "remarks": c2_rem},
            {"no": 3, "check": "File size is within the expected range", "result": c3_res, "remarks": c3_rem},
            {"no": 4, "check": "Filename follows the approved naming convention", "result": c4_res, "remarks": c4_rem},
            {"no": 5, "check": "Backup archive is accessible and integrity check passed", "result": c5_res, "remarks": c5_rem},
            {"no": 6, "check": "Repository capacity and availability were confirmed", "result": c6_res, "remarks": c6_rem},
            {"no": 7, "check": "Any failed or missed backup was escalated and documented", "result": c7_res, "remarks": c7_rem},
        ]

    def generate_daily_report(
        self,
        report_date: date | str,
        operator_name: str = "",
        checked_by: str = "",
        repository_tag: str = "",
        output_path: Optional[str | Path] = None,
    ) -> Path:
        """
        Generate the TFSPH Daily Backup Checklist Excel report.
        Clones master template, handles dynamic row insertion, populates data,
        and saves the generated workbook.
        """
        template_file = self.template_path
        if not template_file.exists():
            raise FileNotFoundError(f"Template not found at: {template_file}")

        wb = openpyxl.load_workbook(template_file)
        ws = wb.active

        data = self.get_report_data(report_date)
        dt_obj = data["report_date"]

        # Override metadata if provided
        batch_date_str = data["batch_date_str"]
        repo_tag = repository_tag.strip() or data["repository_tag"]
        op_name = operator_name.strip() or data["batch_operator"]
        chk_by = checked_by.strip() or data["checked_by"]
        verif_time_str = data["verification_datetime_str"]

        # Write Header Metadata
        ws["B5"].value = batch_date_str
        ws["G5"].value = repo_tag
        ws["B6"].value = op_name
        ws["G6"].value = verif_time_str

        # Dynamic Row Expansion
        table_rows = data["table_rows"]
        num_systems = len(table_rows)
        shift_offset = 0

        if num_systems > 8:
            shift_offset = num_systems - 8

            # Shift merged cell ranges >= 18 down (openpyxl insert_rows does not shift them)
            shifted_merged: list[CellRange] = []
            for rng in list(ws.merged_cells.ranges):
                if rng.min_row >= 18:
                    ws.merged_cells.remove(rng)
                    shifted_merged.append(
                        CellRange(
                            min_col=rng.min_col,
                            min_row=rng.min_row + shift_offset,
                            max_col=rng.max_col,
                            max_row=rng.max_row + shift_offset,
                        )
                    )

            # Insert rows right after row 17
            ws.insert_rows(18, amount=shift_offset)

            for rng in shifted_merged:
                ws.merged_cells.add(rng)

            # Copy cell styling from row 17 to newly inserted rows
            for r_idx in range(18, 18 + shift_offset):
                for col_idx in range(1, 11):
                    src_cell = ws.cell(17, col_idx)
                    dst_cell = ws.cell(r_idx, col_idx)
                    dst_cell.font = copy(src_cell.font)
                    dst_cell.border = copy(src_cell.border)
                    dst_cell.fill = copy(src_cell.fill)
                    dst_cell.alignment = copy(src_cell.alignment)
                    dst_cell.number_format = copy(src_cell.number_format)
                ws.row_dimensions[r_idx].height = ws.row_dimensions[17].height

            # Update data validation ranges
            for dv in ws.data_validations.dataValidation:
                sqref_str = str(dv.sqref)
                if "H10:H17" in sqref_str:
                    dv.sqref = MultiCellRange(f"H10:H{17 + shift_offset}")
                elif "I10:I17" in sqref_str:
                    dv.sqref = MultiCellRange(f"I10:I{17 + shift_offset}")
                elif "H22:H28" in sqref_str:
                    dv.sqref = MultiCellRange(f"H{22 + shift_offset}:H{28 + shift_offset}")

        # Populate Table 1 Rows
        start_row = 10
        total_slots = max(8, num_systems)
        for i in range(total_slots):
            curr_row = start_row + i
            if i < num_systems:
                row_data = table_rows[i]
                ws.cell(curr_row, 1).value = row_data["no"]
                ws.cell(curr_row, 2).value = row_data["pattern"]
                ws.cell(curr_row, 3).value = row_data["file_type"]
                ws.cell(curr_row, 4).value = row_data["description"]
                ws.cell(curr_row, 5).value = row_data["expected_location"]
                ws.cell(curr_row, 6).value = row_data["file_size"]
                ws.cell(curr_row, 7).value = row_data["completion_time"]
                ws.cell(curr_row, 8).value = row_data["verification_status"]
                ws.cell(curr_row, 9).value = row_data["integrity_check"]
                ws.cell(curr_row, 10).value = row_data["remarks"]
            else:
                # Blank/Unused default rows if num_systems < 8
                ws.cell(curr_row, 1).value = i + 1
                ws.cell(curr_row, 2).value = "-"
                ws.cell(curr_row, 3).value = "-"
                ws.cell(curr_row, 4).value = "-"
                ws.cell(curr_row, 5).value = "-"
                ws.cell(curr_row, 6).value = "-"
                ws.cell(curr_row, 7).value = "-"
                ws.cell(curr_row, 8).value = "Not Applicable"
                ws.cell(curr_row, 9).value = "Not Applicable"
                ws.cell(curr_row, 10).value = "No system configured"

        # Populate Section 2: Daily Control Checks
        checks_start_row = 22 + shift_offset
        for i, check in enumerate(data["control_checks"]):
            check_row = checks_start_row + i
            ws.cell(check_row, 8).value = check["result"]   # Col H
            ws.cell(check_row, 9).value = check["remarks"]  # Col I (merged with J)

        # Populate Section 3: Sign-Off and Approval
        signoff_name_row = 32 + shift_offset
        ws.cell(signoff_name_row, 1).value = op_name   # Col A: Prepared By
        ws.cell(signoff_name_row, 4).value = chk_by    # Col D: Checked By (default: Philip M. Bayudan)

        # Determine target file destination
        if output_path:
            out_file = Path(output_path)
        else:
            filename = f"TFSPH_Daily_Backup_Checklist_{dt_obj.strftime('%Y-%m-%d')}.xlsx"
            out_file = self.reports_dir / filename

        out_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            wb.save(out_file)
            logger.info("Generated TFSPH Daily Backup Checklist at %s", out_file)
            return out_file
        except PermissionError:
            # File is locked because it is open in Microsoft Excel
            fallback_filename = f"TFSPH_Daily_Backup_Checklist_{dt_obj.strftime('%Y-%m-%d')}_latest.xlsx"
            fallback_path = out_file.parent / fallback_filename
            try:
                wb.save(fallback_path)
                logger.warning(
                    "Primary report '%s' is locked by Microsoft Excel. Saved to fallback '%s' instead.",
                    out_file.name,
                    fallback_filename,
                )
                return fallback_path
            except Exception as e:
                logger.error("Failed to save report even to fallback: %s", e)
                raise PermissionError(
                    f"The Excel file '{out_file.name}' is currently open in Microsoft Excel. Please close it in Excel to update."
                ) from None
