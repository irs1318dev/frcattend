"""Start the IRS Attendance App."""

import argparse
import pathlib

import rich

from frcattend import config
from frcattend.model import database, roster
import frcattend.view.main_app


def build_parser() -> argparse.ArgumentParser:
    """Define command line arguments."""
    parser = argparse.ArgumentParser(prog="IRS Attendance Program")
    subparsers = parser.add_subparsers()
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
    parser.set_defaults(func=None)

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
    return parser


def run_app(args: argparse.Namespace) -> None:
    """Run the IRS Attendane TUI application."""
    if hasattr(args, "config_path") and args.config_path is not None:
        config.settings.update_from_args(args)
    app = frcattend.view.main_app.IRSAttend()
    app.run()


def sync_data(args: argparse.Namespace) -> None:
    """Synchronize attendance data with other applications."""
    config_path = to_absolute_path(args.config_path)
    db_path = to_absolute_path(args.db_path)
    dbase = database.DBase(db_path)
    updater = roster.SheetUpdater(config_path, dbase)
    rich.print(args)
    if args.student_ids:
        print("updating Student IDs")
        updater.insert_student_ids()
    elif args.attendance_data:
        print("Syncing attendance data!")
        # updater.backup_database_file()
        updater.insert_attendance_info()


def to_absolute_path(path: pathlib.Path) -> pathlib.Path:
    """Convert relative paths to absolute paths."""
    if not path.is_absolute():
        path = pathlib.Path.cwd() / path
    return path


def main() -> None:
    """Function to run the app, used for the setup.py entry_point."""
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
