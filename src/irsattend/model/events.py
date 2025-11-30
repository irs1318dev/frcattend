"""Events and Checkins table definitions, queries, and dataclasss.

## Contents
* EventType: An enumeration of typical FRC team events.
* Event: A dataclass that represents an FRC event.
* Checkin: A dataclass that represents a student attending an FRC event.
* Sqlite adapter and converter functions: Configure Sqlite to automatically
    convert between text data in the event_type, event_date, and timestamp
    columns and EventType, date, and datetime objects.

## Notes
1. The day_of_week field is an integer ranging from 1 (Monday) to 7 (Sunday).
"""

import dataclasses
import datetime
import enum
import sqlite3

from typing import ClassVar, Optional, TYPE_CHECKING


if TYPE_CHECKING:
    from irsattend.model import database

class EventType(enum.StrEnum):
    """Types of events at which we take attendance."""

    COMPETITION = "competition"
    KICKOFF = "kickoff"
    MEETING = "meeting"
    NONE = "none"
    OPPORTUNITY = "opportunity"
    OUTREACH = "outreach"
    VIRTUAL = "virtual"
    VOLUNTEERING = "volunteering"


def adapt_event_type(val: EventType | str) -> str:
    """Adapt schema.EventType objects to Sqlite TEXT values."""
    if isinstance(val, EventType):
        return val.value
    return val


def convert_event_type(val: bytes) -> EventType:
    """Convert values from event_type columns to an EventType enum object."""
    return EventType(str(val))


def convert_event_date(val: bytes) -> datetime.date:
    """Convert Sqlite event_date strings to EventType objects."""
    return datetime.date.fromisoformat(str(val))


def convert_timestamp(val: bytes) -> datetime.datetime:
    """Convert Sqlite timestamp strings to datetime.datetime objects."""
    return datetime.datetime.fromisoformat(str(val))


sqlite3.register_adapter(EventType, adapt_event_type)
sqlite3.register_converter("event_type", convert_event_type)
sqlite3.register_converter("event_date", convert_event_date)
sqlite3.register_converter("timestamp", convert_timestamp)


class EventUpateError(Exception):
    """Raised when an event update fails."""
    pass


