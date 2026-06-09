"""Student table definition."""

import dataclasses
import datetime
import enum
import random
import re
import sqlite3
from typing import ClassVar, Optional, TYPE_CHECKING

from frcattend.model import abstract

if TYPE_CHECKING:
    from frcattend.model import database


class Stage(enum.StrEnum):
    """Allowed student stages."""
    PROSPECT = "prospect"
    """A new student who has commenced fall training."""
    FORMER_PROSPECT = "former_prospect"
    """Student who did not complete fall training or chose not to join team."""
    MEMBER = "member"
    """Completed membership requirements and joined the team for build season."""
    FORMER_MEMBER = "former_member"
    """Former member with limited participation (e.g., never lettered, just one year)."""
    ALUMNI = "alumni"
    """Former member with significant participation (had a role, lettered, etc.)"""

    valid_reasons: ClassVar[dict["Stage", list["Reason"]]] 
    """Maps each stage to the Reason values that are valid for it."""


class Reason(enum.StrEnum):
    """Reasons for a student for being in a specific stage."""
    CHOICE = "choice"
    """Student chose to leave team (FORMER_PROSPECT, FORMER_MEMBER, ALUMNI)."""
    GRADUATED = "graduated"
    """Left team due to graduating from IHS (FORMER_MEMBER, ALUMNI)."""
    INCOMPLETE = "incomplete"
    """Did not complete fall trainining (FORMER_PROSPECT, FORMER_MEMBER)."""
    TRANSFERRED = "transferred"
    """Transferred to different school (FORMER_PROSPECT, FORMER_MEMBER, ALUMNI)."""


Stage.valid_reasons = {
    Stage.PROSPECT: [],
    Stage.FORMER_PROSPECT: [Reason.CHOICE, Reason.INCOMPLETE, Reason.TRANSFERRED],
    Stage.MEMBER: [],
    Stage.FORMER_MEMBER: [
        Reason.CHOICE, Reason.INCOMPLETE, Reason.TRANSFERRED, Reason.GRADUATED
    ],
    Stage.ALUMNI: [Reason.CHOICE, Reason.GRADUATED, Reason.TRANSFERRED],
}


def adapt_stage(val: Stage | str) -> str:
    """Adapt Status objects to Sqlite TEXT values."""
    if isinstance(val, Stage):
        return val.value
    return val


def convert_status(val: bytes) -> Stage:
    """Convert values from status column to an Status enum object."""
    return Stage(val.decode())


sqlite3.register_adapter(Stage, adapt_stage)
sqlite3.register_converter("STAGE", convert_status)


def adapt_reason(val: Reason | str) -> str:
    """Adapt Reason objects to Sqlite TEXT values."""
    if isinstance(val, Reason):
        return val.value
    return val


def convert_reason(val: bytes) -> Reason:
    """Convert values from reason column to an Reason enum object."""
    return Reason(val.decode())


sqlite3.register_adapter(Reason, adapt_reason)
sqlite3.register_converter("REASON", convert_reason)


