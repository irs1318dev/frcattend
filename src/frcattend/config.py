"""Manage configuration settings for the IRS Attend application."""

import argparse
import dataclasses
import datetime
import enum
import functools
import hashlib
import json
import pathlib
import re
import shutil
import tomllib
from typing import ClassVar

import keyring
import keyring.errors
import tomli_w

DB_FILE_NAME = "frc-attend.db"
CONFIG_FILE_NAME = "frc-attend.toml"


class ConfigError(Exception):
    """Errors when setting or accessing settings."""

    class ErrorType(enum.Enum):
        NOT_A_FILE = 1
        PATH_DOES_NOT_EXIST = 2
        INVALID_GOOGLE_SERVICE_ACCOUNT = 3
        UNDEFINED_SETTING = 4

    error_type: ErrorType
    settings: list[str]

    def __init__(self, message: str, error_type: ErrorType) -> None:
        """Set error type."""
        super().__init__(message)
        self.error_type = error_type
        self.settings = []


@dataclasses.dataclass
class Settings:
    """Configuration data for frcattend application.

    password_hash is a SHA256 hash created with the hashlib library. The
    default PIN is 0000. Change the PIN with the `attend config set-pin`
    command.
    """

    team_name: str | None = None
    """Team name that appears on QR code emails (e.g., IRS 1318)."""
    db_path: pathlib.Path | None = None
    """Filesystem path to Sqlite database file with student and attendance data."""
    config_path: pathlib.Path | None = None
    """Filesystem path to TOML configuration file."""
    encryption_key: str | None = None
    """Key for encrypting Sqlite database with SQLCipher."""
    qr_code_dir: pathlib.Path | None = None
    """Filesystem path to folder where QR codes are written."""
    backup_dir: pathlib.Path | None = None
    """Filesystem path to folder where database file is backed up."""
    schoolyear_start_month_and_day: tuple[int, int] = (9, 1)
    """Date on which next academic year starts.
    
    Team events before this date are counted in the prior academic year.
    """
    build_start_month_and_day: tuple[int, int] = (1, 1)
    """Date on which build season starts.
    
    Used for calculating attendance during build and competition season.
    """
    password_hash: str | None = (
        "9af15b336e6a9619928537df30b2e6a2376569fcf9d7e773eccede65606529a0"  # 0000
    )
    """Sets the password for opening application and leaving QR code scan mode."""
    camera_number: int = 0
    """Identifies which camera on computer is used for scanning QR codes.
    
    Camera 0 is front facing camera on Windows OS.
    """
    sender_email: str | None = None
    """Gmail email address used to send QR codes to students."""
    email_sender_name: str | None = None
    """User-friendly app name that appears on QR code emails."""
    smtp_server: str | None = None
    """Gmail credentials."""
    smtp_port: int = 465
    """Gmail credentials."""
    smtp_username: str | None = None
    """Gmail credentials."""
    smtp_password: str | None = None
    """Gmail credentials."""
    google_service_account: dict[str, str] | None = None
    """Authentication credentials for connecting to Google worksheets.

    Credentials are downloaded as a JSON file. Paste the contents of the JSON
    file into a TOML multiline string.
    
    IMPORTANT: Use TOML multiline, literal syntax (''') to add Google
    service account data to TOML config file. The literal syntax ignores escape
    charactes and allows the string to contain double quotes (essntial for
    JSON strings). See https://toml.io/en/
    """
    sync_sheet_key: str | None = None
    """Key to Google sheet used for syncing data between different computers."""
    s3_url: str | None = None
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None

    keyring_service_name: ClassVar[str] = "frcattend"
    """Service name used when storing credentials with the keyring package."""
    keyring_settings: ClassVar[tuple[str, ...]] = (
        "encryption_key",
        "smtp_password",
        "google_service_account",
        "s3_access_key_id",
        "s3_secret_access_key",
    )
    """Settings that can be stored in keyring instead of the config file."""
    keyring_chunk_size: ClassVar[int] = 1200
    """Maximum characters stored in a single keyring password.

    Windows Credential Manager limits passwords to 2560 bytes, and keyring
    encodes passwords as UTF-16 (2 bytes per character), so the limit is 1280
    characters. Longer values are split into multiple keyring passwords.
    """
    keyring_chunk_prefix: ClassVar[str] = "__frcattend_chunks__:"
    """Marks a keyring password that holds the number of chunks for a setting.

    A long value for setting `name` is stored as a header password under
    `name` with the value `<prefix><count>`, and the chunks are stored under
    `name.0`, `name.1`, etc.
    """

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
        self._read_keyring()

    @staticmethod
    def _convert_path_to_absolute(path: pathlib.Path | str) -> pathlib.Path:
        """Convert relative paths to absolute paths."""
        if isinstance(path, str):
            path = pathlib.Path(path)
        return path if path.is_absolute() else pathlib.Path.cwd() / path

    @staticmethod
    def _get_full_path(
        path: pathlib.Path, default_file_name: str
    ) -> pathlib.Path | None:
        """Convert path arg to full filesystem path.

        If path is None, looks for file in current working directory. Otherwise
        converts relative paths to absolute paths. Returns None if path does not
        point to an existing file.
        """
        cwd = pathlib.Path.cwd()
        full_path: pathlib.Path | None = None
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
            file_settings = tomllib.load(toml_file)
        for setting_name, value in self._flatten_config(file_settings).items():
            if isinstance(value, str) and value.lower() in ["", "none", "null"]:
                value = None
            match setting_name:
                case "qr_code_dir":
                    if value is not None:
                        self.qr_code_dir = self._convert_path_to_absolute(value)
                case "backup_dir":
                    if value is not None:
                        self.backup_dir = self._convert_path_to_absolute(value)
                case "google_service_account":
                    if value is None:
                        continue
                    if isinstance(value, str):
                        self.google_service_account = json.loads(value)
                    else:
                        raise ConfigError(
                            "Invalid Google service account data.",
                            ConfigError.ErrorType.INVALID_GOOGLE_SERVICE_ACCOUNT,
                        )
                case _:
                    if setting_name not in app_settings:
                        continue
                    setattr(self, setting_name, value)

    def _read_keyring(self) -> None:
        """Read keyring settings that were not set by the config file."""
        for setting_name in self.keyring_settings:
            if getattr(self, setting_name) is not None:
                continue
            value = self._get_keyring_password(setting_name)
            if value is None:
                continue
            if setting_name == "google_service_account":
                self.google_service_account = json.loads(value)
            else:
                setattr(self, setting_name, value)

    def _get_keyring_password(self, setting_name: str) -> str | None:
        """Get a password from keyring, joining chunks if it was split."""
        value = keyring.get_password(self.keyring_service_name, setting_name)
        chunk_count = self._get_chunk_count(value)
        if chunk_count == 0:
            return value
        chunks = []
        for idx in range(chunk_count):
            chunk = keyring.get_password(
                self.keyring_service_name, f"{setting_name}.{idx}"
            )
            if chunk is None:
                return None
            chunks.append(chunk)
        return "".join(chunks)

    def _set_keyring_password(self, setting_name: str, value: str) -> None:
        """Save a password to keyring, splitting it into chunks if too long."""
        old_chunk_count = self._get_chunk_count(
            keyring.get_password(self.keyring_service_name, setting_name)
        )
        chunks = [
            value[idx : idx + self.keyring_chunk_size]
            for idx in range(0, len(value), self.keyring_chunk_size)
        ]
        if len(chunks) > 1:
            for idx, chunk in enumerate(chunks):
                keyring.set_password(
                    self.keyring_service_name, f"{setting_name}.{idx}", chunk
                )
            keyring.set_password(
                self.keyring_service_name,
                setting_name,
                f"{self.keyring_chunk_prefix}{len(chunks)}",
            )
        else:
            chunks = []
            keyring.set_password(self.keyring_service_name, setting_name, value)
        # Remove leftover chunks from a previously stored, longer value.
        for idx in range(len(chunks), old_chunk_count):
            try:
                keyring.delete_password(
                    self.keyring_service_name, f"{setting_name}.{idx}"
                )
            except keyring.errors.PasswordDeleteError:
                pass

    def _get_chunk_count(self, value: str | None) -> int:
        """Return number of chunks if value is a chunk header, otherwise 0."""
        if value is None or not value.startswith(self.keyring_chunk_prefix):
            return 0
        return int(value.removeprefix(self.keyring_chunk_prefix))

    @classmethod
    def _flatten_config(cls, file_settings: dict) -> dict:
        """Flatten TOML tables into a single dict of setting names and values.

        Keys inside tables (e.g., [app], [email]) are mapped to Settings
        attribute names. Top-level keys outside of any table are also accepted.
        """
        flat_settings = {}
        for table_name, table_values in file_settings.items():
            if isinstance(table_values, dict):
                for key, val in table_values.items():
                    flat_settings[key] = val
            else:
                flat_settings[table_name] = table_values
        return flat_settings

    def secure_config_file(self) -> pathlib.Path:
        """Move authentication credentials from the TOML config file to keyring.

        Store sensitive authentication credentials using the Python keyring
        package. The original config file is copied to a timestamped backup
        file in the same folder, and a new config file is written without the
        settings that were moved to keyring. Returns the path to the backup
        file so the user can delete it.
        """
        if self.config_path is None:
            raise ConfigError(
                "No configuration file to secure.", ConfigError.ErrorType.NOT_A_FILE
            )
        with open(self.config_path, "rb") as toml_file:
            file_settings = tomllib.load(toml_file)

        for setting_name, value in self._flatten_config(file_settings).items():
            if setting_name not in self.keyring_settings:
                continue
            if value is None or str(value).lower() in ["", "none", "null"]:
                continue
            self._set_keyring_password(setting_name, str(value))

        timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = self.config_path.with_name(
            f"{self.config_path.stem}-backup-{timestamp}{self.config_path.suffix}"
        )
        shutil.copy2(self.config_path, backup_path)

        secured_settings = {}
        for table_name, table_values in file_settings.items():
            if isinstance(table_values, dict):
                secured_settings[table_name] = {
                    key: val
                    for key, val in table_values.items()
                    if key not in self.keyring_settings
                }
            elif table_name not in self.keyring_settings:
                secured_settings[table_name] = table_values
        with open(self.config_path, "wb") as toml_file:
            tomli_w.dump(secured_settings, toml_file, multiline_strings=True)
        return backup_path

    def write_new_config_file(self, config_path: pathlib.Path) -> None:
        """Write an empty TOML configuration file with null values for settings.

        TOML has no null type, so unset settings are written as the string
        "null", which `_read_config_file` converts to None. Settings with a
        default value are written with that default. Raises FileExistsError if
        config_path already exists.
        """
        defaults = Settings()
        schoolyear_start = list(defaults.schoolyear_start_month_and_day)
        build_start = list(defaults.build_start_month_and_day)
        content = f"""\
# frcattend configuration file
#
# Settings that are not used can be left as "null". Relative paths are
# relative to the folder where frcattend is started.
#
# Credentials (encryption_key, smtp_password, google_service_account,
# s3_access_key_id, and s3_secret_access_key) can be moved from this file to
# the operating system's secure credential store by running:
#   attend config -s <path to this file>

[app]
# Team name that appears on QR code emails (e.g., IRS 1318).
team_name = "null"

# Key for encrypting the Sqlite database with SQLCipher.
encryption_key = "null"

# Folder where student QR code images are written.
qr_code_dir = "null"

# Folder where the database file is backed up.
backup_dir = "null"

# Month and day on which the next academic year starts, as [month, day].
# Team events before this date are counted in the prior academic year.
schoolyear_start_month_and_day = {schoolyear_start}

# Month and day on which build season starts, as [month, day]. Used for
# calculating attendance during build and competition season.
build_start_month_and_day = {build_start}

# SHA256 hash of the password for opening the application and leaving QR code
# scan mode. The default hash corresponds to the default PIN 0000. Change the
# PIN by running:
#   attend config set-pin <new PIN> -f <path to this file>
password_hash = "9af15b336e6a9619928537df30b2e6a2376569fcf9d7e773eccede65606529a0"

# Identifies which camera is used for scanning QR codes. Camera 0 is usually
# the front-facing camera on Windows.
camera_number = {defaults.camera_number}

[email]
# Gmail address used to send QR codes to students.
sender_email = "null"

# User-friendly name that appears as the sender on QR code emails.
email_sender_name = "null"

# SMTP server credentials for sending email (e.g., smtp.gmail.com).
smtp_server = "null"
smtp_port = {defaults.smtp_port}
smtp_username = "null"
smtp_password = "null"

[google]
# Authentication credentials for connecting to Google worksheets. Credentials
# are downloaded from Google as a JSON file. Paste the contents of the JSON
# file between triple single quotes, which allows the JSON double quotes:
#   google_service_account = '''
#   {{"type": "service_account", ...}}
#   '''
google_service_account = "null"

# Key to the Google sheet used for syncing data between computers.
sync_sheet_key = "null"

[s3]
# S3-compatible object storage used for uploading and downloading data.
s3_url = "null"
s3_access_key_id = "null"
s3_secret_access_key = "null"
"""
        with open(config_path, "x", encoding="utf-8") as toml_file:
            toml_file.write(content)

    @staticmethod
    def set_password_hash(config_path: pathlib.Path, pin: str) -> None:
        """Hash a PIN and store it as password_hash in a TOML config file.

        The file is edited as text so comments and formatting are preserved.
        An existing password_hash line is replaced. Otherwise the setting is
        added after the [app] table header, or at the top of the file if there
        is no [app] table. Raises FileNotFoundError if config_path does not
        exist.
        """
        if not config_path.is_file():
            raise FileNotFoundError(f"Config file {config_path} not found.")
        content = config_path.read_text(encoding="utf-8")
        hash_line = f'password_hash = "{hash_password(pin)}"'
        content, count = re.subn(
            r"^[ \t]*password_hash[ \t]*=.*$", hash_line, content, flags=re.MULTILINE
        )
        if count == 0:
            content, count = re.subn(
                r"^[ \t]*\[app\][ \t]*$",
                lambda match: f"{match.group(0)}\n{hash_line}",
                content,
                count=1,
                flags=re.MULTILINE,
            )
        if count == 0:
            content = f"{hash_line}\n{content}"
        tomllib.loads(content)  # Ensure the edited file is still valid TOML.
        config_path.write_text(content, encoding="utf-8")


# Store settings in a module-level variable, which will be available from any
# other module that imports frcattend.config. This pattern is sometimes referred
# to as a Singleton pattern, because there is only a single instance of the
# Settings class.
settings = Settings()


def hash_password(pw: str) -> str:
    """Calculate the sha256 hash of a password.

    Used by `Settings.set_password_hash` (the `attend config set-pin` command)
    and to check passwords entered in the application.
    """
    return hashlib.sha256(pw.encode("utf-8")).hexdigest()
