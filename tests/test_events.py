"""Test Sqlite event functionality."""

import pathlib
import datetime

import rich  # noqa: F401

from irsattend import model
from irsattend.features import events


DATA_FOLDER = pathlib.Path(__file__).parent / "data"


def test_get_events(full_dbase: model.DBase) -> None:
    """Get events as Event objects."""
    # Act
    events = model.Event.get_all(full_dbase)
    # Assert
    assert all(isinstance(evt, model.Event) for evt in events)
    assert isinstance(events[0].day_of_week, int)
    assert 1 <= events[0].day_of_week <= 7


def test_select_event(full_dbase: model.DBase) -> None:
    """Select a single event by date and type and handle missing event."""
    # Arrange
    expected_event = model.Event.get_all(full_dbase)[-1]
    # Act
    event = model.Event.select(
        full_dbase, expected_event.event_date, expected_event.event_type
    )
    # Assert
    assert isinstance(event, model.Event)
    assert event.event_type == expected_event.event_type.value
    assert event.event_date == expected_event.event_date


def test_select_missing_event(full_dbase: model.DBase) -> None:
    """Select a non-existent event."""
    # Act
    event = model.Event.select(
        full_dbase, datetime.date(2019, 12, 31), model.EventType.OUTREACH
    )
    # Assert
    assert event is None


def test_update_event_description(full_dbase: model.DBase) -> None:
    """Change a record in the events table."""
    # Arrange
    event_to_update = model.Event.get_all(full_dbase)[0]
    key_date = event_to_update.event_date
    key_type = event_to_update.event_type
    assert event_to_update.event_type == model.EventType.MEETING
    assert event_to_update.description is None
    # Act
    event_to_update.update_description(full_dbase, "Test Opportunity")
    updated_event = model.Event.select(full_dbase, key_date, key_type)
    # Assert
    assert updated_event is not None
    assert updated_event.description == "Test Opportunity"


def test_event_attendance(full_dbase: model.DBase) -> None:
    """Get event attendance data."""
    # Act
    event_checkins = events.CheckinEvent.get_checkin_events(full_dbase)
    # Assert
    assert len(event_checkins) > 20
    assert all(isinstance(event, events.CheckinEvent) for event in event_checkins)


def test_add_duplicate_event(full_dbase: model.DBase) -> None:
    """Add an event to the database."""
    # Arrange
    dupe_event = model.Event.get_all(full_dbase)[0]
    # Act, Assert
    assert not dupe_event.add(full_dbase)  # Returns False if event already exists.


def test_add_new_event(full_dbase: model.DBase) -> None:
    """Add a new event to the database."""
    # Arrange
    new_event = model.Event(
        event_date=datetime.date(2024, 12, 25),
        event_type=model.EventType.OUTREACH,
        description="Christmas Outreach",
    )
    # Act, Assert
    assert new_event.add(full_dbase)  # Returns True if event was added.
    assert (
        model.Event.select(
            full_dbase, datetime.date(2024, 12, 25), model.EventType.OUTREACH
        )
        is not None
    )


def test_event_exists(full_dbase: model.DBase) -> None:
    """Check existence of an event in the model."""
    # Arrange
    existing_event = model.Event.get_all(full_dbase)[0]
    missing_event = model.Event(
        event_date=datetime.date(2025, 1, 1),
        event_type=model.EventType.MEETING,
        description="New Year Meeting",
    )
    # Act, Assert
    assert existing_event.exists(full_dbase)
    assert not missing_event.exists(full_dbase)


def test_update_event_date(full_dbase: model.DBase) -> None:
    """Update the date of an existing event."""
    # Arrange
    event_to_update = model.Event(
        datetime.date(2024, 1, 15),
        model.EventType.NONE,
        description="Test Event for Date Update",
    )
    event_to_update.add(full_dbase)
    old_date = event_to_update.event_date
    new_date = old_date + datetime.timedelta(days=1)
    # Act
    event_to_update.update_event_date(full_dbase, new_date)
    # Assert
    assert event_to_update.event_date == new_date
    assert event_to_update.exists(full_dbase)


def test_update_event_type(full_dbase: model.DBase) -> None:
    """Update the type of an existing event."""
    # Arrange
    event_to_update = model.Event.get_all(full_dbase)[0]
    event_to_update.add(full_dbase)
    new_type = model.EventType.COMPETITION
    assert (
        model.Checkin.get_count(full_dbase, event_to_update.event_date, new_type)
        == 0
    )
    # Act
    checkins_updated = event_to_update.update_event_type(full_dbase, new_type)
    # Assert
    assert event_to_update.event_type == new_type
    assert event_to_update.exists(full_dbase)
    assert checkins_updated >= 0
    assert (
        model.Checkin.get_count(full_dbase, event_to_update.event_date, new_type)
        == checkins_updated
    )
