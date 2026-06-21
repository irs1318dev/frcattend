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
        stage=model.Stage.MEMBER,
        start_date=datetime.date(2026, 1, 15),
        reason=None,
        notes=None,
    )
    # Act / Assert
    with pytest.raises(sqlite3.IntegrityError):
        status.add(full_dbase)


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


def test_get_current_member_veteran_dates(full_dbase: model.DBase) -> None:
    """Get the rookie-to-veteran transition date for current members/prospects."""
    # Act
    stages = [model.Stage.MEMBER, model.Stage.PROSPECT]
    veteran_dates = model.Student.get_veteran_dates(full_dbase, stages)
    # Assert
    # davis-isabella-2029-060 stopped attending during build season
    assert "davis-isabella-2029-060" not in veteran_dates
    # bakr-salma-2026-946 has been a member since 2023-12-01.
    assert veteran_dates["bakr-salma-2026-946"] == "2024-05-01"
    # anderson-mason-2029-608 started as a prospect on 2025-09-25 and is
    # currently a member.
    assert veteran_dates["anderson-mason-2029-608"] == "2026-05-01"
    # das-shreya-2026-285 has been a member since 2022-12-01.
    assert veteran_dates["das-shreya-2026-285"] == "2023-05-01"
    # campbell-benjamin-2026-840 is currently a former_member, so they are
    # excluded from the result.
    assert "campbell-benjamin-2026-840" not in veteran_dates
    assert len(veteran_dates) == 87


def test_get_all_member_veteran_dates(full_dbase: model.DBase) -> None:
    """Get the veteran transition date for all past and current students."""
    # Act
    veteran_dates = model.Student.get_veteran_dates(full_dbase)
    # Assert
    # davis-isabella-2029-060 stopped attending during build season
    assert "davis-isabella-2029-060" in veteran_dates
    # bakr-salma-2026-946 has been a member since 2023-12-01.
    assert veteran_dates["bakr-salma-2026-946"] == "2024-05-01"
    # anderson-mason-2029-608 started as a prospect on 2025-09-25 and is
    # currently a member.
    assert veteran_dates["anderson-mason-2029-608"] == "2026-05-01"
    # das-shreya-2026-285 has been a member since 2022-12-01.
    assert veteran_dates["das-shreya-2026-285"] == "2023-05-01"
    # campbell-benjamin-2026-840 is currently a former_member, so they are
    # excluded from the result.
    assert "campbell-benjamin-2026-840" in veteran_dates
    assert len(veteran_dates) == 151


def test_get_past_veteran_dates(full_dbase: model.DBase) -> None:
    """Get the veteran transition dates for past students."""
    # Act
    veteran_dates = model.Student.get_veteran_dates(
        full_dbase, as_of=datetime.date(2024, 12, 1)
    )
    # Assert
    assert len(veteran_dates) == 52


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
