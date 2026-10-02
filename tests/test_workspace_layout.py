"""Resize regressions for controls, job selector and table viewport."""
from PySide6.QtCore import QPoint
from core.models import TransferJob, TransferRecord, FileStatus
from gui.dashboard import DashboardWidget


def test_workspace_resize_retains_controls_and_all_records(qapp):
    widget = DashboardWidget()
    job = TransferJob(name='Long job name for batch operators', source_folder='C:/demo/' + 'very-long-folder/' * 12,
                      destination_folder='C:/destination/' + 'very-long-folder/' * 12)
    widget.update_job_list([job], job.id)
    widget.update_job_info(job)
    records = [TransferRecord(file_name=f'backup-{i}.dmp', job_id=job.id, status=FileStatus.COMPLETED,
                              batch_date='2026-09-30') for i in range(10)]
    widget.set_records(records)
    widget.show()
    try:
        for width, height in [(1200, 660), (900, 530), (1200, 660), (1000, 600)]:
            widget.resize(width, height)
            widget.update_statistics({'COMPLETED': 10})
            for _ in range(4):
                qapp.processEvents()
            assert widget.width() == width
            assert widget.height() == height
            assert widget.job_combo.height() >= 32
            assert widget.transfer_table._proxy.rowCount() == 10
            assert widget.transfer_table._table.viewport().height() >= 100
            for button in (widget._btn_start, widget._btn_stop, widget._btn_sync, widget._btn_transfer_batch):
                position = button.mapTo(widget, QPoint(0, 0))
                assert position.y() >= 0
                assert position.y() + button.height() <= widget.height()
                assert button.height() >= 32
    finally:
        widget.close()
