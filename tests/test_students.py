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
    students = model.Student.get_all(full_dbase)
    # Assert
    assert all(isinstance(student, model.Student) for student in students)
    assert isinstance(students[0].grad_year, int)


def test_add_status(full_dbase: model.DBase) -> None:
    """Add a status for a student."""
    # Arrange
    student_id = "bakr-salma-2026-946"
    initial_count = len(model.Status.get_by_student_id(full_dbase, student_id))
    status = model.Status(
        status_id=0,
        student_id=student_id,
        stage=model.Stage.ALUMNI,
        start_date=datetime.date(2026, 6, 15),
        reason=None,
        notes=None,
    )
    # Act
    status.add(full_dbase)
    # Assert
    statuses = model.Status.get_by_student_id(full_dbase, student_id)
    assert len(statuses) == initial_count + 1
    assert statuses[0].stage == model.Stage.ALUMNI


def test_add_status_with_reason(full_dbase: model.DBase) -> None:
    """Add a status with a reason."""
    # Arrange
    student_id = "barakat-aliyah-2028-637"
    initial_count = len(model.Status.get_by_student_id(full_dbase, student_id))
    note = "Did not submit application"
    status = model.Status(
        status_id=0,
        student_id=student_id,
        stage=model.Stage.FORMER_MEMBER,
        start_date=datetime.date(2026, 5, 1),
        reason=model.Reason.TRANSFERRED,
        notes=note,
    )
    # Act
    status.add(full_dbase)
    # Assert
    statuses = model.Status.get_by_student_id(full_dbase, student_id)
    assert len(statuses) == initial_count + 1
    assert statuses[0].stage == model.Stage.FORMER_MEMBER
    assert statuses[0].reason == model.Reason.TRANSFERRED
    assert statuses[0].notes == note


def test_add_status_invalid_student_id(full_dbase: model.DBase) -> None:
    """Add a status with an invalid student_id."""
    # Arrange
    status = model.Status(
        status_id=0,
        student_id="nonexistent-student-id",
        stage=model.Stage.ROOKIE,
        start_date=datetime.date(2026, 1, 15),
        reason=None,
        notes=None,
    )
    # Act / Assert
    with pytest.raises(sqlite3.IntegrityError):
        status.add(full_dbase)


def test_add_safe_valid_transition(full_dbase: model.DBase) -> None:
    """Add a status that is consistent with the student's current stage."""
    # Arrange
    student_id = "bakr-salma-2026-946"
    initial_count = len(model.Status.get_by_student_id(full_dbase, student_id))
    status = model.Status(
        status_id=0,
        student_id=student_id,
        stage=model.Stage.ALUMNI,
        start_date=datetime.date(2026, 6, 15),
        reason=model.Reason.GRADUATED,
        notes=None,
    )
    # Act
    status.add_safe(full_dbase)
    # Assert
    statuses = model.Status.get_by_student_id(full_dbase, student_id)
    assert len(statuses) == initial_count + 1
    assert statuses[0].stage == model.Stage.ALUMNI
    assert status.status_id != 0


def test_add_safe_no_prior_status(full_dbase: model.DBase) -> None:
    """Add the first status for a student with no status history."""
    # Arrange
    student = model.Student(
        student_id="",
        first_name="Test",
        last_name="Student",
        grad_year=2027,
        email="test.student.addsafe@example.com",
    )
    student.add(full_dbase)
    status = model.Status(
        status_id=0,
        student_id=student.student_id,
        stage=model.Stage.PROSPECT,
        start_date=datetime.date(2026, 9, 1),
        reason=None,
        notes=None,
    )
    # Act
    status.add_safe(full_dbase)
    # Assert
    statuses = model.Status.get_by_student_id(full_dbase, student.student_id)
    assert len(statuses) == 1
    assert statuses[0].stage == model.Stage.PROSPECT


