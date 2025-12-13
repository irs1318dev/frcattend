"""Manage configuration settings for the IRS Attend application."""

import argparse
import dataclasses
import datetime
import enum
import functools
import json
import hashlib
import pathlib
import shutil
import tomllib
from typing import Optional


DB_FILE_NAME = "frc-attend.db"
CONFIG_FILE_NAME = "frc-attend.toml"


class ConfigError(Exception):
    """Errors when setting or accessing settings."""

    class ErrorType(enum.Enum):
        NOT_A_FILE = 1
        PATH_DOES_NOT_EXIST = 2
        INVALID_GOOGLE_SERVICE_ACCOUNT = 3

    error_type: ErrorType

    def __init__(self, message: str, error_type: ErrorType) -> None:
        """Set error type."""
        super().__init__(message)
        self.error_type = error_type


@dataclasses.dataclass
class Settings:
    """Configuration data for frcattend application.

    password_hash is a SHA256 hash created with the hashlib library. The
    default password is 1318. See the hash_password function below for more
    details.
    """

    db_path: Optional[pathlib.Path] = None
    """Filesystem path to Sqlite database file with student and attendance data."""
    config_path: Optional[pathlib.Path] = None
    """Filesystem path to TOML configuration file."""
    qr_code_dir: Optional[pathlib.Path] = None
    """Filesystem path to folder where QR codes are written."""
    schoolyear_start_month_and_day: tuple[int, int] = (9, 1)
    """Date on which next academic year starts.
    
    Team events before this date are counted in the prior academic year.
    """
    build_start_month_and_day: tuple[int, int] = (1, 1)
    """Date on which build season starts.
    
    Used for calculating attendance during build and competition season.
    """
    password_hash: Optional[str] = (
        "095eaa09cd36d1f1e7a963c9ad618edab13f466882c9027ab81ffc18b0eb727e"  # 1318
    )
    """Sets the password for opening application and leaving QR code scan mode."""
    camera_number: int = 0
    """Identifies which camera on computer is used for scanning QR codes.
    
    Camera 0 is front facing camera on Windows OS.
    """
    sender_email: Optional[str] = None
    """Gmail email address used to send QR codes to students."""
    email_sender_name: Optional[str] = None
    """User-friendly app name that appears on QR code emails."""
    smtp_server: Optional[str] = None
    """Gmail credentials."""
    smtp_port: int = 465
    """Gmail credentials."""
    smtp_username: Optional[str] = None
    """Gmail credentials."""
    smtp_password: Optional[str] = None
    """Gmail credentials."""
    google_service_account: Optional[dict[str, str]] = None
    """Authentication credentials for connecting to Google worksheets."""

    @functools.cached_property
    def schoolyear_start_date(self) -> datetime.date:
        """Date on which current season started."""
        current_year = datetime.date.today().year
        schoolyear_start = datetime.date(
            year=current_year,
            month=self.schoolyear_start_month_and_day[0],
            day=self.schoolyear_start_month_and_day[1],
        )
        if datetime.date.today() >= schoolyear_start:
            return schoolyear_start
        else:
            return schoolyear_start.replace(year=current_year - 1)

    @functools.cached_property
    def buildseason_start_date(self) -> datetime.date:
        """Date on current build_season started or will start."""
        buildseason_start = self.schoolyear_start_date.replace(
            month=self.build_start_month_and_day[0],
            day=self.build_start_month_and_day[1],
        )
        if buildseason_start < self.schoolyear_start_date:
            buildseason_start = buildseason_start.replace(
                year=buildseason_start.year + 1
            )
        return buildseason_start

    def update_from_args(self, args: argparse.Namespace) -> None:
        """Read settings."""
        self.db_path = self._get_full_path(args.db_path, DB_FILE_NAME)
        self.config_path = self._get_full_path(args.config_path, CONFIG_FILE_NAME)
        if self.config_path is not None:
            self._read_config_file()

    @staticmethod
    def _convert_path_to_absolute(path: pathlib.Path | str) -> pathlib.Path:
        """Convert relative paths to absolute paths."""
        if isinstance(path, str):
            path = pathlib.Path(path)
        return path if path.is_absolute() else pathlib.Path.cwd() / path

    @staticmethod
    def _get_full_path(
        path: pathlib.Path, default_file_name: str
    ) -> Optional[pathlib.Path]:
        """Convert path arg to full filesystem path.

        If path is None, looks for file in current working directory. Otherwise
        converts relative paths to absolute paths. Returns None if path does not
        point to an existing file.
        """
        cwd = pathlib.Path.cwd()
        full_path: Optional[pathlib.Path] = None
        if path is None:
            full_path = cwd / default_file_name
        elif path.is_absolute():
            full_path = path
        else:
            full_path = cwd / path
        if not full_path.is_file() or not full_path.exists():
            full_path = None
        return full_path

    def _read_config_file(self) -> None:
        """Read TOML configuration file."""
        if self.config_path is None:
            return
        app_settings = dataclasses.asdict(self)
        with open(self.config_path, "rb") as toml_file:
            file_settngs = tomllib.load(toml_file)
        for setting_name, value in file_settngs.items():
            match setting_name:
                case "qr_code_dir":
                    if setting_name is not None and value is not None:
                        self.qr_code_dir = self._convert_path_to_absolute(value)
                case "google_service_account":
                    if isinstance(value, str):
                        self.google_service_account = json.loads(value)
                    else:
                        raise ConfigError(
                            "Invalid Google service account data.",
                            ConfigError.ErrorType.INVALID_GOOGLE_SERVICE_ACCOUNT
                        )
                case _:
                    if setting_name not in app_settings:
                        return
                    if isinstance(value, str) and value.lower() in ["", "none", "null"]:
                        value = None
                    setattr(self, setting_name, value)

    def create_new_config_file(self, config_path: pathlib.Path) -> None:
        """Create a new configuration file with default settings."""
        if not config_path.exists():
            shutil.copy(
                pathlib.Path(__file__).parent / "example-config.toml", config_path
            )


# Store settings in a module-level variable, which will be available from any
# other module that imports frcattend.config. This pattern is sometimes referred
# to as a Singleton pattern, because there is only a single instance of the
# Settings class.
settings = Settings()


def hash_password(pw: str) -> str:
    """Calculate the sha256 hash of a password.
    
    Put the resulting hash code in the config.toml file to use the password in
    the attendance application.
    """
    return hashlib.sha256(pw.encode("utf-8")).hexdigest()
