"""Tools for working with Google documents."""

import dataclasses
import datetime
import enum
import json
import os
import pathlib
import re
import shutil
import tempfile
from typing import Any

import boto3
import gspread
import gspread.utils
import sqlcipher3
import yaml
from botocore.client import BaseClient
from google.oauth2 import service_account

from frcattend import config, model

# TODO: Check attendance name from roster.
# TODO: Provide command-line feedback to user.

BUCKET_NAME = "irs-attendance"
DB_OBJECT_PREFIX = "frcattend-"
DB_OBJECT_SUFFIX = ".db"
DB_OBJECT_TIME_FORMAT = "%Y_%m_%d_%H_%M_%S"
DB_OBJECT_PATTERN = re.compile(
    rf"^{re.escape(DB_OBJECT_PREFIX)}(\d+)-"
    rf"(\d{{4}}_\d{{2}}_\d{{2}}_\d{{2}}_\d{{2}}_\d{{2}}){re.escape(DB_OBJECT_SUFFIX)}$"
)
"""Matches database object keys in format frcattend-N-YYYY_MM_DD_HH_MM_SS.db."""


@dataclasses.dataclass(frozen=True)
class DbObject:
    """Database file in object storage, with info parsed from its key."""

    key: str
    """Object key (i.e., file name)."""
    checkin_id: int
    """Largest checkin_id in the database file's checkins table."""
    timestamp: datetime.datetime
    """Modification time of the database file when it was uploaded."""

    @classmethod
    def from_key(cls, key: str) -> DbObject | None:
        """Parse an object key, or return None if it isn't a database file key."""
        match = DB_OBJECT_PATTERN.match(key)
        if match is None:
            return None
        try:
            timestamp = datetime.datetime.strptime(
                match.group(2), DB_OBJECT_TIME_FORMAT
            )
        except ValueError:
            return None
        return cls(key=key, checkin_id=int(match.group(1)), timestamp=timestamp)


def get_db_objects(keys: list[str]) -> list[DbObject]:
    """Parse database object keys, newest first. Unparseable keys are skipped.

    Sorted by largest checkin_id, then by latest timestamp.
    """
    db_objects = [obj for key in keys if (obj := DbObject.from_key(key)) is not None]
    return sorted(
        db_objects, key=lambda obj: (obj.checkin_id, obj.timestamp), reverse=True
    )


def get_default_db_object(db_objects: list[DbObject]) -> DbObject | None:
    """The database file with both the largest checkin_id and latest timestamp.

    Returns None if there are no files, or if the file with the largest
    checkin_id is not the file with the latest timestamp. In that case, the
    user needs to decide which file to download.
    """
    if not db_objects:
        return None
    max_checkin_id = max(obj.checkin_id for obj in db_objects)
    latest = max(obj.timestamp for obj in db_objects)
    candidates = [
        obj
        for obj in db_objects
        if obj.checkin_id == max_checkin_id and obj.timestamp == latest
    ]
    return candidates[0] if candidates else None


class SynchronizerError(Exception):
    """Error when attempting to update student roster."""

    class ErrorType(enum.Enum):
        """Types of errors."""

        ACCESS_DENIED = enum.auto()
        DUPLICATE_UPLOAD = enum.auto()

    error_type: ErrorType
    """Type of error."""

    def __init__(self, error_type: ErrorType, message: str) -> None:
        """Specify error type on initialization."""
        super().__init__(message)
        self.error_type = error_type