def test_add_safe_duplicate_stage(full_dbase: model.DBase) -> None:
    """Reject a status whose stage the student already has."""
    # Arrange
    student_id = "bakr-salma-2026-946"
    initial_count = len(model.Status.get_by_student_id(full_dbase, student_id))
    status = model.Status(
        status_id=0,
        student_id=student_id,
        stage=model.Stage.VETERAN,
        start_date=datetime.date(2026, 1, 1),
        reason=None,
        notes=None,
    )
    # Act / Assert
    with pytest.raises(model.StatusError) as exc_info:
        status.add_safe(full_dbase)
    assert exc_info.value.error_type == model.StatusErrorTypes.STATUS_EXISTS
    assert len(model.Status.get_by_student_id(full_dbase, student_id)) == initial_count


def test_add_safe_invalid_date(full_dbase: model.DBase) -> None:
    """Reject a status with an earlier start_date than an existing status."""
    # Arrange
    student_id = "bakr-salma-2026-946"
    initial_count = len(model.Status.get_by_student_id(full_dbase, student_id))
    status = model.Status(
        status_id=0,
        student_id=student_id,
        stage=model.Stage.ALUMNI,
        start_date=datetime.date(2024, 1, 1),
        reason=None,
        notes=None,
    )
    # Act / Assert
    with pytest.raises(model.StatusError) as exc_info:
        status.add_safe(full_dbase)
    assert exc_info.value.error_type == model.StatusErrorTypes.INVALID_DATE
    assert len(model.Status.get_by_student_id(full_dbase, student_id)) == initial_count


def test_add_safe_not_eligible(full_dbase: model.DBase) -> None:
    """Reject a status that isn't consistent with the student's current stage."""
    # Arrange
    student_id = "davis-isabella-2029-060"
    initial_count = len(model.Status.get_by_student_id(full_dbase, student_id))
    status = model.Status(
        status_id=0,
        student_id=student_id,
        stage=model.Stage.VETERAN,
        start_date=datetime.date(2026, 4, 1),
        reason=None,
        notes=None,
    )
    # Act / Assert
    with pytest.raises(model.StatusError) as exc_info:
        status.add_safe(full_dbase)
    assert exc_info.value.error_type == model.StatusErrorTypes.NOT_ELIGIBLE
    assert len(model.Status.get_by_student_id(full_dbase, student_id)) == initial_count


def test_get_current(full_dbase: model.DBase) -> None:
    """Get the current (most recent) status for every student."""
    # Act
    statuses = model.Status.get_current(full_dbase)
    # Assert
    student_ids = [status.student_id for status in statuses]
    assert len(student_ids) == len(set(student_ids))
    by_student = {status.student_id: status for status in statuses}
    current = by_student["davis-isabella-2029-060"]
    assert current.stage == model.Stage.FORMER_MEMBER
    assert current.start_date == datetime.date(2026, 3, 1)


def test_grad_years(full_dbase: model.DBase) -> None:
    """Get available graduation years without filtering by stage."""
    # Act
    grad_years = model.Student.grad_years(full_dbase)
    # Assert
    assert all(isinstance(grad_year, int) for grad_year in grad_years)
    assert grad_years == sorted(grad_years)


def test_get_with_status(full_dbase: model.DBase) -> None:
    """Get all students and their corresponding status."""
    # Act
    students = model.Student.get_with_status(
        full_dbase, asof_date=datetime.date(2026, 1, 1)
    )
    # Assert
    assert students
    assert all(isinstance(student.status, model.Status) for student in students)


def test_get_with_status_includes_status_starting_on_asof_date(
    full_dbase: model.DBase,
) -> None:
    """A status is current as of its own start_date, not just after it.

    Regression test: a batch stage change made "as of today" was invisible
    on every screen that shows current status, because get_with_status
    excluded statuses whose start_date equaled asof_date instead of
    including them.
    """
    # Arrange
    student_id = "bakr-salma-2026-946"
    new_start_date = datetime.date(2026, 6, 15)
    status = model.Status(
        status_id=0,
        student_id=student_id,
        stage=model.Stage.ALUMNI,
        start_date=new_start_date,
        reason=model.Reason.GRADUATED,
        notes=None,
    )
    status.add_safe(full_dbase)
    # Act
    students = model.Student.get_with_status(full_dbase, asof_date=new_start_date)
    # Assert
    student = next(s for s in students if s.student_id == student_id)
    assert student.status is not None
    assert student.status.stage == model.Stage.ALUMNI
    assert student.status.start_date == new_start_date
