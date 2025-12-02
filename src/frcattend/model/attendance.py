"""Define methods based on multiple tables."""

import dataclasses
import datetime
import sqlite3
from typing import Optional

from frcattend import config
from frcattend import model


@dataclasses.dataclass
class AttendanceStudent(model.Student):
    """Student record with attendance totals."""

    year_checkins: int
    build_checkins: int

    def __init__(
        self,
        student_id: str,
        first_name: str,
        last_name: str,
        grad_year: int,
        email: str,
        year_checkins: int,
        build_checkins: int,
        last_checkin: datetime.date,
        deactivated_on: Optional[datetime.date | str] = None,
    ) -> None:
        """A student record with checkin totals for the current season."""
        self.year_checkins = year_checkins
        self.build_checkins = build_checkins
        self.last_checkin = last_checkin
        super().__init__(
            student_id, first_name, last_name, grad_year, email, deactivated_on
        )


class Attendance:
    """Manage multi-table queries ana analysis."""

    @staticmethod
    def get_student_attendance_cursor(
        dbase: model.DBase, include_inactive: bool = False
    ) -> sqlite3.Cursor:
        """Join students and checkins table and get current season data.

        Caller must close the cursor.
        """
        relation = "students" if include_inactive else "active_students"
        # An 'app' is an appearance.
        query = """
                WITH year_checkins AS (
                    SELECT student_id, COUNT(student_id) as checkins,
                           MAX(event_date) as last_checkin
                      FROM checkins
                     WHERE timestamp >= :year_start
                  GROUP BY student_id
                ),
                build_checkins AS (
                    SELECT student_id, COUNT(student_id) as checkins
                      FROM checkins
                     WHERE timestamp >= :build_start
                  GROUP BY student_id
                )
                SELECT s.student_id, s.last_name, s.first_name, s.grad_year,
                       s.email, s.deactivated_on,
                       COALESCE(y.checkins, 0) AS year_checkins,
                       COALESCE(b.checkins, 0) AS build_checkins,
                       y.last_checkin
                  FROM students AS s
             LEFT JOIN year_checkins AS y
                    ON y.student_id = s.student_id
             LEFT JOIN build_checkins AS b
                    ON b.student_id = s.student_id
              ORDER BY last_name, first_name;
        """
        conn = dbase.get_db_connection()
        cursor = conn.execute(
            query,
            {
                "year_start": config.settings.schoolyear_start_date,
                "build_start": config.settings.buildseason_start_date,
            },
        )
        return cursor

    @classmethod
    def get_student_attendance_students(
        cls, dbase: model.DBase, include_inactive: bool = False
    ) -> list[AttendanceStudent]:
        """Get a list of AttendanceStudent objects."""
        cursor = cls.get_student_attendance_cursor(dbase)
        students = [AttendanceStudent(**dict(row)) for row in cursor]
        cursor.connection.close()
        return students
