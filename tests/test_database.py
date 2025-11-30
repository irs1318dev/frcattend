"""Test Sqlite database functionality."""

import datetime
import json
import pathlib

import pytest
import rich  # noqa: F401

from frcattend import model


DATA_FOLDER = pathlib.Path(__file__).parent / "data"


def test_empty_database(empty_database: model.DBase) -> None:
    """Create an empty IrsAttend database."""
    # Assert
    query = "SELECT name FROM sqlite_schema WHERE type = 'table';"
    with empty_database.get_db_connection() as conn:
        tables = set(row["name"] for row in conn.execute(query))
    conn.close()
    assert len(tables) == 4
    assert "students" in tables
    assert "checkins" in tables
    # Must close connection or fixtures won't be able to delete Sqlite3 file when
    #   setting up for other tests.


def test_nonexistant_database_raises_error(empty_output_folder: pathlib.Path) -> None:
    """Raise an error if a database doesn't exist."""
    # Act, Assert
    with pytest.raises(model.DBaseError):
        model.DBase(empty_output_folder / "irsattend.db")


def test_existing_database_raises_error_on_create_new(empty_database) -> None:
    """Raise an error if create_new = True and database file already exists."""
    # Act, Assert
    with pytest.raises(model.DBaseError):
        model.DBase(empty_database.db_path, create_new=True)


def test_attendance_table(full_dbase: model.DBase) -> None:
    """Attendance table has many rows and 5 columns of data."""
    # Act
    checkins = model.Checkin.get_all(full_dbase)
    # Assert
    assert len(checkins) > 4000
    assert isinstance(checkins[0], model.Checkin)


def test_attendance_counts(full_dbase: model.DBase) -> None:
    """Get count of student appearances."""
    # Act
    season_counts = model.Checkin.get_counts_by_student(
        full_dbase, datetime.date(2025, 9, 1)
    )
    build_counts = model.Checkin.get_counts_by_student(
        full_dbase, datetime.date(2026, 1, 1)
    )
    # Assert
    assert len(season_counts) >= len(build_counts)
    for student_id in build_counts:
        assert student_id in season_counts
        assert isinstance(season_counts[student_id], int)
        assert isinstance(build_counts[student_id], int)
        assert season_counts[student_id] >= build_counts[student_id]
        assert build_counts[student_id] >= 0


def test_attendance_report_data(full_dbase: model.DBase) -> None:
    """Get info for student attendance report."""
    # Act
    cursor = full_dbase.get_student_attendance_data()
    # Assert
    for row in cursor:
        rich.print(dict(row))
    cursor.connection.close()


def test_to_dict(full_dbase: model.DBase) -> None:
    """Save database contents to a JSON file."""
    # Act
    data = full_dbase.to_dict()
    # Assert
    tables = ["students", "checkins", "events"]
    assert len(data) == len(tables)
    assert all(col in data for col in tables)
    for table in tables:
        assert isinstance(data[table], list)
        assert len(data[table]) >= 10

    with open(full_dbase.db_path.parent / "testdata.json", "wt") as jfile:
        json.dump(data, jfile, indent=2)


def test_from_dict(full_dbase: model.DBase, empty_database2: model.DBase) -> None:
    """Import student data from a dictionay into an empty database."""
    # Arrange
    exported_data = full_dbase.to_dict()
    # Act
    empty_database2.load_from_dict(exported_data)
    # Assert
    students1 = model.Student.get_all(full_dbase, include_inactive=True)
    students2 = model.Student.get_all(empty_database2, include_inactive=True)
    assert len(students1) == len(students2)
    checkins1 = model.Checkin.get_all(full_dbase)
    checkins2 = model.Checkin.get_all(empty_database2)
    assert len(checkins1) == len(checkins2)


def test_add_event(noevents_dbase: model.DBase) -> None:
    """Add an event to the events table."""
    # Arrange
    edate = datetime.date(2026, 1, 10)
    desc = "Multiteam kickoff event at Auburn H.S."
    # Act
    noevents_dbase.add_event(model.EventType.KICKOFF, edate, desc)
    # Assert
    events = noevents_dbase.get_events_dict()
    assert len(events) == 1
    assert events[0]["event_type"] == model.EventType.KICKOFF
    assert events[0]["event_date"] == edate.isoformat()
    assert events[0]["description"] == desc


def test_add_duplicate_event_does_nothing(noevents_dbase: model.DBase) -> None:
    """Do not add any records to the events table when event is a duplicate."""
    # Arrange
    edate = datetime.date(2026, 1, 10)
    desc = "Multiteam kickoff event at Auburn H.S."
    noevents_dbase.add_event(model.EventType.KICKOFF, edate, desc)
    # Act
    noevents_dbase.add_event(model.EventType.KICKOFF, edate, "duplicate")
    # Assert
    events = noevents_dbase.get_events_dict()
    assert len(events) == 1
    assert events[0]["description"] == desc


def test_add_checkin(
    attendance_test_data: dict[str, list], noevents_dbase: model.DBase
) -> None:
    """Add a student checkin."""
    # Arrange
    students = attendance_test_data["students"]
    event_date = datetime.datetime(2025, 11, 15)
    noevents_dbase.add_event(model.EventType.COMPETITION, event_date, "test")
    checkin = model.Checkin(
        checkin_id=-1,
        student_id=students[0]["student_id"],
        event_type=model.EventType.COMPETITION,
        timestamp=event_date,
    )
    # Act
    checkin.add(noevents_dbase)
    # Assert
    checkins = model.Checkin.get_all(noevents_dbase)
    assert len(checkins) == 1
    assert checkins[0].student_id == students[0]["student_id"]
    assert checkins[0].event_type == model.EventType.COMPETITION
    assert checkins[0].iso_date == "2025-11-15"
