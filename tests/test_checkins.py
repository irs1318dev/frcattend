"""Test Sqlite checkin functionality."""

import datetime
import pathlib

import rich  # noqa: F401

from frcattend import model


DATA_FOLDER = pathlib.Path(__file__).parent / "data"


def test_add_active_checkin(full_dbase: model.DBase) -> None:
    """Add a checkin to the checkins table."""
    # Arrange
    student_ids = model.Student.get_all_ids(full_dbase, include_inactive=False)
    event = model.Event(
        datetime.date(2027, 1, 1), model.EventType.VIRTUAL, "Pytest Event"
    )
    event.add(full_dbase)
    checkin = model.Checkin(
        0,
        student_ids[-1],
        model.EventType.VIRTUAL,
        datetime.datetime(2027, 1, 1, 17, 30),
    )
    # Act
    checkin_id = checkin.add(full_dbase)
    assert checkin_id
    assert checkin.checkin_id == checkin_id
    added_checkins = model.Checkin.get_checkin_by_student_and_date(
        full_dbase,
        student_ids[-1],
        datetime.date(2027, 1, 1),
    )
    assert len(added_checkins) == 1
    added_checkin = added_checkins[0]
    assert added_checkin.checkin_id == checkin_id
    assert added_checkin.timestamp == checkin.timestamp
    assert added_checkin.inactive == checkin.inactive


def test_get_checkin_count(full_dbase: model.DBase) -> None:
    """Get number of checkins for an event."""
    # Arrange
    event = model.Event.get_all(full_dbase)[0]
    # Act
    count = model.Checkin.get_count(full_dbase, event.event_date, event.event_type)
    # Assert
    assert isinstance(count, int)
    assert count >= 0
    rich.print(f"\nCheckin count for event on {event.event_date}: {count}")


def test_checkedin_student_ids(full_dbase: model.DBase) -> None:
    """Get list of student IDs who have checked in for an event."""
    # Arrange
    event = model.Event.get_all(full_dbase)[0]
    # Act
    student_ids = model.Checkin.get_checkedin_students(
        full_dbase, event.event_date, event.event_type
    )
    # Assert
    assert all(isinstance(sid, str) for sid in student_ids)
    assert len(student_ids) >= 0
