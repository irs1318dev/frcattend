"""Main entry point for IRS Attend Application."""

import json
import pathlib
from typing import Any

import textual
from textual import app, containers, message, reactive, screen, widgets

from frcattend import config, model
from frcattend.features import excel, summary, sync
import frcattend.view
from frcattend.view import (
    attendance_screen,
    event_screen,
    file_widgets,
    pw_dialog,
    student_screen,
    survey_screen,
    take_attendance,
)


class EnableUiMessage(message.Message):
    """Direct the application to enable or disable the UI buttons on the screen."""

    enable: bool

    def __init__(self, enable: bool) -> None:
        """Set enable status on initialization."""
        super().__init__()
        self.enable = enable


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
                    "Students",
                    id="main-manage-students",
                    tooltip="Get a new student's info and generate a QR code.",
                )
                yield widgets.Button(
                    "Attendance by Student",
                    id="main-view-records",
                    tooltip=(
                        "View the number of checkins and "
                        "events attended for each student."
                    ),
                )
                yield widgets.Button(
                    "Attendance by Event",
                    id="main-manage-events",
                    tooltip=(
                        "View the number of checkins and students that attended "
                        "each event."
                    ),
                )
                yield widgets.Button(
                    "Surveys",
                    id="main-manage-surveys",
                    tooltip="Create and edit surveys.",
                )

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
                yield widgets.Button(
                    "Select Database",
                    id="main-select-database",
                    tooltip="Connect to a different database file.",
                )
                yield widgets.Button(
                    "Export",
                    id="main-export-database",
                    tooltip=(
                        "Export attendance data to an Excel spreadsheet or JSON file."
                    ),
                )
                yield widgets.Button(
                    "Import",
                    id="main-import-database",
                    tooltip="Import data from a JSON file.",
                )
                yield widgets.Button(
                    "Upload",
                    id="main-upload-database",
                    tooltip="Upload data to a Google Sheet.",
                )
                yield widgets.Button(
                    "Download",
                    id="main-download-database",
                    tooltip="Download data from a Google Sheet.",
                )

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
                    tooltip="ADVANCED: Create a new settings file (.toml).",
                )
                yield widgets.Button(
                    "Select Settings File",
                    id="main-select-settings",
                    tooltip="Select a different settings file.",
                )
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

    @textual.on(widgets.Button.Pressed, "#main-manage-surveys")
    def action_manage_surveys(self) -> None:
        """Go to survey management screen."""
        self.app.push_screen(survey_screen.SurveyScreen())

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

    @textual.on(widgets.Button.Pressed, "#main-upload-database")
    def upload_database(self) -> None:
        """Prepare to upload attendance data to a Google spreadsheet."""
        try:
            synchro = sync.Synchronizer()
        except config.ConfigError as err:
            self._notify_config_errors(err)
            return
        except sync.SynchronizerError as err:
            self._notify_synchro_errors(err)
            return
        self.set_button_status(enabled=False)
        self.notify("Starting upload...")
        self.set_timer(0.1, lambda: self._do_upload(synchro))

    @textual.work
    async def _do_upload(self, synchro: sync.Synchronizer) -> None:
        """Upload the database to a Google spreadsheet and show confirm dialog.

        Async work method is needed to allow UI notification to be displayed.
        """
        row_counts = synchro.upload()
        self.set_button_status(enabled=False)
        confirm_prompt = UploadConfirmation(row_counts)
        self.push_screen(confirm_prompt)

    @textual.work
    @textual.on(widgets.Button.Pressed, "#main-download-database")
    async def download_database(self) -> None:
        """Display download dialog and download data."""
        self.notify("Starting download...")
        self.set_timer(0.1, self.push_screen(DownloadConfirmation()))

    def _notify_synchro_errors(self, err: sync.SynchronizerError) -> None:
        """Notify user of synchronization errors."""
        if err.error_type == sync.SynchronizerError.ErrorType.ACCESS_DENIED:
            self.notify(
                "Access to Google workbook was denied. "
                "Did you share the workbook with your Google service account?",
                title="Access Denied!",
                severity="error",
            )

    def _notify_config_errors(self, err: config.ConfigError) -> None:
        """Notify user of missing or invalid configurations settings."""
        if err.error_type == config.ConfigError.ErrorType.UNDEFINED_SETTING:
            for setting in err.settings:
                match setting:
                    case "db_path":
                        self.notify(
                            "You must select a database before uploading attendance "
                            "data. (db_path)",
                            title="No Database Selected",
                            severity="warning",
                        )
                    case "google_servie_account":
                        self.notify(
                            "Add a Google service account to the settings TOML file. "
                            "(google_service_account)",
                            title="No Google Service Account",
                            severity="warning",
                        )
                    case "sync_sheet_key":
                        self.notify(
                            "Add synchronizer Google sheet key to the settings TOML "
                            "file. (sync_sheet_key)",
                            title="No Synchronizer Google Sheet Key",
                            severity="warning",
                        )

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

    def set_button_status(self, enabled: bool) -> None:
        """Disable all buttons."""
        for button in self.query(widgets.Button):
            button.disabled = not enabled

    @textual.on(EnableUiMessage)
    def _set_button_status(self, message: EnableUiMessage) -> None:
        """Enable or disable buttons."""
        self.set_button_status(enabled=message.enable)


