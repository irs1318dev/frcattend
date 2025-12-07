"""Connect to the Sqlite database and run queries."""

from collections.abc import Sequence
import dataclasses
import datetime
import json
import os
import pathlib
import sqlite3
from typing import Any


from frcattend.model import events_checkins, students, surveys


class DBaseError(Exception):
    """Error occurred when working with database."""


# Sqlite converts Python datetime.date and datetime.datetime objects to
#   ISO-8601-formatted strings automatically. But as of Python 3.12, this
#   behavior is deprecated, which means the Python developers will remove this
#   behavior in a future version of Python and we should stop relying on it.
# The adapter and converter functions handle the conversions between Python
#   datetime and date objects and Sqlite text strings. All columns with type
#   DATE will be converted to datetime.date objects and columns with type
#   DATETIME will be converted to datetime.datetime objects.
# NOTE: For all this to work, pass detect_types=sqlite3.PARSE_DECLTYPES
#   to sqlite3.connect method.
# See https://docs.python.org/3/library/sqlite3.html#how-to-convert-sqlite-values-to-custom-python-types


def adapt_from_date(val: datetime.date | None) -> str | None:
    """Convert dates to ISO-formatted strings for storing in Sqlite."""
    return None if val is None else val.isoformat()


def convert_to_date(val: bytes | None) -> datetime.date | None:
    """Convert Sqlite event_date strings to EventType objects."""
    if val is None:
        return None
    return datetime.date.fromisoformat(val.decode())


def adapt_from_datetime(val: datetime.datetime | None) -> str | None:
    """Convert datetimes to ISO-formatted strings for storingin Sqlite."""
    return None if val is None else val.isoformat()


def convert_to_datetime(val: bytes | None) -> datetime.datetime | None:
    """convert Sqlite DATETIME columns to Python datetime objects."""
    if val is None:
        return None
    return datetime.datetime.fromisoformat(val.decode())


def convert_to_bool(val: bytes) -> bool:
    """Convert integer Sqlite columns to Python Bool objects."""
    return int(val) != 0


sqlite3.register_adapter(datetime.date, adapt_from_date)
sqlite3.register_converter("DATE", convert_to_date)
sqlite3.register_adapter(datetime.datetime, adapt_from_datetime)
sqlite3.register_converter("DATETIME", convert_to_datetime)
sqlite3.register_converter("BOOL", convert_to_bool)


def dict_factory(cursor: sqlite3.Cursor, row: Sequence) -> dict[str, Any]:
    """Return Sqlite data as a dictionary."""
    fields = [column[0] for column in cursor.description]
    return {key: value for key, value in zip(fields, row)}


@dataclasses.dataclass
class DbInfo:
    access_time: datetime.datetime
    modification_time: datetime.datetime
    creation_time: datetime.datetime


class DBase:
    """Read and write to database."""

    db_path: pathlib.Path
    """Path to Sqlite database."""

    def __init__(self, db_path: pathlib.Path, create_new: bool = False) -> None:
        """Set database path."""
        self.db_path = db_path
        if create_new:
            if self.db_path.exists():
                raise DBaseError(
                    f"Cannot create new database at {db_path}, file already exists."
                )
            else:
                self.create_tables()
        else:
            if not db_path.exists():
                raise DBaseError(f"Database file at {db_path} does not exist.")

    def get_db_connection(self, as_dict=False) -> sqlite3.Connection:
        """Get connection to the SQLite database. Create DB if it doesn't exist."""
        conn = sqlite3.connect(self.db_path, detect_types=sqlite3.PARSE_DECLTYPES)
        if as_dict:
            conn.row_factory = dict_factory
        else:
            conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def create_tables(self):
        """Creates the database tables if they don't already exist."""
        with self.get_db_connection() as conn:
            conn.execute(students.Student.table_def)
            conn.execute(surveys.Survey.table_def)
            conn.execute(events_checkins.Checkin.table_def)
            conn.execute(events_checkins.Event.table_def)
            conn.execute(students.Student.active_students_view_def)
        conn.close()

    def to_dict(self) -> dict[str, list[dict[str, str | int | None]]]:
        """Save database contents to a JSON file.

        Returns:
            Contents of the database as a Python dictionary. Format:
            {<table_name>: [{<col_name>: <col_value>}]}
        """
        db_data = {}
        db_data["students"] = [
            student.to_dict()
            for student in students.Student.get_all(self, include_inactive=True)
        ]
        db_data["surveys"] = [
            survey.to_dict() for survey in surveys.Survey.get_all(self)
        ]
        event_data = [event.to_dict() for event in events_checkins.Event.get_all(self)]
        excluded_columns = ["event_id", "day_of_week"]
        db_data["events"] = [
            {col: val for col, val in row.items() if col not in excluded_columns}
            for row in event_data
        ]
        checkins = [c.to_dict() for c in events_checkins.Checkin.get_all(self)]
        excluded_columns = ["checkin_id"]
        db_data["checkins"] = [
            {col: val for col, val in row.items() if col not in excluded_columns}
            for row in checkins
        ]
        return db_data

    def load_from_dict(
        self, db_data_dict: dict[str, list[dict[str, str | int | None]]]
    ) -> None:
        """Import data into the Sqlite database."""
        student_query = """
            INSERT INTO students
                        (student_id, first_name, last_name, email, grad_year,
                        deactivated_on)
                 VALUES (:student_id, :first_name, :last_name, :email, :grad_year,
                        :deactivated_on);
        """
        survey_query = """
            INSERT INTO surveys
                        (title, question, answers, multiselect,
                         allow_freetext, max_length)
                 VALUES (:title, :question, :answers_json, :multiselect,
                         :allow_freetext, :max_length);
        """
        checkins_query = """
            INSERT INTO checkins
                        (student_id, event_type, timestamp, inactive)
                 VALUES (:student_id, :event_type, :timestamp, :inactive);
        """
        event_query = """
            INSERT INTO events
                        (event_date, event_type, description)
                 VALUES (:event_date, :event_type, :description);
        """
        # Convert survey data to format expected by the database
        # The answers field needs to be converted to JSON for storage
        survey_data = [
            {**survey, "answers_json": json.dumps(survey["answers"])}
            for survey in db_data_dict.get("surveys", [])
        ]

        with self.get_db_connection() as conn:
            conn.executemany(student_query, db_data_dict["students"])
            conn.executemany(survey_query, survey_data)
            conn.executemany(event_query, db_data_dict["events"])
        with conn:
            conn.executemany(checkins_query, db_data_dict["checkins"])
        conn.close()

    def get_database_file_info(self) -> DbInfo:
        """Get information about the currently-selected database file."""
        file_info = os.stat(self.db_path)
        return DbInfo(
            access_time=datetime.datetime.fromtimestamp(file_info.st_atime),
            modification_time=datetime.datetime.fromtimestamp(file_info.st_mtime),
            creation_time=datetime.datetime.fromtimestamp(file_info.st_birthtime),
        )
