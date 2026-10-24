"""Connect to the Sqlite database and run queries."""

import dataclasses
import datetime
import json
import os
import pathlib
from collections.abc import Callable, Sequence
from typing import Any

import sqlcipher3

from frcattend import config
from frcattend.model import abstract, events_checkins, students, surveys

SQLITE_HEADER = b"SQLite format 3\x00"
"""First 16 bytes of every unencrypted Sqlite database file."""


class DBaseError(Exception):
    """Error occurred when working with database."""


class UnencryptedDBaseError(DBaseError):
    """Database file exists but is not encrypted with SQLCipher."""


def is_unencrypted(db_path: pathlib.Path) -> bool:
    """Return True if the file is a plain-text (unencrypted) Sqlite database.

    SQLCipher encrypts the entire file, including the header, so an encrypted
    file never starts with the standard Sqlite header string.
    """
    with open(db_path, "rb") as db_file:
        return db_file.read(len(SQLITE_HEADER)) == SQLITE_HEADER


def _get_escaped_key() -> str:
    """Get the configured encryption key, escaped as an SQL string literal.

    PRAGMA and ATTACH ... KEY statements do not accept bound parameters, so the
    key must be embedded in the SQL text.

    Raises:
        DBaseError: If the encryption key is not set.
    """
    key = config.settings.encryption_key
    if not key:
        raise DBaseError("The encryption_key setting is required to open the database.")
    return key.replace("'", "''")


def connect(db_path: pathlib.Path, **kwargs: Any) -> sqlcipher3.Connection:
    """Open an SQLCipher connection keyed with the configured encryption key.

    Raises:
        DBaseError: If the encryption key is not set or the key cannot
            decrypt the database file.
    """
    escaped_key = _get_escaped_key()
    conn = sqlcipher3.connect(db_path, **kwargs)
    conn.execute(f"PRAGMA key = '{escaped_key}';")
    try:
        # SQLCipher does not verify the key until the first read.
        conn.execute("SELECT count(*) FROM sqlite_schema;").fetchone()
    except sqlcipher3.DatabaseError as err:
        conn.close()
        raise DBaseError(
            f"Unable to decrypt database at {db_path}. The encryption key is "
            "incorrect or the file is not an SQLCipher database."
        ) from err
    return conn


def _get_table_counts(conn: sqlcipher3.Connection) -> dict[str, int]:
    """Get the number of rows in every user table of an open connection."""
    query = """
        SELECT name FROM sqlite_schema
         WHERE type = 'table' AND name NOT LIKE 'sqlite_%';
    """
    counts = {}
    for (name,) in conn.execute(query).fetchall():
        quoted_name = '"' + name.replace('"', '""') + '"'
        counts[name] = conn.execute(f"SELECT count(*) FROM {quoted_name};").fetchone()[
            0
        ]
    return counts


# Sqlite converts Python datetime.date and datetime.datetime objects to
#   ISO-8601-formatted strings automatically. But as of Python 3.12, this
#   behavior is deprecated, which means the Python developers will remove this
#   behavior in a future version of Python and we should stop relying on it.
# The adapter and converter functions handle the conversions between Python
#   datetime and date objects and Sqlite text strings. All columns with type
#   DATE will be converted to datetime.date objects and columns with type
#   DATETIME will be converted to datetime.datetime objects.
# NOTE: For all this to work, pass detect_types=sqlcipher3.PARSE_DECLTYPES
#   to sqlcipher3.connect method.
# See https://docs.python.org/3/library/sqlite3.html#how-to-convert-sqlite-values-to-custom-python-types


def adapt_from_date(val: datetime.date | None) -> str | None:
    """Convert dates to ISO-formatted strings for storing in Sqlite."""
    return None if val is None else val.isoformat()


def convert_to_date(val: bytes | None) -> datetime.date | None:
    """Convert Sqlite event_date strings to EventType objects."""
    if val is None:
        return None
    return datetime.datetime.fromisoformat(val.decode()).date()


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


sqlcipher3.register_adapter(datetime.date, adapt_from_date)
sqlcipher3.register_converter("DATE", convert_to_date)
sqlcipher3.register_adapter(datetime.datetime, adapt_from_datetime)
sqlcipher3.register_converter("DATETIME", convert_to_datetime)
sqlcipher3.register_converter("BOOL", convert_to_bool)


def dict_factory(cursor: sqlcipher3.Cursor, row: Sequence) -> dict[str, Any]:
    """Return Sqlite data as a dictionary."""
    fields = [column[0] for column in cursor.description]
    return {key: value for key, value in zip(fields, row)}