@dataclasses.dataclass
class Status(abstract.TableDef):
    """Status of an FRC Student."""

    status_id: int
    student_id: str
    stage: Stage
    start_date: datetime.date
    reason: Optional[Reason] = None
    notes: Optional[str] = None

    table_name: ClassVar[str] = "statuses"
    table_def: ClassVar[str] = """
        CREATE TABLE IF NOT EXISTS statuses (
                  status_id INTEGER PRIMARY KEY AUTOINCREMENT,
                 student_id TEXT NOT NULL,
                      stage STAGE NOT NULL,
                 start_date DATE,
                     reason REASON,
                      notes TEXT,
                FOREIGN KEY (student_id) REFERENCES students (student_id)
        );
    """

    def add(self, dbase: "database.DBase") -> int:
        """Add the status record to the database.

        Returns:
            The status_id of the newly added record.
        """
        query = """
                INSERT INTO statuses
                            (student_id, stage, start_date, reason, notes)
                     VALUES (:student_id, :stage, :start_date, :reason, :notes);
        """
        conn = dbase.get_db_connection()
        try:
            with conn:
                cursor = conn.execute(
                    query,
                    {
                        "student_id": self.student_id,
                        "stage": self.stage,
                        "start_date": self.start_date,
                        "reason": self.reason,
                        "notes": self.notes,
                    },
                )
            status_id = cursor.lastrowid
        finally:
            conn.close()
        self.status_id = 0 if status_id is None else status_id
        return self.status_id


    def update(self, dbase: "database.DBase") -> None:
        """Update the status record in the database."""
        query = """
                UPDATE statuses
                   SET stage = :stage,
                       start_date = :start_date,
                       reason = :reason,
                       notes = :notes
                 WHERE status_id = :status_id;
        """
        with dbase.get_db_connection() as conn:
            conn.execute(
                query,
                {
                    "status_id": self.status_id,
                    "stage": self.stage,
                    "start_date": self.start_date,
                    "reason": self.reason,
                    "notes": self.notes,
                },
            )
        conn.close()

    @staticmethod
    def get_by_status_id(dbase: "database.DBase", status_id: int) -> "Status":
        """Retrieve a single status record."""
        query = """
                  SELECT status_id, student_id, stage, start_date, reason, notes
                  FROM statuses
                 WHERE status_id = ?;
        """
        conn = dbase.get_db_connection(as_dict=True)
        status = Status(**conn.execute(query, [status_id]).fetchone())
        conn.close()
        return status

    @staticmethod
    def get_by_student_id(dbase: "database.DBase", student_id: str) -> "list[Status]":
        """Retrieve list of Status objects for specific student."""
        query = """
                SELECT status_id, student_id, stage, start_date, reason, notes
                  FROM statuses
                 WHERE student_id = ?
              ORDER BY start_date DESC;
        """
        conn = dbase.get_db_connection(as_dict=True)
        statuses = [
            Status(**status) for status in conn.execute(query, [student_id])
        ]
        conn.close()
        return statuses


    def to_dict(self) -> dict:
        """Convert the Status dataclass to a dictionary."""
        return {
            "student_id": self.student_id,
            "stage": str(self.stage),
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "reason": str(self.reason) if self.reason else None,
            "notes": self.notes,
        }

    @staticmethod
    def get_all(dbase: "database.DBase") -> list["Status"]:
        """Retrieve a list of Student objects from the database."""
        query = """
                SELECT status_id, student_id, stage, start_date, reason, notes
                  FROM statuses
              ORDER BY student_id, start_date;
        """
        conn = dbase.get_db_connection(as_dict=True)
        statuses = [Status(**status) for status in conn.execute(query)]
        conn.close()
        return statuses

