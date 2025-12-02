"""Main entry point for IRS Attend Application."""

import json
import pathlib

import textual
from textual import app, containers, reactive, widgets

from frcattend import config, model
from frcattend.features import excel, summary
import frcattend.view
from frcattend.view import (
    attendance_screen,
    event_screen,
    file_widgets,
    pw_dialog,
    student_screen,
    take_attendance,
)


class FrcAttend(app.App):
    """Main application and introduction screen."""

    CSS_PATH = frcattend.view.CSS_FOLDER / "root.tcss"

    TITLE = "FRC Attendance System"
    BINDINGS = [
        ("a", "take_attendance", "Take Attendance"),
        ("s", "manage_students", "Manage Students"),
        ("v", "view_records", "View Attendance Records"),
    ]
    SCREENS = {
        "students": student_screen.StudentScreen,
    }
    db_path: reactive.reactive[pathlib.Path | None] = reactive.reactive(None)
    config_path: reactive.reactive[pathlib.Path | None] = reactive.reactive(None)
    message = reactive.reactive("Debugging messages will show up here!")

    def compose(self) -> app.ComposeResult:
        """Add widgets to screen."""
        yield widgets.Header()

        # Main menu bar
        with containers.HorizontalGroup(classes="pane"):
            with containers.HorizontalGroup(id="main-top-menu", classes="toolbar"):
                yield widgets.Button(
                    "Take Attendance",
                    id="main-take-attendance",
                    tooltip="Scan some QR Codes!",
                )
                yield widgets.Button(
                    "Manage Students",
                    id="main-manage-students",
                    tooltip="Get a new student's info and generate a QR code.",
                )
                yield widgets.Button("View Attendance Records", id="main-view-records")
                yield widgets.Button("Manage Events", id="main-manage-events")

        # Database Controls
        with containers.VerticalGroup(classes="pane"):
            with containers.HorizontalGroup():
                yield widgets.Label("Current Database: ", classes="emphasis")
                yield widgets.Label(
                    str(config.settings.db_path), id="main-config-db-path"
                )
            with containers.HorizontalGroup(
                id="main-database-buttons", classes="toolbar"
            ):
                yield widgets.Button(
                    "Create New Database File",
                    id="main-create-database",
                    classes="attend-main",
                )
                yield widgets.Button("Select Database", id="main-select-database")
                yield widgets.Button("Export", id="main-export-database")
                yield widgets.Button("Import", id="main-import-database")

        # Configuration Controls
        with containers.VerticalGroup(classes="pane"):
            with containers.HorizontalGroup():
                yield widgets.Label("Configuration File: ", classes="emphasis")
                yield widgets.Label(
                    str(config.settings.config_path), id="main-settings-path"
                )
            with containers.HorizontalGroup(classes="toolbar"):
                yield widgets.Button(
                    "Create New Settings File",
                    id="main-create-settings",
                )
                yield widgets.Button(
                    "Select Settings File",
                    id="main-select-settings",
                )
        # yield widgets.Label(
        #     "Nothing to see here!", id="main-status-message", classes="debug"
        # )
        yield widgets.Markdown(summary.get_summary(), id="main-db-summary")
        yield widgets.Footer()

    def on_mount(self) -> None:
        """Called when the app is first mounted."""
        self.db_path = config.settings.db_path
        self.config_path = config.settings.config_path

        def _exit_if_no_pw(success: bool | None) -> None:
            if not success or success is None:
                self.exit(message="Incorrect password.")

        pw_dialog.PasswordPrompt.show(
            submit_callback=_exit_if_no_pw, exit_on_cancel=True
        )

    @textual.on(widgets.Button.Pressed, "#main-take-attendance")
    def action_take_attendance(self) -> None:
        """Put application in attenance mode, so students can scan QR codes."""
        self.app.push_screen(take_attendance.ScanScreen())

    @textual.on(widgets.Button.Pressed, "#main-manage-students")
    def action_manage_students(self) -> None:
        """Go to register students screen."""
        self.app.push_screen(student_screen.StudentScreen())

    @textual.on(widgets.Button.Pressed, "#main-view-records")
    def action_view_records(self) -> None:
        """View attendance records."""
        self.app.push_screen(attendance_screen.AttendanceScreen())

    @textual.on(widgets.Button.Pressed, "#main-manage-events")
    def action_manage_events(self) -> None:
        """Go to event management screen."""
        self.app.push_screen(event_screen.EventScreen())

    @textual.on(widgets.Button.Pressed, "#main-select-database")
    async def action_select_database(self) -> None:
        """Select a different database file or create a new one."""

        def _select_database(db_path: pathlib.Path | None) -> None:
            """Select a new, existing database file."""
            if db_path is None:
                return
            config.settings.db_path = db_path
            self.db_path = db_path

        file_selector = file_widgets.FileSelector(
            pathlib.Path.cwd(),
            [".db", ".sqlite3"],
            create=False,
            default_filename=config.DB_FILE_NAME,
            id="main-select-database-file",
        )
        await self.app.push_screen(file_selector, _select_database)

    @textual.on(widgets.Button.Pressed, "#main-create-database")
    async def action_create_database(self) -> None:
        """Select a different database file or create a new one.

        Method `_on_file_selector_file_selected` is called when file selected.
        """

        def _create_database(db_path: pathlib.Path | None) -> None:
            """Select a new, existing database file."""
            if db_path is None:
                return
            model.DBase(db_path, create_new=True)
            config.settings.db_path = db_path
            self.db_path = db_path

        file_creator = file_widgets.FileSelector(
            pathlib.Path.cwd(),
            [".db", ".sqlite3"],
            create=True,
            default_filename=config.DB_FILE_NAME,
            id="main-create-database-file",
        )
        await self.app.push_screen(file_creator, _create_database)

    @textual.on(widgets.Button.Pressed, "#main-export-database")
    async def export_file(self):
        """Display a file selection widget for exporting data.

        Method `_on_file_selector_file_selected` is called when file selected.
        """

        def _export_database_to_file(export_path: pathlib.Path | None) -> None:
            """Export the contents of the sqlite database to a file."""
            if config.settings.db_path is None or export_path is None:
                return
            match export_path.suffix.lower():
                case ".json":
                    dbase = model.DBase(config.settings.db_path)
                    with open(export_path.with_suffix(".json"), "wt") as jfile:
                        json.dump(dbase.to_dict(), jfile, indent=2)
                    self.message = "Exporting JSON file."
                case ".xlsx":
                    dbase = model.DBase(config.settings.db_path)
                    excel.write(dbase, export_path.with_suffix(".xlsx"))
                case _:
                    self.message = "Incorrect file type"

        file_selector = file_widgets.FileSelector(
            pathlib.Path.cwd(),
            [".json", ".xlsx"],
            create=True,
            id="main-export-data-file",
        )
        await self.app.push_screen(file_selector, _export_database_to_file)

    @textual.on(widgets.Button.Pressed, "#main-import-database")
    async def select_import_file(self):
        """Display a file selection widget for importing data.

        Method `_on_file_selector_file_selected` is called when file selected.
        """

        def _import_data_from_file(import_path: pathlib.Path | None) -> None:
            """Import data from a JSON file."""
            if config.settings.db_path is None or import_path is None:
                return
            match import_path.suffix.lower():
                case ".json":
                    with open(import_path, "rt") as jfile:
                        imported_data = json.load(jfile)
                    dbase = model.DBase(config.settings.db_path)
                    dbase.load_from_dict(imported_data)

        file_selector = file_widgets.FileSelector(
            pathlib.Path.cwd(), [".json", ".xlsx"], id="main-import-data-file"
        )
        await self.app.push_screen(file_selector, _import_data_from_file)

    @textual.on(widgets.Button.Pressed, "#main-select-settings")
    async def select_settings_file(self):
        """Display a file selection widget for the application settings file.

        Method `_on_file_selector_file_selected` is called when file selected.
        """

        def _select_settings(config_path: pathlib.Path | None) -> None:
            """Select a new settings TOML file."""
            if config_path is None:
                return
            config.settings.config_path = config_path
            self.config_path = config_path

        file_selector = file_widgets.FileSelector(
            pathlib.Path.cwd(),
            [".toml"],
            create=False,
            default_filename=config.CONFIG_FILE_NAME,
            id="main-select-settings-file",
        )
        await self.app.push_screen(file_selector, _select_settings)

    @textual.on(widgets.Button.Pressed, "#main-create-settings")
    async def create_settings_file(self):
        """Display a file creation widget for the application settings. file.

        Method `_on_file_selector_file_selected` is called when file selected.
        """

        def _create_settings(config_path: pathlib.Path | None) -> None:
            """Select a new settings TOML file."""
            if config_path is None:
                return
            config.settings.create_new_config_file(config_path)
            config.settings.config_path = config_path
            self.config_path = config_path

        file_creator = file_widgets.FileSelector(
            pathlib.Path.cwd(),
            [".toml"],
            create=True,
            default_filename=config.CONFIG_FILE_NAME,
            id="main-create-settings-file",
        )
        await self.app.push_screen(file_creator, _create_settings)

    def watch_db_path(self, db_path: str) -> None:
        """Update the database path label."""
        self.query_one("#main-config-db-path", widgets.Label).update(str(db_path))
        self.query_one("#main-db-summary", widgets.Markdown).update(
            summary.get_summary()
        )

    def watch_config_path(self, config_path: str) -> None:
        """update the config path label."""
        self.query_one("#main-settings-path", widgets.Label).update(str(config_path))

    def watch_message(self) -> None:
        """Update the status message on changes."""
        # status_label = self.query_one("#main-status-message", widgets.Label)
        # status_label.update(self.message)

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        """Disable navigation actions when other screens are active."""
        if len(self.screen_stack) == 1:
            return True
        if isinstance(self.screen_stack[-1], take_attendance.ScanScreen):
            return False
        match action:
            case "manage_students":
                return not isinstance(
                    self.screen_stack[-1], student_screen.StudentScreen
                )
            case _:
                return True
