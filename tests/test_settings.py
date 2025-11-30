"""Test command-line args and settings."""

import argparse
import pathlib


from frcattend import config


DATA_PATH = pathlib.Path(__file__).parent / "data"


def test_read_config() -> None:
    """Read the configuration from a TOML file."""
    # Arrange
    args = argparse.Namespace(config_path=DATA_PATH / "irsattend.toml")
    args.db_path = DATA_PATH / "irsattend.db"
    # Act
    config.settings.update_from_args(args)
    # Assert
    assert isinstance(config.settings.qr_code_dir, pathlib.Path)
    assert config.settings.qr_code_dir.name == "qr_codes"
    assert config.settings.email_sender_name == "IRS Attendance System"
    assert config.settings.schoolyear_start_date.month == 9
    assert config.settings.schoolyear_start_date.day == 1
    assert config.settings.buildseason_start_date.month == 1
    assert config.settings.buildseason_start_date.day == 1
    assert (
        config.settings.buildseason_start_date > config.settings.schoolyear_start_date
    )
