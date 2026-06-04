"""Test Sqlite student functionality."""

import datetime
import pathlib
import sqlite3

import pytest

import rich  # noqa: F401

from frcattend import model

DATA_FOLDER = pathlib.Path(__file__).parent / "data"


def test_get_students(full_dbase: model.DBase) -> None:
    """Get students as Student objects."""
    # Act
    students = model.Student.get_all(full_dbase, include_inactive=True)
    # Assert
    assert all(isinstance(student, model.Student) for student in students)
    assert isinstance(students[0].grad_year, int)
    assert isinstance(students[0].deactivated_on, datetime.date)


def test_add_status(full_dbase: model.DBase) -> None:
    """Add a status for a student."""
    # Arrange
    student_id = "al_farsi-omar-2029-343"
    initial_count = len(model.Status.get_by_student_id(full_dbase, student_id))
    status = model.Status(
        status_id=0,
        student_id=student_id,
        stage=model.Stage.MEMBER,
        start_date=datetime.date(2026, 1, 15),
        reason=None,
        notes=None,
    )
    # Act
    status.add(full_dbase)
    # Assert
    statuses = model.Status.get_by_student_id(full_dbase, student_id)
    assert len(statuses) == initial_count + 1
    assert statuses[0].stage == model.Stage.MEMBER


def test_add_status_with_reason(full_dbase: model.DBase) -> None:
    """Add a status with a reason."""
    # Arrange
    student_id = "ahmed-daniel-2026-118"
    initial_count = len(model.Status.get_by_student_id(full_dbase, student_id))
    note = "Did not submit application"
    status = model.Status(
        status_id=0,
        student_id=student_id,
        stage=model.Stage.FORMER_PROSPECT,
        start_date=datetime.date(2026, 1, 15),
        reason=model.Reason.INCOMPLETE,
        notes=note,
    )
    # Act
    status.add(full_dbase)
    # Assert
    statuses = model.Status.get_by_student_id(full_dbase, student_id)
    assert len(statuses) == initial_count + 1
    assert statuses[0].stage == model.Stage.FORMER_PROSPECT
    assert statuses[0].reason == model.Reason.INCOMPLETE
    assert statuses[0].notes == note


def test_add_status_invalid_student_id(full_dbase: model.DBase) -> None:
    """Add a status with an invalid student_id."""
    # Arrange
    status = model.Status(
        status_id=0,
        student_id="nonexistent-student-id",
        stage=model.Stage.MEMBER,
        start_date=datetime.date(2026, 1, 15),
        reason=None,
        notes=None,
    )
    # Act / Assert
    with pytest.raises(sqlite3.IntegrityError):
        status.add(full_dbase)
