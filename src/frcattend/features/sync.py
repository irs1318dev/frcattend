"""Tools for working with Google documents."""

import datetime
import enum
import json
import pathlib
import sqlite3
from typing import Any, Optional
import yaml

from google.oauth2 import service_account
import gspread
import gspread.utils

from frcattend import config, model


# TODO: Check attendance name from roster.
# TODO: Provide command-line feedback to user.


class SynchronizerError(Exception):
    """Error when attempting to update student roster."""

    class ErrorType(enum.Enum):
        """Types of errors."""

        ACCESS_DENIED = enum.auto()
        MISSING_TABLE = enum.auto()
        COLUMN_MISMATCH = enum.auto()

    error_type: ErrorType
    """Type of error."""

    def __init__(self, error_type: ErrorType, message: str) -> None:
        """Specify error type on initialization."""
        super().__init__(message)
        self.error_type = error_type


class GoogleWorkbook:
    """Connect to a Google Workbook."""

    spreadsheet: gspread.spreadsheet.Spreadsheet
    """Google spreadsheet that holds student roster."""
    roster_sheet: gspread.worksheet.Worksheet
    """Worksheet that contains the roster information."""
    sheet_key: str
    """Alpha-numeric string that uniquely identifies Google Sheet."""
    _credentials: service_account.Credentials
    """Information required to connect to Google Sheet roster."""
    _client: gspread.Client
    """An object that's used to connect to Google accounts."""

    def __init__(self, sheet_key: str) -> None:
        """Initialize from settings in config file."""
        if config.settings.google_service_account is None:
            error = config.ConfigError(
                "google_service_account undefined in config TOML file. "
                "Cannot connect to Google workbook.",
                config.ConfigError.ErrorType.UNDEFINED_SETTING,
            )
            error.settings.append("google_service_account")
            raise error
        self._credentials = self._get_credentials(
            config.settings.google_service_account
        )
        self.sheet_key = sheet_key
        self.client = gspread.authorize(self._credentials)
        try:
            self.spreadsheet = self.client.open_by_key(self.sheet_key)
        except PermissionError:
            raise SynchronizerError(
                SynchronizerError.ErrorType.ACCESS_DENIED,
                "Permission Error when accessing workheet.",
            )

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

    @property
    def worksheet_titles(self) -> list[str]:
        """List of worksheet titles."""
        return [sheet.title for sheet in self.spreadsheet.worksheets()]

    def rowcol_to_a1(self, row: int, col: int) -> str:
        """Convert row and column numbers to A1 spreadsheet notation."""
        return gspread.utils.rowcol_to_a1(row, col)