@dataclasses.dataclass
class Event:
    """An event at which we record attendance."""

    event_date: datetime.date
    event_type: EventType
    description: Optional[str]

    table_def: ClassVar[str] = """
        CREATE TABLE IF NOT EXISTS events (
            event_date TEXT NOT NULL,
           day_of_week INT GENERATED ALWAYS AS (strftime('%u', event_date)) VIRTUAL,
            event_type TEXT NOT NULL,
           description TEXT,
           PRIMARY KEY (event_date, event_type) ON CONFLICT IGNORE
        );
    """

    def __init__(
        self,
        event_date: datetime.date | str,
        event_type: str | EventType,
        description: Optional[str] = None,
    ) -> None:
        """Ensure event_date is converted to datetime.date."""
        if isinstance(event_date, str):
            event_date = datetime.date.fromisoformat(event_date)
        if isinstance(event_type, str):
            event_type = EventType(event_type)
        self.event_date = event_date
        self.event_type = event_type
        self.description = description

    @property
    def iso_date(self) -> str:
        """Event date as an iso-formatted string."""
        return self.event_date.strftime("%Y-%m-%d")

    @property
    def day_of_week(self) -> int:
        """Day of week as an integer with Monday = 1."""
        return self.event_date.weekday() + 1

    @property
    def weekday_name(self) -> str:
        """Day of week as a string: 'Monday', 'Tuesday', etc."""
        return self.event_date.strftime("%A")

    @property
    def key(self) -> str:
        """String that uniquely identifies the event."""
        return f"{self.iso_date}::{self.event_type.value}"

    def exists(self, dbase: "database.DBase") -> bool:
        """Check if the event exists in the database."""
        query = """
                SELECT 1
                  FROM events
                 WHERE event_date = ?
                   AND event_type = ?;
        """
        conn = dbase.get_db_connection()
        query_result = conn.execute(
            query, (self.event_date, self.event_type)
        ).fetchone()
        conn.close()
        return query_result is not None

    def add(self, dbase: "database.DBase") -> bool:
        """Add the event to the database.

        Return True if the event was added, False if it already existed.
        """
        query = """
                INSERT INTO events
                            (event_date, event_type, description)
                     VALUES (:event_date, :event_type, :description);
        """
        with dbase.get_db_connection() as conn:
            cursor = conn.execute(
                query,
                {
                    "event_date": self.event_date,
                    "event_type": self.event_type,
                    "description": self.description,
                },
            )
        row_count = cursor.rowcount
        conn.close()
        return row_count == 1

    def delete(self, dbase: "database.DBase") -> bool:
        """Delete the event from the database.

        Return True if the event was deleted, False if it did not exist.
        """
        query = """
                DELETE FROM events
                      WHERE event_date = :event_date
                        AND event_type = :event_type;
        """
        with dbase.get_db_connection() as conn:
            cursor = conn.execute(
                query,
                {"event_date": self.event_date, "event_type": self.event_type},
            )
        row_count = cursor.rowcount
        conn.close()
        return row_count == 1

    @staticmethod
    def select(
        dbase: "database.DBase", event_date: datetime.date, event_type: EventType
    ) -> "Event | None":
        """Retrieve a single event."""
        query = """
                SELECT event_date, event_type, description
                  FROM events
                 WHERE event_date = ?
                   AND event_type = ?;
        """
        conn = dbase.get_db_connection(as_dict=True)
        query_result = conn.execute(
            query, (event_date.strftime("%Y-%m-%d"), event_type)
        ).fetchone()
        event = None if query_result is None else Event(**query_result)
        conn.close()
        return event

    @staticmethod
    def get_all(dbase: "database.DBase") -> list["Event"]:
        """Retrieve a list of Student objects from the database."""
        query = """
                SELECT event_date, event_type, description
                  FROM events
              ORDER BY event_date, event_type;
        """
        conn = dbase.get_db_connection(as_dict=True)
        events = [Event(**event) for event in conn.execute(query)]
        conn.close()
        return events
    
    def update_description(
        self, dbase: "database.DBase", description: str | None
    ) -> None:
        """Update the event in the database."""
        if self.description == description:
            return
        else:
            self.description = description
        query = """
                UPDATE events
                   SET description = :description
                 WHERE event_type = :event_type AND event_date = :event_date;
        """
        with dbase.get_db_connection() as conn:
            conn.execute(
                query,
                {
                    "event_date": self.event_date,
                    "event_type": self.event_type,
                    "description": description,
                },
            )
        conn.close()

    def update_event_type(self, dbase: "database.DBase", new_type: EventType) -> int:
        """Update the event type in the database.

        Returns:
          Number of checkins updated.

        Raises:
          EventUpdateError: If the update could not be performed.
        """
        if self.event_type == new_type:
            # Do nothing if the event_type hasn't changed.
            return 0
        if not self.exists(dbase):
            raise EventUpateError("Original event does not exist.")
        event_query = """
                UPDATE events
                   SET event_type = :new_type
                 WHERE event_type = :event_type AND event_date = :event_date;
        """
        checkins_query = """
                UPDATE checkins
                   SET event_type = :new_type
                 WHERE event_date = :event_date
                   AND event_type = :event_type;
        """
        params = {
                    "new_type": new_type,
                    "event_type": self.event_type,
                    "event_date": self.event_date
        }
        with dbase.get_db_connection() as conn:
            conn.execute(event_query, params)
            cursor = conn.execute(checkins_query, params)
            checkins_updated = cursor.rowcount
        conn.close()
        self.event_type = new_type
        return checkins_updated

    def update_event_date(
        self, dbase: "database.DBase", new_date: datetime.date
    ) -> None:
        """Update the event date in the database.

        Raises:
          EventUpdateError: If the update could not be performed.
        """
        if self.event_date == new_date:
            # Do nothing if the date hasn't changed.
            return
        if not self.exists(dbase):
            raise EventUpateError("Original event does not exist.")
        checkin_counts = Checkin.get_count(dbase, self.event_date, self.event_type)
        if checkin_counts > 0:
            raise EventUpateError("Cannot change date; checkins exist for this event.")
        event_query = """
                UPDATE events
                   SET event_date = :new_date
                 WHERE event_type = :event_type AND event_date = :event_date;
        """
        params = {
            "new_date": new_date,
            "event_date": self.event_date,
            "event_type": self.event_type,
        }
        with dbase.get_db_connection() as conn:
            conn.execute(event_query, params)
        conn.close()
        self.event_date = new_date


