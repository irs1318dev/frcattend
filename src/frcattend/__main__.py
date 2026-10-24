"""Start the IRS Attendance App."""

import argparse
import pathlib

import rich

import frcattend.view.app
from frcattend import config
from frcattend.features import sync
from frcattend.model import database


def build_parser() -> argparse.ArgumentParser:
    """Define command line arguments."""
    parser = argparse.ArgumentParser(prog="IRS Attendance Program")
    parser.set_defaults(func=None)
    subparsers = parser.add_subparsers()
    _add_app_parser(subparsers)
    _add_sync_parser(subparsers)
    _add_encrypt_parser(subparsers)
    add_pw_hash_parser(subparsers)
    return parser


def _add_app_parser(subparsers: argparse._SubParsersAction) -> None:
    """Define arguments for the app subcommand."""
    app_parser = subparsers.add_parser("app", help="Run IRS Attendance application.")
    app_parser.set_defaults(func=run_app)
    app_parser.add_argument(
        "-d",
        "--db_path",
        help="Path to attendance database",
        type=pathlib.Path,
        default=None,
    )
    app_parser.add_argument(
        "-c",
        "--config_path",
        help="Path to config file",
        type=pathlib.Path,
        default=None,
    )


def _add_sync_parser(subparsers: argparse._SubParsersAction) -> None:
    """Define arguments for the sync-roster subcommand."""
    sync_parser = subparsers.add_parser(
        "sync-roster", help="Synchronize attendance data with the student roster."
    )
    sync_parser.set_defaults(func=sync_data)
    sync_group = sync_parser.add_mutually_exclusive_group(required=True)
    sync_group.add_argument(
        "-i",
        "--student-ids",
        action="store_true",
        help="Send student IDs to the team's Google Sheet roster.",
    )
    sync_group.add_argument(
        "-a",
        "--attendance-data",
        action="store_true",
        help="Send attendance to the team's Google Sheet roster.",
    )
    sync_parser.add_argument(
        "config_path", type=pathlib.Path, help="Path to roster configuration file."
    )
    sync_parser.add_argument(
        "db_path", type=pathlib.Path, help="Path to attendance Sqlite file."
    )


def _add_encrypt_parser(subparsers: argparse._SubParsersAction) -> None:
    """Define arguments for encrypting a Sqlite database file."""
    encrypt_parser = subparsers.add_parser("encrypt", help="Encrypt a Sqlite3 file.")
    encrypt_parser.set_defaults(func=encrypt_db)
    encrypt_parser.add_argument(
        "db_path", type=pathlib.Path, help="Path to an unencrypted Sqlite3 file."
    )
    encrypt_parser.add_argument(
        "-c",
        "--config_path",
        help="Path to config file with the encryption key",
        type=pathlib.Path,
        required=True,
    )


def add_pw_hash_parser(subparsers: argparse._SubParsersAction) -> None:
    """Define arguments for the pw-hash subcommand."""
    pw_parser = subparsers.add_parser(
        "pw-hash", help="Create a password hash for the coniguration TOML file."
    )
    pw_parser.set_defaults(func=hash_password)
    pw_parser.add_argument("password", help="Password to be hashed.")


def run_app(args: argparse.Namespace) -> None:
    """Run the IRS Attendane TUI application."""
    if hasattr(args, "config_path") and args.config_path is not None:
        config.settings.update_from_args(args)
    app = frcattend.view.app.FrcAttend()
    app.run()


def sync_data(args: argparse.Namespace) -> None:
    """Synchronize attendance data with other applications."""
    config_path = args.config_path.resolve()
    db_path = args.db_path.resolve()
    dbase = database.DBase(db_path)
    updater = sync.RosterUpdater(config_path, dbase)
    rich.print(args)
    if args.student_ids:
        print("updating Student IDs")
        updater.insert_student_ids()
    elif args.attendance_data:
        print("Syncing attendance data!")
        # updater.backup_database_file()
        updater.insert_attendance_info()


def encrypt_db(args: argparse.Namespace) -> None:
    """Encrypt a Sqlite database file using the key in the TOML config file."""
    config.settings.update_from_args(args)
    if config.settings.config_path is None:
        rich.print(f"[red]Config file at {args.config_path} not found. [/red]")
        return
    db_path = args.db_path.resolve()
    try:
        database.DBase.encrypt_file(db_path)
    except database.DBaseError as err:
        rich.print(f"[red]{err}[/red]")
        return
    rich.print(f"Encrypted {db_path}")


def hash_password(args: argparse.Namespace) -> None:
    """Hash a password."""
    rich.print(config.hash_password(args.password))


# def to_absolute_path(path: pathlib.Path) -> pathlib.Path:
#     """Convert relative paths to absolute paths."""
#     if not path.is_absolute():
#         path = path.resolve()
#     return path


def main() -> None:
    """Function to run the app, used for the setup.py entry_point."""
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
