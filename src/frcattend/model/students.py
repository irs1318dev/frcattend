"""Student table definition."""

import dataclasses
import datetime
import random
import re
from typing import ClassVar, Optional, TYPE_CHECKING


if TYPE_CHECKING:
    from frcattend.model import database

@dataclasses.dataclass
class Student:
    """An FRC student."""

    student_id: str
    first_name: str
    last_name: str
    grad_year: int
    email: str
    deactivated_on: Optional[datetime.date]

    table_def: ClassVar[str] = """
        CREATE TABLE IF NOT EXISTS students (
                student_id TEXT PRIMARY KEY,
                first_name TEXT NOT NULL,
                 last_name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                 grad_year INTEGER NOT NULL,
            deactivated_on TEXT
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
        if isinstance(deactivated_on, str):
            deactivated_on = datetime.date.fromisoformat(deactivated_on)
        self.student_id = (
            student_id
            if student_id
            else self.generate_unique_student_id(first_name, last_name, grad_year)
        )
        self.first_name = first_name
        self.last_name = last_name
        self.grad_year = grad_year
        self.email = email
        self.deactivated_on = deactivated_on

    @property
    def deactivated_iso(self) -> Optional[str]:
        """Deactivation date as an iso-formatted string, or None."""
        if self.deactivated_on is None:
            return None
        return self.deactivated_on.isoformat()

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
