"""Test Sqlite checkin functionality."""

import pathlib

import rich  # noqa: F401

from frcattend import model


DATA_FOLDER = pathlib.Path(__file__).parent / "data"


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
