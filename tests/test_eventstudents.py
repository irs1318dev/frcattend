"""Test EventStudent functionality."""

import datetime

import rich  # noqa: F401

from frcattend import model
from frcattend.features import events


def test_get_students_for_event(full_dbase: model.DBase) -> None:
    """Get students who attended a specific event."""
    # Arrange
    event_key = model.Event.get_all(full_dbase)[0].key
    # Act
    students = events.EventStudent.get_students_for_event(full_dbase, event_key)
    # Assert
    assert all(isinstance(sut, events.EventStudent) for sut in students)
    assert all(isinstance(sut.timestamp, datetime.datetime) for sut in students)