@dataclasses.dataclass
class Checkin:
    checkin_id: int
    student_id: str
    event_type: EventType
    timestamp: datetime.datetime

    table_def: ClassVar[str] = """
        CREATE TABLE IF NOT EXISTS checkins (
            checkin_id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT NOT NULL,
            event_date TEXT GENERATED ALWAYS AS (date(timestamp)) VIRTUAL,
           day_of_week INT GENERATED ALWAYS AS (strftime('%u', event_date)) VIRTUAL,
            event_type TEXT,
             timestamp TEXT NOT NULL,
           FOREIGN KEY (student_id) REFERENCES students (student_id),
           FOREIGN KEY (event_date, event_type)
                       REFERENCES events (event_date, event_type)
                       DEFERRABLE INITIALLY DEFERRED,
            CONSTRAINT single_event_constraint UNIQUE(student_id, event_date, event_type)
        );
    """
    # DEFERRABLE INITIALLY DEFERRED allows queries to create foreign key violations
    # within a transaction, as long as the violations are fixed before the end of the
    # transaction. See section 4.2 of https://sqlite.org/foreignkeys.html

    def __init__(
        self,
        checkin_id: int,
        student_id: str,
        event_type: str | EventType,
        timestamp: datetime.datetime | str,
    ) -> None:
        """Ensure timestamp is converted to datetime.datetime."""
        if isinstance(timestamp, str):
            timestamp = datetime.datetime.fromisoformat(timestamp)
        if isinstance(event_type, str):
            event_type = EventType(event_type)
        self.checkin_id = checkin_id
        self.student_id = student_id
        self.event_type = event_type
        self.timestamp = timestamp

    @property
    def event_date(self) -> datetime.date:
        """Date of the event as a datetime.date object."""
        return self.timestamp.date()

    @property
    def day_of_week(self) -> int:
        """Day of week as an integer with Monday = 1."""
        return self.event_date.weekday() + 1

    @staticmethod
    def to_iso_date(date: datetime.date) -> str:
        """Convert a datetime.date to an iso-formatted string."""
        return date.strftime("%Y-%m-%d")

    @property
    def iso_date(self) -> str:
        """Event date as an iso-formatted string."""
        return self.to_iso_date(self.event_date)

    def add(self, dbase: "database.DBase") -> int | None:
        """Add the checkin record to the database.

        Returns:
            The checkin ID of the newly added record, or None if the insert
            failed.
        """
        query = """
                INSERT INTO checkins
                            (student_id, event_type, timestamp)
                     VALUES (:student_id, :event_type, :timestamp);
        """
        with dbase.get_db_connection() as conn:
            cursor = conn.execute(
                query,
                {
                    "student_id": self.student_id,
                    "event_type": self.event_type.value,
                    "timestamp": self.timestamp,
                },
            )
            checkin_id = cursor.lastrowid
        conn.close()
        return checkin_id

    @staticmethod
    def get_all(dbase: "database.DBase") -> list["Checkin"]:
        """Retrieve a list of Checkin objects from the database."""
        query = """
                SELECT checkin_id, student_id, event_type, timestamp
                  FROM checkins
              ORDER BY timestamp;
        """
        conn = dbase.get_db_connection(as_dict=True)
        checkins = [Checkin(**checkin) for checkin in conn.execute(query)]
        conn.close()
        return checkins

    @classmethod
    def get_checkedin_students(
        cls,
        dbase: "database.DBase",
        event_date: datetime.date,
        event_type: EventType,
    ) -> list[str]:
        """Get a list of student IDs who checked in for a given event."""
        query = """
                SELECT student_id
                  FROM checkins
                 WHERE event_date = ?
                   AND event_type = ?;
        """
        conn = dbase.get_db_connection()
        student_ids = [
            row["student_id"] for row in conn.execute(query, (event_date, event_type))
        ]
        conn.close()
        return student_ids

    @staticmethod
    def get_counts_by_student(
        dbase: "database.DBase", since: datetime.date
    ) -> dict[str, int]:
        """Get a dictionary of student IDs and their checkin counts."""
        conn = dbase.get_db_connection()
        cursor = conn.execute(
            """
                SELECT student_id, COUNT(student_id) as checkins
                  FROM checkins
                 WHERE timestamp >= ?
              GROUP BY student_id
              ORDER BY student_id;
        """,
            (since,),
        )
        counts = {row["student_id"]: row["checkins"] for row in cursor.fetchall()}
        conn.close()
        return counts

    @staticmethod
    def get_count(
        dbase: "database.DBase", event_date: datetime.date, event_type: EventType
    ) -> int:
        """Count the number of checkins for a given event."""
        query = """
                SELECT COUNT(*) AS checkin_count
                  FROM checkins
                 WHERE event_date = ?
                   AND event_type = ?;
        """
        conn = dbase.get_db_connection()
        query_result = conn.execute(
            query, (event_date.strftime("%Y-%m-%d"), event_type)
        ).fetchone()
        conn.close()
        return query_result["checkin_count"]

    def to_dict(self) -> dict:
        """Convert the Checkin dataclass to a JSON-serializable dictionary."""
        return {
            "checkin_id": self.checkin_id,
            "student_id": self.student_id,
            "event_type": self.event_type,
            "timestamp": self.timestamp.isoformat(),
        }

