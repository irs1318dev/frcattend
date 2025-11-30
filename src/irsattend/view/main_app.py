"""Main entry point for IRS Attend Application."""

import json
import pathlib

import textual
from textual import app, containers, reactive, widgets

from irsattend import config, model
from irsattend.features import excel
import irsattend.view
from irsattend.view import (
    attendance_screen,
    event_screen,
    file_widgets,
    pw_dialog,
    student_screen,
    take_attendance,
)


class IRSAttend(app.App):
    """Main application and introduction screen."""

    CSS_PATH = irsattend.view.CSS_FOLDER / "root.tcss"

    TITLE = "IRS 1318 Attendance System"
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
            with containers.HorizontalGroup(id="main-top-menu"):
                yield widgets.Button(
                    "Take Attendance",
                    id="main-take-attendance",
                    tooltip="Scan some QR Codes!",
                )
                yield widgets.Button(
                    "Manage Students",
                    id="main-manage-students",
                    classes="attend-main",
                    tooltip="Get a new student's info and generate a QR code.",
                )
                yield widgets.Button(
                    "View Attendance Records",
                    id="main-view-records",
                    classes="attend-main",
                )
                yield widgets.Button(
                    "Manage Events", id="main-manage-events", classes="attend-main"
                )

        # Database Controls
        with containers.VerticalGroup(classes="pane"):
            with containers.HorizontalGroup():
                yield widgets.Label("Current Database: ", classes="emphasis")
                yield widgets.Label(
                    str(config.settings.db_path), id="main-config-db-path"
                )
            with containers.HorizontalGroup(
                id="main-database-buttons", classes="config"
            ):
                yield widgets.Button(
                    "Create New Database File",
                    id="main-create-database",
                    classes="attend-main",
                )
                yield widgets.Button(
                    "Select Database", id="main-select-database", classes="attend-main"
                )
                yield widgets.Button(
                    "Export", id="main-export-database", classes="attend-main"
                )
                yield widgets.Button(
                    "Import", id="main-import-database", classes="attend-main"
                )

        # Configuration Controls
        with containers.VerticalGroup(classes="pane"):
            with containers.HorizontalGroup():
                yield widgets.Label("Configuration File: ", classes="emphasis")
                yield widgets.Label(
                    str(config.settings.config_path), id="main-settings-path"
                )
            with containers.HorizontalGroup(classes="config"):
                yield widgets.Button(
                    "Create New Settings File",
                    classes="dock-right attend-main",
                    id="main-create-settings",
                )
                yield widgets.Button(
                    "Select Settings File",
                    classes="dock-right attend-main",
                    id="main-select-settings",
                )
        yield widgets.Label(
            "Nothing to see here!", id="main-status-message", classes="debug"
        )
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
    def action_select_database(self) -> None:
        """Select a different database file or create a new one."""
        self._close_any_file_selector()
        self.mount(
            file_widgets.FileSelector(
                pathlib.Path.cwd(),
                [".db", ".sqlite3"],
                create=False,
                default_filename="irsattend.db",
                id="main-select-database-file",
            )
        )

    def _select_database(self, db_path: pathlib.Path) -> None:
        """Select a new, existing database file."""
        config.settings.db_path = db_path
        self.db_path = db_path

    @textual.on(widgets.Button.Pressed, "#main-create-database")
    def action_create_database(self) -> None:
        """Select a different database file or create a new one.

        Method `_on_file_selector_file_selected` is called when file selected.
        """
        self._close_any_file_selector()
        self.mount(
            file_widgets.FileSelector(
                pathlib.Path.cwd(),
                [".db", ".sqlite3"],
                create=True,
                default_filename="irsattend.db",
                id="main-create-database-file",
            )
        )

    @textual.on(widgets.Button.Pressed, "#main-export-database")
    def select_export_file(self):
        """Display a file selection widget for exporting data.

        Method `_on_file_selector_file_selected` is called when file selected.
        """
        self._close_any_file_selector()
        self.mount(
            file_widgets.FileSelector(
                pathlib.Path.cwd(),
                [".json", ".xlsx"],
                create=True,
                id="main-export-data-file",
            )
        )

    def _export_database_to_file(self, export_path: pathlib.Path) -> None:
        """Export the contents of the sqlite database to a file."""
        if config.settings.db_path is None:
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

    @textual.on(widgets.Button.Pressed, "#main-import-database")
    def select_import_file(self):
        """Display a file selection widget for importing data.

        Method `_on_file_selector_file_selected` is called when file selected.
        """
        self._close_any_file_selector()
        self.mount(
            file_widgets.FileSelector(
                pathlib.Path.cwd(), [".json", ".xlsx"], id="main-import-data-file"
            )
        )

    def _import_data_from_file(self, import_path: pathlib.Path) -> None:
        """Import data from a JSON file."""
        if config.settings.db_path is None:
            return
        match import_path.suffix.lower():
            case ".json":
                with open(import_path, "rt") as jfile:
                    imported_data = json.load(jfile)
                dbase = model.DBase(config.settings.db_path)
                dbase.load_from_dict(imported_data)

    @textual.on(widgets.Button.Pressed, "#main-select-settings")
    def select_settings_file(self):
        """Display a file selection widget for the application settings file.

        Method `_on_file_selector_file_selected` is called when file selected.
        """
        self._close_any_file_selector()
        self.mount(
            file_widgets.FileSelector(
                pathlib.Path.cwd(),
                [".toml"],
                create=False,
                default_filename="irsattend.toml",
                id="main-select-settings-file",
            )
        )

    @textual.on(widgets.Button.Pressed, "#main-create-settings")
    def create_settings_file(self):
        """Display a file creation widget for the application settings. file.

        Method `_on_file_selector_file_selected` is called when file selected.
        """
        self._close_any_file_selector()
        self.mount(
            file_widgets.FileSelector(
                pathlib.Path.cwd(),
                [".toml"],
                create=True,
                default_filename="irsattend.toml",
                id="main-create-settings-file",
            )
        )

    def _select_settings(self, config_path: pathlib.Path) -> None:
        """Select a new settings TOML file."""
        config.settings.config_path = config_path
        self.config_path = config_path

    def _on_file_selector_file_selected(
        self, message: file_widgets.FileSelector.FileSelected
    ) -> None:
        """Update db_path in config and main screen."""
        self.message = f"Selected DB file: {message.path, message.create, message.id}"
        match message.id:
            case "main-select-database-file":
                self._select_database(message.path)
            case "main-create-database-file":
                model.DBase(message.path, create_new=True)
                self._select_database(message.path)
            case "main-export-data-file":
                self._export_database_to_file(message.path)
            case "main-import-data-file":
                self._import_data_from_file(message.path)
            case "main-select-settings-file":
                self._select_settings(message.path)
            case "main-create-settings-file":
                config.settings.create_new_config_file(message.path)
                self._select_settings(message.path)

    def _close_any_file_selector(self) -> None:
        """Close any existing FileSelector widget to prevent duplicates."""
        try:
            for selector in self.query(file_widgets.FileSelector):
                selector.remove()
        except Exception:
            pass

    def watch_db_path(self, db_path: str) -> None:
        """Update the database path label."""
        self.query_one("#main-config-db-path", widgets.Label).update(str(db_path))

    def watch_config_path(self, config_path: str) -> None:
        """update the config path label."""
        self.query_one("#main-settings-path", widgets.Label).update(str(config_path))

    def watch_message(self) -> None:
        """Update the status message on changes."""
        status_label = self.query_one("#main-status-message", widgets.Label)
        status_label.update(self.message)

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
