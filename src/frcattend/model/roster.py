"""Tools for working with Google documents."""

import datetime
import json
import pathlib
import sqlite3
from typing import Any, Optional
import yaml

from google.oauth2 import service_account
import gspread
import gspread.utils

from frcattend import model


# TODO: Check attendance name from roster.
# TODO: Provide command-line feedback to user.


class RosterError(Exception):
    """Error when attempting to update student roster."""


class SheetUpdater:
    """Connect to and update Google Sheet roster."""

    spreadsheet: gspread.spreadsheet.Spreadsheet
    """Google spreadsheet that holds student roster."""
    roster_sheet: gspread.worksheet.Worksheet
    """Worksheet that contains the roster information."""
    sheet_key: str
    """Alpha-numeric string that uniquely identifies Google Sheet."""
    roster_sheet_name: str
    """Name of worksheet that contains the roster table."""
    header_row: int
    """Index number of worksheet row with column labels.
    
    First row in worksheet is row 1.
    """
    column_map: dict[str, str]
    """Map of field names (dict key)"""
    dbase: model.DBase
    """Sqlite database that contains student attendance data."""
    _credentials: service_account.Credentials
    """Information required to connect to Google Sheet roster."""
    _client: gspread.Client
    """An object that's used to connect to Google accounts."""

    def __init__(
        self, config_path: pathlib.Path, dbase: pathlib.Path | model.DBase
    ) -> None:
        """Initialize from settings in config file."""
        with open(config_path) as config_file:
            settings = yaml.safe_load(config_file)
        self._credentials = self._get_credentials(settings["google_service_account"])
        self.sheet_key = settings["roster_sheet_key"]
        self.roster_sheet_name = settings["sheet_name"]
        self.header_row = settings["header_row"]
        self.column_map = settings["column_map"]
        self.client = gspread.authorize(self._credentials)
        self.spreadsheet = self.client.open_by_key(self.sheet_key)
        self.roster_sheet = self.spreadsheet.worksheet(self.roster_sheet_name)
        if isinstance(dbase, pathlib.Path):
            self.dbase = model.DBase(dbase)
        else:
            self.dbase = dbase
        self.backup_folder = pathlib.Path(settings["backup_folder"])

    @property
    def worksheet_titles(self) -> list[str]:
        """List of worksheet titles."""
        return [sheet.title for sheet in self.spreadsheet.worksheets()]

    @property
    def mapped_sheet(self) -> gspread.worksheet.Worksheet:
        """Worksheet identified in the column map."""
        return self.spreadsheet.worksheet(self.roster_sheet_name)

    @property
    def mapped_header_row(self):
        """Column labels in the header row of the mapped worksheet."""
        return self.mapped_sheet.row_values(self.header_row)

    @staticmethod
    def _get_credentials(
        account_data: str | dict[str, str],
    ) -> service_account.Credentials:
        """Load Google service account credientials from the database."""
        if isinstance(account_data, str):
            account_data = json.loads(account_data)
        credentials = service_account.Credentials.from_service_account_info(
            account_data
        )
        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive",
        ]
        return credentials.with_scopes(scope)

    def get_mapped_col_number(self, field_name: str) -> Optional[int]:
        """Column number that maps to field."""
        col_number = None
        col_label = self.column_map[field_name]
        if col_label is not None:
            try:
                col_number = self.mapped_header_row.index(col_label) + 1
            except ValueError:
                pass
        return col_number

    def get_mapped_col_data(self, field_name: str) -> Optional[list[Any]]:
        """Get column values"""
        col_num = self.get_mapped_col_number(field_name)
        if col_num is None:
            return None
        else:
            col_values = (self.mapped_sheet.col_values(col_num))[self.header_row :]
            return [v.strip() if isinstance(v, str) else v for v in col_values]

    def get_mapped_col_ref(self, field_name: str, length: int) -> Optional[str]:
        """A1 reference that maps to field's first data row."""
        col_number = self.get_mapped_col_number(field_name)
        if col_number is not None:
            col_top = self.rowcol_to_a1(self.header_row + 1, col_number)
            col_bot = self.rowcol_to_a1(self.header_row + length, col_number)
            return f"{col_top}:{col_bot}"
        else:
            return None

    def rowcol_to_a1(self, row: int, col: int) -> str:
        """Convert row and column numbers to A1 spreadsheet notation."""
        return gspread.utils.rowcol_to_a1(row, col)

    def _get_student_ids_from_database(self) -> dict[tuple[str, str, int], str]:
        """Get student IDs as a dict.

        Dict keys are a tuple with <last_name>, <first_name>, <grad_year>.
        Dictionary values are student IDs.
        """
        student_ids: dict[tuple[str, str, int], str] = {}
        for s in model.Student.get_all(self.dbase, include_inactive=True):
            student_ids[(s.last_name, s.first_name, s.grad_year)] = s.student_id
        return student_ids

    def insert_student_ids(self) -> None:
        """Insert student IDs into the roster's student identifier column."""
        student_ids = self._get_student_ids_from_database()
        roster_lnames = self.get_mapped_col_data("last_name")
        roster_fnames = self.get_mapped_col_data("first_name")
        roster_gyears = self.get_mapped_col_data("grad_year")
        roster_ids = []
        if roster_lnames is None or roster_fnames is None or roster_gyears is None:
            raise RosterError("Unable to read data from Google roster")
        for last_name, first_name, grad_year in zip(
            roster_lnames, roster_fnames, roster_gyears
        ):
            key = (last_name, first_name, int(grad_year))
            student_id = student_ids.get(key)
            roster_ids.append(student_id)
        roster_id_ref = self.get_mapped_col_ref("student_id", len(roster_ids))
        batch_data = [{"range": roster_id_ref, "values": [[id_] for id_ in roster_ids]}]
        self.roster_sheet.batch_update(batch_data)

    def insert_attendance_info(self) -> None:
        """Insert attendance data into the Google Sheet roster."""
        roster_ids = self.get_mapped_col_data("student_id")
        if roster_ids is None:
            return
        cursor = model.Attendance.get_student_attendance_cursor(self.dbase)
        attendance_info = {
            stu["student_id"]: (stu["year_checkins"], stu["build_checkins"])
            for stu in cursor
        }
        cursor.connection.close()
        year_checkins = []
        build_checkins = []
        for student_id in roster_ids:
            if student_id in attendance_info:
                checkins = attendance_info[student_id]
                year_checkins.append([checkins[0]])
                build_checkins.append([checkins[1]])
            else:
                year_checkins.append([None])
                build_checkins.append([None])
        season_ref = self.get_mapped_col_ref("school_year_checkins", len(roster_ids))
        build_ref = self.get_mapped_col_ref("build_season_checkins", len(roster_ids))
        batch_data = [
            {"range": season_ref, "values": year_checkins},
            {"range": build_ref, "values": build_checkins},
        ]
        self.roster_sheet.batch_update(batch_data)

    def backup_database_file(self) -> None:
        """Copy the attendance database and save to a folder."""
        # filename includes timestamp in YYYYMMDD_HHMM format
        now = datetime.datetime.now().strftime("%Y%m%d_%H%M")
        backup_path = self.backup_folder / f"attendance-backup-{now}.sqlite3"
        source_conn = self.dbase.get_db_connection()
        target_conn = sqlite3.connect(backup_path)
        source_conn.backup(target_conn)
        source_conn.close()
        target_conn.close()
