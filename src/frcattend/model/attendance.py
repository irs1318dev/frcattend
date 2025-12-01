"""Define methods based on multiple tables."""

import sqlite3

from frcattend import config
from frcattend import model




class Attendance:
    """Manage multi-table queries ana analysis."""

    @staticmethod
    def get_student_attendance_data(dbase: model.DBase) -> sqlite3.Cursor:
        """Join students and checkins table and get current season data.
        
        Caller must close the cursor.
        """
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
                       COALESCE(y.checkins, 0) AS year_checkins,
                       COALESCE(b.checkins, 0) AS build_checkins,
                       y.last_checkin
                  FROM active_students AS s
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
