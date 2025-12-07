"""Test Sqlite student functionality."""

import datetime
import pathlib

import rich  # noqa: F401

from frcattend import model

DATA_FOLDER = pathlib.Path(__file__).parent / "data"


def test_get_students(full_dbase: model.DBase) -> None:
    """Get events as Event objects."""
    # Act
    students = model.Student.get_all(full_dbase, include_inactive=True)
    # Assert
    assert all(isinstance(student, model.Student) for student in students)
    assert isinstance(students[0].grad_year, int)
    assert isinstance(students[0].deactivated_on, datetime.date)
