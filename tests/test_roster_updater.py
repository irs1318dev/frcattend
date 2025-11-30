"""Update the Google Sheet roster with attendance data.

The tests in this module require a Google sheet roster that can be used for
testing and a roster settings YAML file with:
  1. Valid service account data
  2. A roster sheet key and column names that correspond to the test roster.

You have to create these on your own. See tests/data/example-roster-settings.yaml
for additional guidance.

Set the backup_folder setting in the YAML file to tests/ouput folder.
"""

import pathlib

import pytest
import rich  # noqa: F401

from frcattend.model import database, roster

TEST_PATH = pathlib.Path(__file__).parent
DATA_PATH = TEST_PATH / "data"
OUTPUT_PATH = TEST_PATH / "output"
SETTINGS_PATH = DATA_PATH / "private" / "test-roster-settings.yaml"

# Comment following line to run tests.
pytestmark = pytest.mark.skip(reason="Roster update tests are slow.")


def test_open_settings_and_authorization(full_dbase) -> None:
    """Import Google Sheet settings."""
    # Act
    updater = roster.SheetUpdater(SETTINGS_PATH, full_dbase)
    # Arrange
    assert isinstance(updater.roster_sheet_name, str)
    assert updater.roster_sheet_name


def test_update_student_ids(full_dbase: database.DBase) -> None:
    """Update the attendance IDs in the test Google sheet."""
    # Arrange
    updater = roster.SheetUpdater(SETTINGS_PATH, full_dbase)
    # Act
    updater.insert_student_ids()
    # Assert
    # Verify by inspecting Google sheet


def test_update_attendance_data(full_dbase: database.DBase) -> None:
    """Send attendance data to the roster."""
    # Arrange
    updater = roster.SheetUpdater(SETTINGS_PATH, full_dbase)
    # Act
    updater.insert_student_ids()
    updater.insert_attendance_info()
    # Assert
    # Verify by inspecting Google sheet


def test_db_backup(full_dbase: database.DBase) -> None:
    """Send attendance data to the roster.

    Set the backup_folder setting in the YAML file to tests/ouput folder or this
    test won't pass.
    """
    # Arrange
    updater = roster.SheetUpdater(SETTINGS_PATH, full_dbase)
    print()
    # Act
    updater.backup_database_file()
    # Assert
    output_files = [file for file in OUTPUT_PATH.iterdir()]
    assert len(output_files) == 2
    assert any([f.name.startswith("attendance-backup") for f in output_files])