@dataclasses.dataclass
class DbTimeStamps:
    """Sqlite file timestamps."""

    access_time: datetime.datetime
    modification_time: datetime.datetime
    creation_time: datetime.datetime


class DBase:
    """Read and write to database."""

    db_path: pathlib.Path
    """Path to Sqlite database."""
    tables: list[type[abstract.TableDef]]
    """SQL table definitions."""

    def __init__(self, db_path: pathlib.Path, create_new: bool = False) -> None:
        """Set database path."""
        self.tables = [
            students.Student,
            students.Status,
            events_checkins.Event,
            events_checkins.Checkin,
            surveys.Survey,
            surveys.Answer,
        ]
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
            if is_unencrypted(db_path):
                raise UnencryptedDBaseError(
                    f"Database file at {db_path} is not encrypted."
                )

    @classmethod
    def encrypt_file(cls, db_path: pathlib.Path) -> DBase:
        """Encrypt an unencrypted Sqlite database file in place.

        The database is exported to a temporary SQLCipher file keyed with the
        configured encryption key. After verifying that the encrypted copy
        contains the same tables and row counts as the original, the encrypted
        copy replaces the original file.

        Returns:
            A DBase object for the newly-encrypted database file.

        Raises:
            DBaseError: If the file does not exist, is already encrypted, the
                encryption key is not set, or the encrypted copy does not match
                the original.
        """
        if not db_path.exists():
            raise DBaseError(f"Database file at {db_path} does not exist.")
        if not is_unencrypted(db_path):
            raise DBaseError(f"Database file at {db_path} is already encrypted.")
        escaped_key = _get_escaped_key()
        temp_path = db_path.with_name(db_path.name + ".encrypting")
        if temp_path.exists():
            temp_path.unlink()
        escaped_temp_path = str(temp_path).replace("'", "''")

        # A connection without a key reads the file as plain-text Sqlite.
        plain_conn = sqlcipher3.connect(db_path)
        try:
            original_counts = _get_table_counts(plain_conn)
            user_version = plain_conn.execute("PRAGMA user_version;").fetchone()[0]
            plain_conn.execute(
                f"ATTACH DATABASE '{escaped_temp_path}' AS encrypted "
                f"KEY '{escaped_key}';"
            )
            plain_conn.execute("SELECT sqlcipher_export('encrypted');")
            plain_conn.execute(f"PRAGMA encrypted.user_version = {int(user_version)};")
            plain_conn.execute("DETACH DATABASE encrypted;")
        finally:
            plain_conn.close()

        try:
            enc_conn = connect(temp_path)
            try:
                encrypted_counts = _get_table_counts(enc_conn)
            finally:
                enc_conn.close()
            if encrypted_counts != original_counts:
                raise DBaseError(
                    f"Encrypted copy of {db_path} does not match the original. "
                    "The original file was not changed."
                )
        except DBaseError:
            temp_path.unlink(missing_ok=True)
            raise
        os.replace(temp_path, db_path)
        return cls(db_path)

    def get_db_connection(self, as_dict=False) -> sqlcipher3.Connection:
        """Get connection to the encrypted database. Create DB if it doesn't exist."""
        conn = connect(self.db_path, detect_types=sqlcipher3.PARSE_DECLTYPES)
        if as_dict:
            conn.row_factory = dict_factory
        else:
            conn.row_factory = sqlcipher3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def create_tables(self) -> None:
        """Creates the database tables if they don't already exist."""
        with self.get_db_connection() as conn:
            for tabledef in self.tables:
                tabledef.create(conn)
        conn.close()

    def get_schema(self) -> dict[str, list[str]]:
        """Get information about the database's tables and columns.

        The schema does not include generated columns, like auto-incremented
        primary keys or dates that are generated from timestamps. The schema
        represents the minimum set of columns that fully defines the attendance
        dataset with no duplication.
        """
        return {
            tabledef.table_name: tabledef.get_nongenerated_columns(self)
            for tabledef in self.tables
        }

    def to_dict(self) -> dict[str, list[dict[str, str | int | None]]]:
        """Save database contents to a JSON file.

        Returns:
            Contents of the database as a Python dictionary. Format:
            {<table_name>: [{<col_name>: <col_value>}]}
        """
        db_data = {}
        db_data["students"] = [
            student.to_dict() for student in students.Student.get_all(self)
        ]
        db_data["statuses"] = [
            status.to_dict() for status in students.Status.get_all(self)
        ]
        db_data["surveys"] = [
            survey.to_dict() for survey in surveys.Survey.get_all(self)
        ]
        db_data["answers"] = [
            answer.to_dict() for answer in surveys.Answer.get_all(self)
        ]
        event_data = [event.to_dict() for event in events_checkins.Event.get_all(self)]
        excluded_columns = ["event_id", "day_of_week"]
        db_data["events"] = [
            {col: val for col, val in row.items() if col not in excluded_columns}
            for row in event_data
        ]
        db_data["checkins"] = [
            c.to_dict() for c in events_checkins.Checkin.get_all(self)
        ]
        return db_data

    def load_from_dict(self, db_data_dict: dict[str, list[dict[str, Any]]]) -> None:
        """Import data into the Sqlite database."""
        student_query = """
            INSERT INTO students
                        (student_id, first_name, last_name, email, grad_year)
                 VALUES (:student_id, :first_name, :last_name, :email, :grad_year);
        """
        statuses_query = """
            INSERT INTO statuses
                        (student_id, stage, start_date, reason, notes)
                 VALUES (:student_id, :stage, :start_date, :reason, :notes);
        """
        checkins_query = """
            INSERT INTO checkins
                        (student_id, event_type, timestamp)
                 VALUES (:student_id, :event_type, :timestamp);
        """
        event_query = """
            INSERT INTO events
                        (event_date, event_type, description)
                 VALUES (:event_date, :event_type, :description);
        """
        survey_query = """
            INSERT INTO surveys
                        (title, question, choices, multiselect,
                         allow_freetext, max_length, replace)
                 VALUES (:title, :question, :choices_json, :multiselect,
                         :allow_freetext, :max_length, :replace);
        """
        answers_query = """
                    INSERT INTO answers
                                (student_id, survey_title, answer_date,
                                choices, freetext_answer)
                        VALUES (:student_id, :survey_title, :answer_date,
                                :choices_json, :freetext_answer);
        """
        # Convert survey data to format expected by the database
        # The choices field needs to be converted to JSON for storage
        survey_data = [
            {**survey, "choices_json": json.dumps(survey["choices"])}
            for survey in db_data_dict.get("surveys", [])
        ]
        answer_data = [
            {**answer, "choices_json": json.dumps(answer["choices"])}
            for answer in db_data_dict.get("answers", [])
        ]

        with self.get_db_connection() as conn:
            conn.executemany(student_query, db_data_dict["students"])
            conn.executemany(statuses_query, db_data_dict["statuses"])
            conn.executemany(event_query, db_data_dict["events"])
        with conn:
            conn.executemany(checkins_query, db_data_dict["checkins"])
            conn.executemany(survey_query, survey_data)
            conn.executemany(answers_query, answer_data)
        conn.close()

    def get_database_file_info(self) -> DbTimeStamps:
        """Get information about the currently-selected database file."""
        file_info = os.stat(self.db_path)
        return DbTimeStamps(
            access_time=datetime.datetime.fromtimestamp(file_info.st_atime),
            modification_time=datetime.datetime.fromtimestamp(file_info.st_mtime),
            creation_time=datetime.datetime.fromtimestamp(file_info.st_birthtime),
        )

    def backup(
        self,
        pages: int = 100,
        status_callback: Callable[[int, int, int], Any] | None = None,
    ) -> pathlib.Path:
        """Backup the database file.

        Put the backup in the folder specified by the 'backup_dir' setting in
        the TOML configuration file. Or if the 'backup_dir' option isn't set,
        put the backup in the current working directory.

        Use the same filename as the curent database file, but add
        "BU_YYMMDD_HHMM"
        """
        # Set backup path and file name.
        if config.settings.backup_dir is None:
            backup_dir = pathlib.Path.cwd()
        else:
            backup_dir = config.settings.backup_dir
        backup_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("_BU_%Y%m%d_%H%M")
        backup_path = backup_dir / (self.db_path.stem + timestamp + ".db")
        # Backup the database. SQLCipher requires the backup to use the same key.
        bu_conn = connect(backup_path)
        conn = self.get_db_connection()
        conn.backup(bu_conn, pages=pages, progress=status_callback)
        bu_conn.commit()
        bu_conn.close()
        conn.close()
        return backup_path

    def get_record_counts(self) -> dict[str, int]:
        """Get number of records in each table.

        Returns:
            A dictionary with table names for keys and number of records for
            values.
        """
        return {tdef.table_name: tdef.count(self) for tdef in self.tables}

    def delete_all(self) -> None:
        """Delete all data from all tables."""
        with self.get_db_connection() as conn:
            for tdef in self.tables[::-1]:  # Delete tables in reverse order (relative
                tdef.delete_all(conn)  #   to order of creation to prvent foriegn
        conn.close()  #   key violations.