class Synchronizer:
    """Upload and download data to and from Google workbook."""

    workbook: GoogleWorkbook
    """Google workbook that contains attendance data."""
    dbase: model.DBase
    """Sqlite database that contains student attendance data."""
    schema: dict[str, list[str]]
    """Table names and columns."""

    def __init__(self) -> None:
        """Connect to Google workbook identifyed in sync_sheet_key setting."""
        if config.settings.db_path is None:
            error = config.ConfigError(
                "db_path is undefined in config TOML file. Cannot connect to database.",
                config.ConfigError.ErrorType.UNDEFINED_SETTING,
            )
            error.settings.append("db_path")
            raise error
        if config.settings.sync_sheet_key is None:
            error = config.ConfigError(
                "sync_sheet_key undefined in config TOML file. "
                "Cannot connect to Google workbook.",
                config.ConfigError.ErrorType.UNDEFINED_SETTING,
            )
            error.settings.append("sync_sheet_key")
            raise error
        self.dbase = model.DBase(config.settings.db_path)
        self.workbook = GoogleWorkbook(config.settings.sync_sheet_key)
        self.schema = self.dbase.get_schema()

    def add_log_sheet(self) -> None:
        """Add a worksheet to log activities."""
        if "log" not in self.workbook.worksheet_titles:
            self.workbook.spreadsheet.add_worksheet("log", rows=10, cols=10)

    def upload(self) -> dict[str, int]:
        """Upload all attendance data to a Google spreadsheet.

        Returns:
            A dictionary of table names and the number of rows written for each
            table.
        """
        db_data = self.dbase.to_dict()
        return self.write_data_to_workbook(db_data)

    def write_data_to_workbook(
        self, db_data: dict[str, list[dict[str, Any]]]
    ) -> dict[str, int]:
        """Write attendance data to a Google workbook.

        Args:
            db_data: A dictionary produced by
                frcattend.model.database.DBase.to_dict(). Every key is a table
                name and every value is a list of table rows. Each row is a
                row-oritented dictionary with format
                {column_name: column_value}.

        Returns:
            A dictionary of table names and the number of rows written for each
            table.
        """
        return {
            table_name: self.write_table_to_sheet(table_name, table_data)
            for table_name, table_data in db_data.items()
        }

    def write_table_to_sheet(
        self, table_name: str, table_data: list[dict[str, Any]]
    ) -> int:
        """Write a database table to a Google Sheets worksheet.

        Args:
            table_name: The name of the SQL table with the data that will be
                written to the Google sheet.
            table_data: The data from the SQL table, as a row-oriented list of
                dictionaries of the form {col_name: col_value}.

        Returns:
            The number of rows of data that are written to the sheet.

        ### Assumptions
        * Every row of table_data contains all columns. No rows have missing
          columns.
        * Every field value in table_data is JSON-serializable.
        """
        col_names = self.schema[table_name]
        sheet_data: list[list[Any] | dict[str, Any]] = [col_names]
        for row in table_data:
            sheet_data.append(
                [
                    json.dumps(row[col_name])
                    if isinstance(row[col_name], (list, dict))
                    else row[col_name]
                    for col_name in col_names
                ]
            )
        if table_name in self.workbook.worksheet_titles:
            current_sheet = self._backup_and_clear_sheet(table_name)
        else:
            current_sheet = self.workbook.spreadsheet.add_worksheet(
                table_name, rows=len(table_data), cols=len(col_names)
            )
        current_sheet.update(sheet_data)
        return len(sheet_data)

    def _backup_and_clear_sheet(self, table_name: str) -> gspread.Worksheet:
        """Backup existing sheet with title table_name and clear contents."""
        current_sheet = self.workbook.spreadsheet.worksheet(table_name)
        backup_sheet_name = table_name + "_bu"
        if backup_sheet_name in self.workbook.worksheet_titles:
            self.workbook.spreadsheet.del_worksheet(
                self.workbook.spreadsheet.worksheet(backup_sheet_name)
            )
        self.workbook.spreadsheet.duplicate_sheet(
            current_sheet.id, new_sheet_name=backup_sheet_name
        )
        current_sheet.clear()
        return current_sheet

    def download(self) -> dict[str, list[dict[str, Any]]]:
        """Read all sheets in the workbook.

        Returns:
            A dictionary of the format
            {table_name: list[{column_name: value, ...}], ...}.

        Raises:
            SynchronizerError with error_type = ErrorType.COLUMN_MISMATCH
            if downloaded table names and columns don't match database schema.
        """
        wb_data: dict[str, list[dict[str, Any]]] = {}
        for table_name, columns in self.schema.items():
            wb_data[table_name] = self.read_sheet(table_name)
            schema_columns = set(columns)
            wb_columns = set(self.schema[table_name])
            if wb_columns != schema_columns:
                raise SynchronizerError(
                    SynchronizerError.ErrorType.COLUMN_MISMATCH,
                    f"Google sheet columns do not match schema for {table_name} table. "
                    f"Missing sheet columns: ({schema_columns - wb_columns}). "
                    f"Extra sheet columns: ({wb_columns - schema_columns}).",
                )
        return wb_data

    @staticmethod
    def count_rows(wb_data: dict[str, list[dict[str, Any]]]) -> dict[str, int]:
        """Get count of records in each table."""
        return {table_name: len(rows) for table_name, rows in wb_data.items()}

    @staticmethod
    def time_of_last_change(
        wb_data: dict[str, list[dict[str, Any]]],
    ) -> datetime.datetime | None:
        """Get date and time of most recent checkin in attendace dataset.

        Assumes checkin data is sorted in ascending order.
        """
        checkins = wb_data["checkins"]
        if checkins is None or len(checkins) == 0:
            return None
        else:
            return datetime.datetime.fromisoformat(checkins[-1]["timestamp"])

    def read_sheet(self, table_name: str) -> list[dict[str, Any]]:
        """Read the worksheet with title equal to table_name.

        Returns:
            A list of row-oritented dictionaries, where each dictionary is one
            row and the Google worksheet and has the format
            {column_name: value}.

        ### Assumptions
        * The title of the worksheet exactly matches the SQL table name.
        * Row 1 of the google sheet contains column headers.
        * The column headers exactly match the SQL table column names.
        """
        if table_name not in self.workbook.worksheet_titles:
            raise SynchronizerError(
                SynchronizerError.ErrorType.MISSING_TABLE,
                f"Table {table_name} is missing from Google workbook.",
            )
        worksheet = self.workbook.spreadsheet.worksheet(table_name)
        ws_data = worksheet.get_all_records(default_blank=None)
        return self._convert_bools(ws_data)

    def _convert_bools(self, table_data: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Convert "TRUE", and "FALSE" values from Google sheet to Booleans."""
        for index, row in enumerate(table_data):
            for col_name, val in row.items():
                match str(val):
                    case "TRUE" | "True" | "true":
                        table_data[index][col_name] = True
                    case "FALSE" | "False" | "false":
                        table_data[index][col_name] = False
        return table_data

    def clear_all_sheets(self) -> None:
        """Remove all worksheets from the spreadsheet."""
        self.add_log_sheet()
        for sheet in self.workbook.spreadsheet.worksheets():
            if sheet.title == "log":
                continue
            self.workbook.spreadsheet.del_worksheet(sheet)


class RosterUpdater:
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
        for s in model.Student.get_all(self.dbase):
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
            raise SynchronizerError(
                SynchronizerError.ErrorType.COLUMN_MISMATCH,
                "Unable to read data from Google roster",
            )
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
