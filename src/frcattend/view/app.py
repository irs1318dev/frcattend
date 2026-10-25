"""Main entry point for IRS Attend Application."""

import json
import pathlib
from typing import cast

import boto3.exceptions
import botocore.exceptions
import textual
from textual import app, containers, message, reactive, screen, widgets

import frcattend.view
from frcattend import config, model
from frcattend.features import excel, summary, sync
from frcattend.view import (
    attendance_screen,
    event_screen,
    file_widgets,
    pw_dialog,
    student_screen,
    survey_screen,
    sync_dialogs,
    take_attendance,
)

UPLOAD_ERRORS = (
    config.ConfigError,
    boto3.exceptions.Boto3Error,
    botocore.exceptions.BotoCoreError,
    botocore.exceptions.ClientError,
)
"""Errors that can occur when uploading to or listing cloud object storage."""
DOWNLOAD_ERRORS = (*UPLOAD_ERRORS, model.DBaseError, OSError)
"""Errors that can occur when backing up, downloading, or replacing the database."""


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
    # ruff: ignore[RUF012]  # Textual requires mutable class variables.
    BINDINGS = [
        ("a", "take_attendance", "Take Attendance"),
        ("s", "manage_students", "Manage Students"),
        ("v", "view_records", "View Attendance Records"),
    ]
    # ruff: ignore[RUF012]
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
        with (
            containers.HorizontalGroup(classes="pane"),
            containers.HorizontalGroup(id="main-top-menu", classes="toolbar"),
        ):
            yield widgets.Button(
                "Take Attendance",
                id="main-take-attendance",
                tooltip="Scan some QR Codes!",
                classes="ok",
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
                    "View the number of checkins and events attended for each student."
                ),
                classes="ok",
            )
            yield widgets.Button(
                "Attendance by Event",
                id="main-manage-events",
                tooltip=(
                    "View the number of checkins and students that attended each event."
                ),
                classes="ok",
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
                    classes="ok",
                )
                yield widgets.Button(
                    "Import",
                    id="main-import-database",
                    tooltip="Import data from a JSON file.",
                    classes="ok",
                )
                yield widgets.Button(
                    "Upload",
                    id="main-upload-database",
                    tooltip="Upload the database to cloud storage.",
                )
                yield widgets.Button(
                    "Download",
                    id="main-download-database",
                    tooltip="Replace the database with a file from cloud storage.",
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
            instructions=(
                "Use a '.xlsx' file extension to export to an Excel file.\n"
                "Use a '.json' file extension to export to a JSON text file."
            ),
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
        """Upload the current database to cloud object storage."""
        try:
            synchro = sync.Synchronizer()
        except config.ConfigError as err:
            self.notify(str(err), title="Cannot Upload", severity="warning")
            return
        self.set_button_status(enabled=False)
        self.notify("Starting upload...")
        self._do_upload(synchro)

    @textual.work(thread=True, exclusive=True, group="upload")
    def _do_upload(self, synchro: sync.Synchronizer, force: bool = False) -> None:
        """Upload the database and show results, or ask before overwriting.

        Runs in a thread because S3 calls block.
        """
        try:
            object_key = synchro.upload(force=force)
        except sync.SynchronizerError as err:
            if err.error_type == sync.SynchronizerError.ErrorType.DUPLICATE_UPLOAD:
                self.call_from_thread(
                    self.push_screen,
                    sync_dialogs.ForceUploadDialog(str(err)),
                    lambda overwrite: self._on_force_upload(synchro, overwrite),
                )
                return
            self._show_upload_results(synchro, success=False, message=str(err))
            return
        except UPLOAD_ERRORS as err:
            self._show_upload_results(synchro, success=False, message=str(err))
            return
        self._show_upload_results(synchro, success=True, message=object_key)

    def _on_force_upload(
        self, synchro: sync.Synchronizer, overwrite: bool | None
    ) -> None:
        """Re-upload with force if user chose to overwrite, else re-enable UI."""
        if overwrite:
            self.notify("Overwriting existing upload...")
            self._do_upload(synchro, force=True)
        else:
            self.set_button_status(enabled=True)

    def _show_upload_results(
        self, synchro: sync.Synchronizer, success: bool, message: str
    ) -> None:
        """List files in object storage and show the results dialog.

        Must be called from the upload worker thread.
        """
        try:
            uploads = synchro.list_uploads()
        except UPLOAD_ERRORS:
            uploads = None
        self.call_from_thread(
            self.push_screen,
            sync_dialogs.UploadResultsDialog(success, message, uploads),
            lambda _: self.set_button_status(enabled=True),
        )

    @textual.on(widgets.Button.Pressed, "#main-download-database")
    def download_database(self) -> None:
        """Choose a database file in cloud object storage and download it."""
        try:
            synchro = sync.Synchronizer()
        except config.ConfigError as err:
            self.notify(str(err), title="Cannot Download", severity="warning")
            return
        self.set_button_status(enabled=False)
        self.notify("Listing files in cloud storage...")
        self._list_downloads(synchro)

    @textual.work(thread=True, exclusive=True, group="download")
    def _list_downloads(self, synchro: sync.Synchronizer) -> None:
        """List files in object storage and ask the user which to download.

        Runs in a thread because S3 calls block.
        """
        try:
            keys = synchro.list_uploads()
        except UPLOAD_ERRORS as err:
            self._show_download_results(success=False, message=str(err))
            return
        self.call_from_thread(
            self.push_screen,
            sync_dialogs.DownloadChooseFileDialog(keys),
            lambda object_key: self._on_download_file_chosen(synchro, object_key),
        )

    def _on_download_file_chosen(
        self, synchro: sync.Synchronizer, object_key: str | None
    ) -> None:
        """Download the chosen file, or re-enable UI if the user cancelled."""
        if object_key is None:
            self.set_button_status(enabled=True)
            return
        self.notify(f"Downloading {object_key}...")
        self._do_download(synchro, object_key)

    @textual.work(thread=True, exclusive=True, group="download")
    def _do_download(self, synchro: sync.Synchronizer, object_key: str) -> None:
        """Back up the database, replace it with the download, and show results.

        Runs in a thread because S3 calls block.
        """
        try:
            backup_path = synchro.download(object_key)
        except DOWNLOAD_ERRORS as err:
            self._show_download_results(success=False, message=str(err))
            return
        self._show_download_results(
            success=True, message=object_key, backup_path=backup_path
        )

    def _show_download_results(
        self, success: bool, message: str, backup_path: pathlib.Path | None = None
    ) -> None:
        """Show the download results dialog, then refresh the main screen.

        Must be called from a download worker thread.
        """

        def _on_dismiss(_: None) -> None:
            self.set_button_status(enabled=True)
            self.update_summary()

        self.call_from_thread(
            self.push_screen,
            sync_dialogs.DownloadResultsDialog(success, message, backup_path),
            _on_dismiss,
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
        self.update_summary()

    def update_summary(self) -> None:
        """Refresh the database summary, e.g., after the database file changes."""
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

    upload_status: dict[str, int | str]
    """Number of records uploaded for each table or table upload status."""

    def __init__(self, upload_status: dict[str, int | str]) -> None:
        """Specify table upload status on initialization."""
        super().__init__()
        self.upload_status = upload_status

    def compose(self) -> app.ComposeResult:
        """Build the dialog box."""
        with containers.Vertical(id="upload-confirm-dialog", classes="modal-dialog"):
            status_text = (
                cast(str, self.upload_status["status"]).replace("-", " ").title() + "!"
            )
            yield widgets.Label(status_text, classes="emphasis")
            markdown = ["# Rows Uploaded"]
            for table_name, count in self.upload_status.items():
                if table_name != "status":
                    markdown.append(f"    * {table_name:>12} {count}")
            yield widgets.Markdown("\n".join(markdown))
            yield widgets.Button("Ok", id="confirm-upload", classes="ok-cancel-row")

    @textual.on(widgets.Button.Pressed, "#confirm-upload")
    def on_button_pressed(self, event: widgets.Button.Pressed) -> None:
        """Dismiss the dialog."""
        self.post_message(EnableUiMessage(enable=True))
        self.dismiss()