class UploadConfirmation(screen.ModalScreen):
    """Show confirmation for uploading data to Syncro Google Workbook to user."""

    CSS_PATH = frcattend.view.CSS_FOLDER / "root.tcss"

    row_counts: dict[str, int]
    """Number of records uploaded for each table."""

    def __init__(self, row_counts: dict[str, int]) -> None:
        """Specify number of uploaded rows on initialization."""
        super().__init__()
        self.row_counts = row_counts

    def compose(self) -> app.ComposeResult:
        """Build the dialog box."""
        with containers.Vertical(id="upload-confirm-dialog", classes="modal-dialog"):
            yield widgets.Label("Uploaded Records!", classes="emphasis")
            markdown = ["# Rows Uploaded"]
            for table_name, count in self.row_counts.items():
                markdown.append(f"    * {table_name:>12} {count}")
            yield widgets.Markdown("\n".join(markdown))
            yield widgets.Button("Ok", id="confirm-upload", classes="ok-cancel-row")

    @textual.on(widgets.Button.Pressed, "#confirm-upload")
    def on_button_pressed(self, event: widgets.Button.Pressed) -> None:
        """Dismiss the dialog."""
        self.post_message(EnableUiMessage(enable=True))
        self.dismiss()


class DownloadConfirmation(screen.ModalScreen):
    """Show summary of downloaded info and have user confirm overrwriting DB."""

    CSS_PATH = frcattend.view.CSS_FOLDER / "root.tcss"

    synchro: sync.Synchronizer
    """Object that downloads data from a Google spreadsheet."""
    sheet_data: dict[str, list[dict[str, Any]]]
    """Data downloaded from Google spreadsheet."""

    def __init__(self) -> None:
        """Set up database on initialization."""
        super().__init__()
        self.synchro = sync.Synchronizer()
        self.sheet_data = self.synchro.download()

    def compose(self) -> app.ComposeResult:
        """Build the dialog box."""
        with containers.Vertical(id="download-confirm-dialog", classes="modal-dialog"):
            yield widgets.Label("Download Attendance Data", classes="emphasis")
            yield widgets.Label("Record Counts")
            yield self.build_counts_table()
            yield widgets.Label("Time of Last Checkin")
            yield self.build_tolc_table()
            with containers.Horizontal(classes="dialog-row"):
                yield widgets.Button("Ok", id="main-download-ok")
                yield widgets.Button("Cancel", id="main-download-cancel")

    def build_counts_table(self) -> widgets.DataTable:
        """Build table showing record counts in current DB and downloaded data."""
        db_counts = self.synchro.dbase.get_record_counts()
        sheet_counts = self.synchro.count_rows(self.sheet_data)
        table = widgets.DataTable(id="download-confirm-counts-table")
        for col in [
            ("Table", "table"),
            ("Local DB Records", "db_count"),
            ("Google Sheets Records", "sheet_count"),
        ]:
            table.add_column(col[0], key=col[1])
        for table_name in db_counts:
            table.add_row(table_name, db_counts[table_name], sheet_counts[table_name])
        return table

    def build_tolc_table(self) -> widgets.Markdown:
        """Build table showing time of last checkin for DB and downloaded data."""
        db_tolc = model.Checkin.get_time_of_last_checkin(self.synchro.dbase)
        if db_tolc is None:
            db_tolc_str = "None"
        else:
            db_tolc_str = db_tolc.replace(microsecond=0).isoformat()
        sheet_tolc = self.synchro.time_of_last_change(self.sheet_data)
        if sheet_tolc is None:
            sheet_tolc_str = "None"
        else:
            sheet_tolc_str = sheet_tolc.replace(microsecond=0).isoformat()
        mdown = "\n".join(
            [
                "| Local Database | Google Sheet |",
                "|----------------|--------------|",
                f"|{db_tolc_str}|{sheet_tolc_str}|",
            ]
        )
        return widgets.Markdown(mdown)

    @textual.on(widgets.Button.Pressed, "#main-download-cancel")
    def cancel_dialog(self) -> None:
        """Close the dialog and take no action."""
        self.dismiss()

    @textual.on(widgets.Button.Pressed, "#main-download-ok")
    def ok_dialog(self) -> None:
        """Write the downloaded data to the database."""
        self.synchro.dbase.backup()
        self.synchro.dbase.delete_all()
        self.synchro.dbase.load_from_dict(self.sheet_data)
        self.dismiss()
