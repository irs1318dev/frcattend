"""Test Sqlite student functionality."""

import pathlib

import rich  # noqa: F401

from frcattend import model

DATA_FOLDER = pathlib.Path(__file__).parent / "data"


def test_get_students(full_dbase: model.DBase) -> None:
    """Get events as Event objects."""
    # Act
    students = model.Student.get_all(full_dbase)
    # Assert
    assert all(isinstance(student, model.Student) for student in students)
    assert isinstance(students[0].grad_year, int)