@dataclasses.dataclass
class Student(abstract.TableDef):
    """An FRC student."""

    student_id: str
    first_name: str
    last_name: str
    grad_year: int
    email: str
    deactivated_on: Optional[datetime.date]

    table_name: ClassVar[str] = "students"
    table_def: ClassVar[str] = """
        CREATE TABLE IF NOT EXISTS students (
                student_id TEXT PRIMARY KEY,
                first_name TEXT NOT NULL,
                 last_name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                 grad_year INTEGER NOT NULL,
            deactivated_on DATE
        );
    """
    active_students_view_def: ClassVar[str] = """
        CREATE VIEW IF NOT EXISTS active_students AS
            SELECT student_id, first_name, last_name, grad_year, email, deactivated_on
              FROM students
             WHERE deactivated_on IS NULL;
    """

    _underscore_pattern: ClassVar[re.Pattern] = re.compile(r"[\s\-]+")
    """Replace whitespace and dashes with an underscore."""
    _remove_pattern: ClassVar[re.Pattern] = re.compile(r"[.!?;,:']+")
    """Remove punctuation."""

    def __init__(
        self,
        student_id: str,
        first_name: str,
        last_name: str,
        grad_year: int,
        email: str,
        deactivated_on: Optional[datetime.date | str] = None,
    ) -> None:
        """Ensure deactivated_on is converted to datetime.date if needed.

        Pass an empty string to student_id to auto-generate a unique ID.
        """
        self.student_id = (
            student_id
            if student_id
            else self.generate_unique_student_id(first_name, last_name, grad_year)
        )
        match deactivated_on:
            case None:
                self.deactivated_on = None
            case str():
                self.deactivated_on = datetime.date.fromisoformat(deactivated_on)
            case datetime.date():
                self.deactivated_on = deactivated_on
        self.first_name = first_name
        self.last_name = last_name
        self.grad_year = grad_year
        self.email = email

    @property
    def deactivated_iso(self) -> Optional[str]:
        """Deactivation date as an iso-formatted string, or None."""
        if self.deactivated_on is None:
            return None
        else:
            return self.deactivated_on.isoformat()

    @classmethod
    def create(cls, conn: sqlite3.Connection) -> None:
        """Create the table and other associated items (views, indexes, etc.)."""
        super().create(conn)
        conn.execute(cls.active_students_view_def)

    @classmethod
    def _clean_name(cls, name: str) -> str:
        """Replace dashes and spaces with an underscore and remove punctuation."""
        name = cls._remove_pattern.sub("", name)
        return cls._underscore_pattern.sub("_", name)

    @classmethod
    def generate_unique_student_id(
        cls, first_name: str, last_name: str, grad_year: int
    ) -> str:
        """Generate a unique 8-digit student ID."""
        first_name = cls._clean_name(first_name)
        last_name = cls._clean_name(last_name)
        return (
            f"{last_name.strip().lower()}-{first_name.strip().lower()}"
            f"-{grad_year}-{random.randint(1, 999):03}"
        )

    def add(self, dbase: "database.DBase") -> None:
        """Add the Student to the database."""
        query = """
                INSERT INTO students
                            (student_id, first_name, last_name, grad_year, email,
                            deactivated_on)
                     VALUES (:student_id, :first_name, :last_name, :grad_year,
                            :email, :deactivated_on);
        """
        with dbase.get_db_connection() as conn:
            conn.execute(
                query,
                {
                    "student_id": self.student_id,
                    "first_name": self.first_name,
                    "last_name": self.last_name,
                    "grad_year": self.grad_year,
                    "email": self.email,
                    "deactivated_on": self.deactivated_iso,
                },
            )
        conn.close()

    def update(self, dbase: "database.DBase") -> None:
        """Update the Student in the database."""
        query = """
                UPDATE students
                   SET first_name = :first_name,
                       last_name = :last_name,
                       grad_year = :grad_year,
                       email = :email,
                       deactivated_on = :deactivated_on
                 WHERE student_id = :student_id;
        """
        with dbase.get_db_connection() as conn:
            conn.execute(
                query,
                {
                    "student_id": self.student_id,
                    "first_name": self.first_name,
                    "last_name": self.last_name,
                    "grad_year": self.grad_year,
                    "email": self.email,
                    "deactivated_on": self.deactivated_iso,
                },
            )
        conn.close()

    @staticmethod
    def get_all(
        dbase: "database.DBase",
        include_inactive: bool = False,
    ) -> list["Student"]:
        """Retrieve a list of Student objects from the database."""
        table_name = "students" if include_inactive else "active_students"
        query = f"""
                SELECT student_id, last_name, first_name, grad_year, email,
                       deactivated_on
                  FROM {table_name}
              ORDER BY student_id;
        """
        conn = dbase.get_db_connection(as_dict=True)
        students = [Student(**student) for student in conn.execute(query)]
        conn.close()
        return students

    @staticmethod
    def get_by_id(dbase: "database.DBase", student_id: str) -> "Student | None":
        """Retrieve a Student object by student_id."""
        query = """
                SELECT student_id, last_name, first_name, grad_year, email,
                       deactivated_on
                  FROM students
                 WHERE student_id = ?;
        """
        conn = dbase.get_db_connection(as_dict=True)
        result = conn.execute(query, (student_id,)).fetchone()
        conn.close()
        if result is None:
            return None
        return Student(**result)

    @staticmethod
    def get_all_ids(
        dbase: "database.DBase", include_inactive: bool = False
    ) -> list[str]:
        """Retrieve a list of all student IDs from the database."""
        query = """
                SELECT student_id
                  FROM students
              ORDER BY student_id;
        """
        conn = dbase.get_db_connection()
        student_ids = [row["student_id"] for row in conn.execute(query)]
        conn.close()
        return student_ids

    def to_dict(self) -> dict:
        """Convert the Student dataclass to a dictionary."""
        return {
            "student_id": self.student_id,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "grad_year": self.grad_year,
            "email": self.email,
            "deactivated_on": self.deactivated_iso,
        }

    @staticmethod
    def summary(dbase: "database.DBase") -> dict[str, int]:
        """Get the number of active students in the attenance system."""
        query = """
            WITH totals AS (
                SELECT count(*) AS total,
                       count(deactivated_on) AS deactivated
                  FROM students
                )
            SELECT total, (total - deactivated) AS active, deactivated
            FROM totals;
            """
        conn = dbase.get_db_connection()
        row = conn.execute(query).fetchone()
        result = {
            "total": row["total"],
            "active": row["active"],
            "deactivated": row["deactivated"],
        }
        conn.close()
        return result
