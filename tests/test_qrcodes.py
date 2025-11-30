"""Test Sqlite event functionality."""

import pathlib

import pytest
import rich  # noqa: F401

from irsattend import config, model
from irsattend.features import emailer, qr_code_generator


DATA_FOLDER = pathlib.Path(__file__).parent / "data"
QR_FOLDER_NAME = "test_qr_codes"

# Comment next line to run tests.
pytestmark = pytest.mark.skip(reason="Tests require email credentials.")


def test_generate_qr_codes(
    full_dbase:model.DBase,
    empty_output_folder: pathlib.Path,
) -> None:
    """Generate QR codes for all students."""
    # Arrange
    qr_folder = empty_output_folder / QR_FOLDER_NAME
    students = model.Student.get_all(full_dbase, include_inactive=True)
    num_active_students = len([s for s in students if s.deactivated_on is None])
    # Act
    generator = qr_code_generator.generate_all_qr_codes(qr_folder, full_dbase)
    results = list(generator)
    # Assert
    assert results[0] == ("quantity-students", num_active_students)
    assert len(results) == num_active_students + 1
    assert all(result[1] is True for result in results[1:])
    for student in students:
        qr_path = qr_folder / f"{student.student_id}.png"
        if student.deactivated_on is None:
            assert qr_path.exists()
        else:
            assert not qr_path.exists()


def test_send_one_qr_code(
    full_dbase: model.DBase,
    empty_output_folder: pathlib.Path,
    settings: config.Settings,
) -> None:
    """Generate and send one QR code email.

    Sends email to the sender email address specified in test config. Check
    sender inbox to verify email was received.
    """
    # Arrange
    students = model.Student.get_all(full_dbase)
    qr_folder = empty_output_folder / QR_FOLDER_NAME
    list(qr_code_generator.generate_all_qr_codes(qr_folder, full_dbase))
    # Act
    assert settings.sender_email is not None
    result = emailer.send_email(
        settings.sender_email,
        f"{students[0].first_name} {students[0].last_name}",
        qr_folder / f"{students[0].student_id}.png",
    )
    assert result[0]


def test_send_multiple_qr_codes(
    full_dbase: model.DBase,
    empty_output_folder: pathlib.Path,
    settings: config.Settings,
) -> None:
    """Generate and send multiple QR code emails.

    Sends emails to the sender email address specified in test config. Check
    sender inbox to verify emails were received.
    """
    # Arrange
    students = model.Student.get_all(full_dbase)
    qr_folder = empty_output_folder / QR_FOLDER_NAME
    num_codes = 5
    list(qr_code_generator.generate_all_qr_codes(qr_folder, full_dbase))
    # Act
    assert settings.sender_email is not None
    results = list(
        emailer.send_all_emails(
            qr_folder, students[:num_codes], email=settings.sender_email
        )
    )
    # Assert
    assert len(results) == num_codes
    assert all(result[1] is True for result in results)
