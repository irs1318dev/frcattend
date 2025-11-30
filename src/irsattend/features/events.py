"""Bind events to the user interface (view)."""

import dataclasses
import datetime
from typing import Optional

from irsattend import model


@dataclasses.dataclass
class CheckinEvent(model.Event):
    """Event with total number of students who checkedin."""

    checkin_count: int
    """Number of students who checked in at the event."""

    def __init__(
        self,
        event_date: datetime.date | str,
        event_type: str | model.EventType,
        checkin_count: int,
        description: Optional[str] = None,
    ) -> None:
        """Convert event-date and event_type if needed."""
        self.checkin_count = checkin_count
        super().__init__(event_date, event_type, description)

    @staticmethod
    def get_checkin_events(dbase: model.DBase) -> list["CheckinEvent"]:
        """Retrieve a events with number of students attending."""
        query = """
                WITH event_attendance AS (
                        SELECT event_date, day_of_week, event_type,
                               count(student_id) AS checkin_count
                          FROM checkins
                      GROUP BY event_date, day_of_week, event_type
                )
                SELECT a.event_date,
                       COALESCE(e.event_type, a.event_type) AS event_type,
                       a.checkin_count,
                       e.description
                  FROM event_attendance AS a
             LEFT JOIN events AS e
                    ON a.event_date = e.event_date AND
                       a.event_type = e.event_type
              ORDER BY a.event_date DESC;
        """
        conn = dbase.get_db_connection(as_dict=True)
        events = [CheckinEvent(**event) for event in conn.execute(query)]
        conn.close()
        return events


@dataclasses.dataclass
class EventStudent(model.Student):
    """Students who have checked in at a specific event."""

    event_key: str
    timestamp: str

    @staticmethod
    def get_students_for_event(
        dbase: model.DBase, event_key: str
    ) -> list["EventStudent"]:
        """Retrieve students who attended the specified event."""
        event_date, event_type = tuple(event_key.split("::"))
        query = """
                SELECT s.student_id, s.first_name, s.last_name, s.grad_year, s.email,
                       c.timestamp, s.deactivated_on
                    FROM events e
                LEFT JOIN checkins c
                    ON c.event_date = e.event_date
                    AND c.event_type = e.event_type
            INNER JOIN students s
                    ON s.student_id = c.student_id
                    WHERE e.event_date = ?
                    AND e.event_type = ?
            ORDER BY s.student_id;
        """
        conn = dbase.get_db_connection(as_dict=True)
        students = [
            EventStudent(event_key=event_key, **student)
            for student in conn.execute(query, (event_date, event_type))
        ]
        conn.close()
        return students