class Synchronizer:
    """Upload and download sqlite files from the cloud."""

    dbase: model.DBase

    def __init__(self) -> None:
        """Specify the database that will be synchronized."""
        if config.settings.db_path is None:
            raise config.ConfigError(
                "db_path setting is missing",
                config.ConfigError.ErrorType.UNDEFINED_SETTING,
            )
        self.dbase = model.DBase(config.settings.db_path)

    def upload(self, force: bool = False) -> str:
        """Upload a copy of the database to cloud object storage.

        The uploaded file is named frcattend-N-YYYY_MM_DD_HH_MM_SS.db, where N
        is the largest checkin_id in the checkins table and the timestamp is
        the database file's modification time. Unless force is True, the
        upload is refused if a file with the same name is already in the
        bucket. Returns the uploaded object key.
        """
        client = self._get_s3_client()
        checkin_index = self._get_max_checkin_id()
        modified = datetime.datetime.fromtimestamp(self.dbase.db_path.stat().st_mtime)
        object_key = (
            f"{DB_OBJECT_PREFIX}{checkin_index}-"
            f"{modified.strftime('%Y_%m_%d_%H_%M_%S')}{DB_OBJECT_SUFFIX}"
        )
        if not force and self._object_exists(client, object_key):
            raise SynchronizerError(
                SynchronizerError.ErrorType.DUPLICATE_UPLOAD,
                f"{object_key} has already been uploaded to cloud storage.",
            )
        with tempfile.TemporaryDirectory() as temp_dir:
            copy_path = pathlib.Path(temp_dir) / object_key
            source_conn = self.dbase.get_db_connection()
            target_conn = model.connect(copy_path)
            source_conn.backup(target_conn)
            source_conn.close()
            target_conn.close()
            client.upload_file(str(copy_path), BUCKET_NAME, object_key)  # type: ignore
        return object_key

    def list_uploads(self) -> list[str]:
        """Keys of all database files in the bucket, sorted by name."""
        client = self._get_s3_client()
        paginator = client.get_paginator("list_objects_v2")  # type: ignore
        keys = [
            obj["Key"]
            for page in paginator.paginate(Bucket=BUCKET_NAME, Prefix=DB_OBJECT_PREFIX)
            for obj in page.get("Contents", [])
        ]
        return sorted(keys)

    def download(self, object_key: str) -> pathlib.Path:
        """Replace the local database with a database file from object storage.

        The current database file is backed up first. The downloaded file is
        verified to be a database that can be decrypted with the configured
        encryption key before it overwrites the current database file. If any
        step fails, the current database file is not changed. Returns the path
        to the backup file.
        """
        client = self._get_s3_client()
        backup_path = self.backup_database_file()
        db_path = self.dbase.db_path
        temp_path = db_path.with_name(db_path.name + ".downloading")
        temp_path.unlink(missing_ok=True)
        try:
            client.download_file(BUCKET_NAME, object_key, str(temp_path))  # type: ignore
            # Raises DBaseError if file is unencrypted or has a different key.
            downloaded = model.DBase(temp_path)
            conn = downloaded.get_db_connection()
            try:
                conn.execute("SELECT MAX(checkin_id) FROM checkins;").fetchone()
            except sqlcipher3.DatabaseError as err:
                raise model.DBaseError(
                    f"{object_key} is not a valid attendance database."
                ) from err
            finally:
                conn.close()
            os.replace(temp_path, db_path)
        finally:
            temp_path.unlink(missing_ok=True)
        return backup_path

    def backup_database_file(self) -> pathlib.Path:
        """Copy the database file, appending 'backup' and a timestamp to its name.

        The copy goes in the folder specified by the backup_dir setting, or in
        the same folder as the database file if backup_dir isn't set. Returns
        the path to the backup file.
        """
        db_path = self.dbase.db_path
        backup_dir = config.settings.backup_dir or db_path.parent
        backup_dir.mkdir(parents=True, exist_ok=True)
        now = datetime.datetime.now().strftime(DB_OBJECT_TIME_FORMAT)
        backup_path = backup_dir / f"{db_path.stem}-backup-{now}{db_path.suffix}"
        shutil.copy2(db_path, backup_path)
        return backup_path

    @staticmethod
    def _get_s3_client() -> BaseClient:
        """Connect to S3-compatible object storage using configured credentials."""
        required = {
            "s3_url": config.settings.s3_url,
            "s3_access_key_id": config.settings.s3_access_key_id,
            "s3_secret_access_key": config.settings.s3_secret_access_key,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            error = config.ConfigError(
                f"{', '.join(missing)} undefined in config TOML file. "
                "Cannot connect to cloud storage.",
                config.ConfigError.ErrorType.UNDEFINED_SETTING,
            )
            error.settings.extend(missing)
            raise error
        return boto3.client(
            "s3",
            endpoint_url=config.settings.s3_url,
            aws_access_key_id=config.settings.s3_access_key_id,
            aws_secret_access_key=config.settings.s3_secret_access_key,
            region_name="auto",  # Required by Cloudflare R2.
        )

    def _get_max_checkin_id(self) -> int:
        """Largest checkin_id in the local database, or 0 if no checkins."""
        conn = self.dbase.get_db_connection()
        row = conn.execute("SELECT MAX(checkin_id) FROM checkins;").fetchone()
        conn.close()
        return 0 if row[0] is None else row[0]

    @staticmethod
    def _object_exists(client: BaseClient, object_key: str) -> bool:
        """True if an object with exactly this key is in the bucket."""
        response = client.list_objects_v2(  # type: ignore
            Bucket=BUCKET_NAME, Prefix=object_key, MaxKeys=1
        )
        return any(obj["Key"] == object_key for obj in response.get("Contents", []))


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


class RosterUpdaterError(Exception):
    """Error when attempting to update the Google Sheet roster."""

    class ErrorType(enum.Enum):
        """Types of errors."""

        COLUMN_MISMATCH = enum.auto()

    error_type: ErrorType
    """Type of error."""

    def __init__(self, error_type: ErrorType, message: str) -> None:
        """Specify error type on initialization."""
        super().__init__(message)
        self.error_type = error_type


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

    def get_mapped_col_number(self, field_name: str) -> int | None:
        """Column number that maps to field."""
        col_number = None
        col_label = self.column_map[field_name]
        if col_label is not None:
            try:
                col_number = self.mapped_header_row.index(col_label) + 1
            except ValueError:
                pass
        return col_number

    def get_mapped_col_data(self, field_name: str) -> list[Any] | None:
        """Get column values"""
        col_num = self.get_mapped_col_number(field_name)
        if col_num is None:
            return None
        else:
            col_values = (self.mapped_sheet.col_values(col_num))[self.header_row :]
            return [v.strip() if isinstance(v, str) else v for v in col_values]

    def get_mapped_col_ref(self, field_name: str, length: int) -> str | None:
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
            raise RosterUpdaterError(
                RosterUpdaterError.ErrorType.COLUMN_MISMATCH,
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
        target_conn = model.connect(backup_path)
        source_conn.backup(target_conn)
        source_conn.close()
        target_conn.close()
