"""Export attendance data to an Excel file."""

import dataclasses
import pathlib
from typing import Any

import xlsxwriter

from frcattend import model
from frcattend.features import events


def write(dbase: model.DBase, excel_path: pathlib.Path) -> None:
    """Write all data to a Microsoft Excel file."""
    workbook = xlsxwriter.Workbook(excel_path)
    attendance_data = dbase.to_dict()
    _write_sheet(workbook, "Students", attendance_data["students"])
    _write_sheet(workbook, "Events", attendance_data["events"])
    student_totals = [
        dict(row) for row in model.Attendance.get_student_attendance_cursor(dbase)
    ]
    _write_sheet(workbook, "Attendance by Student", student_totals)
    event_totals = events.CheckinEvent.get_checkin_events(dbase)
    _write_sheet(
        workbook,
        "Attendance by Event",
        [dataclasses.asdict(event) for event in event_totals],
    )
    _write_sheet(workbook, "Check-ins", attendance_data["checkins"])
    workbook.close()


def _write_sheet(
    workbook: xlsxwriter.Workbook, sheet_name: str, data: list[dict[str, Any]]
) -> None:
    """Write a table of data to a worksheet."""
    sheet = workbook.add_worksheet(sheet_name)
    sheet.write_row(row=0, col=0, data=list(data[0].keys()))
    for row_number, row_values in enumerate(data):
        sheet.write_row(row=row_number + 1, col=0, data=list(row_values.values()))
