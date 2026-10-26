"""Start the IRS Attendance App."""

import argparse
import pathlib
import tomllib

import rich

import frcattend.view.app
from frcattend import config
from frcattend.features import sync
from frcattend.model import database

TEMPLATE_FILE_NAME = "frcattend-config-template.toml"


def build_parser() -> argparse.ArgumentParser:
    """Define command line arguments."""
    parser = argparse.ArgumentParser(prog="IRS Attendance Program")
    parser.set_defaults(func=None)
    subparsers = parser.add_subparsers()
    _add_app_parser(subparsers)
    _add_sync_parser(subparsers)
    _add_encrypt_parser(subparsers)
    _add_config_parser(subparsers)
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


def _add_config_parser(subparsers: argparse._SubParsersAction) -> None:
    """Define arguments for the secure subcommand."""
    secure_parser = subparsers.add_parser(
        "config",
        help="Create a TOML config file template or move its credentials to keyring.",
    )
    secure_parser.set_defaults(func=run_config, db_path=None)
    secure_group = secure_parser.add_mutually_exclusive_group()
    secure_group.add_argument(
        "-c",
        "--create",
        nargs="?",
        const=pathlib.Path(TEMPLATE_FILE_NAME),
        type=pathlib.Path,
        metavar="CONFIG_PATH",
        help=f"Create a new TOML config file template (default: {TEMPLATE_FILE_NAME}).",
    )
    secure_group.add_argument(
        "-s",
        "--secure",
        dest="config_path",
        type=pathlib.Path,
        metavar="CONFIG_PATH",
        help="Move credentials from the TOML config file to keyring.",
    )
    config_subparsers = secure_parser.add_subparsers()
    _add_set_pin_parser(config_subparsers)


def _add_set_pin_parser(subparsers: argparse._SubParsersAction) -> None:
    """Define arguments for the config set-pin subcommand."""
    pin_parser = subparsers.add_parser(
        "set-pin", help="Hash a PIN and store it as password_hash in a config file."
    )
    pin_parser.set_defaults(func=set_pin)
    pin_parser.add_argument("pin", help="PIN to be hashed.")
    pin_parser.add_argument(
        "-f",
        "--config-file",
        type=pathlib.Path,
        required=True,
        help="Path to the TOML config file that will store the hash.",
    )


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


def run_config(args: argparse.Namespace) -> None:
    """Run the option selected for the secure subcommand."""
    if args.create is not None:
        create_config(args)
    elif args.config_path is not None:
        secure_config(args)
    else:
        rich.print("[red]Specify -c/--create, -s/--secure, or set-pin.[/red]")


def create_config(args: argparse.Namespace) -> None:
    """Write a new TOML config file template."""
    config_path = args.create.resolve()
    try:
        config.settings.write_new_config_file(config_path)
    except FileExistsError:
        rich.print(f"[red]File {config_path} already exists.[/red]")
        return
    rich.print(f"Created config file template: [bold]{config_path}[/bold]")


def secure_config(args: argparse.Namespace) -> None:
    """Move credentials from the TOML config file to the system keyring."""
    config.settings.update_from_args(args)
    if config.settings.config_path is None:
        rich.print(f"[red]Config file at {args.config_path} not found. [/red]")
        return
    backup_path = config.settings.secure_config_file()
    rich.print(
        f"Credentials moved to keyring. Secured config file: "
        f"{config.settings.config_path}\n"
        f"The original config file was saved to [bold]{backup_path}[/bold]\n"
        "[yellow]Save the credentials from the backup file in a different secure "
        "location, such as a password manager, then delete the backup file."
        "[/yellow]"
    )


def set_pin(args: argparse.Namespace) -> None:
    """Hash a PIN and store it in the TOML config file."""
    config_path = args.config_file.resolve()
    try:
        config.Settings.set_password_hash(config_path, args.pin)
    except FileNotFoundError:
        rich.print(f"[red]Config file at {config_path} not found.[/red]")
        return
    except tomllib.TOMLDecodeError as err:
        rich.print(f"[red]Config file at {config_path} is not valid TOML: {err}[/red]")
        return
    rich.print(f"Updated password_hash in [bold]{config_path}[/bold]")


def main() -> None:
    """Function to run the app, used for the setup.py entry_point."""
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
