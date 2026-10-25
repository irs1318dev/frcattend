"""Dialogs for synchronizing databases on different computers."""

import pathlib

import textual
from textual import app, containers, screen, widgets

import frcattend.view
from frcattend.features import sync


class ForceUploadDialog(screen.ModalScreen[bool]):
    """Warn user before uploading the database.

    Shown when a file with the same name is already in object storage.
    Dismisses with True if the user wants to overwrite the existing file.
    """

    CSS_PATH = frcattend.view.CSS_FOLDER / "sync_dialogs.tcss"

    message: str
    """Explanation of why the upload was refused."""

    def __init__(self, message: str) -> None:
        """Include the duplicate upload message in the dialog."""
        super().__init__()
        self.message = message

    def compose(self) -> app.ComposeResult:
        """Layout the dialog box."""
        with containers.Vertical(id="force-upload-dialog", classes="modal-dialog"):
            yield widgets.Label("[bold yellow]Database Already Uploaded[/bold yellow]")
            yield widgets.Static()
            yield widgets.Static(self.message)
            yield widgets.Static()
            yield widgets.Static(
                "The database has probably not changed since the last upload. "
                "Do you want to upload it again and overwrite the existing file?"
            )
            with containers.Horizontal():
                yield widgets.Button("Upload", variant="warning", id="force-upload-ok")
                yield widgets.Button(
                    "Cancel", variant="primary", id="force-upload-cancel"
                )

    def on_button_pressed(self, event: widgets.Button.Pressed) -> None:
        """Return True if the user chose to upload anyway."""
        if event.button.id == "force-upload-ok":
            self.dismiss(True)
        elif event.button.id == "force-upload-cancel":
            self.dismiss(False)


class UploadResultsDialog(screen.ModalScreen[None]):
    """Inform user that upload was completed and show files in object storage."""

    CSS_PATH = frcattend.view.CSS_FOLDER / "sync_dialogs.tcss"

    success: bool
    """True if the database was uploaded."""
    message: str
    """Uploaded object key on success, or error message on failure."""
    uploads: list[str] | None
    """Database files in object storage, or None if they could not be listed."""

    def __init__(self, success: bool, message: str, uploads: list[str] | None) -> None:
        """Specify upload outcome and files in object storage on initialization."""
        super().__init__()
        self.success = success
        self.message = message
        self.uploads = uploads

    def compose(self) -> app.ComposeResult:
        """Layout the dialog box."""
        with containers.Vertical(id="upload-results-dialog", classes="modal-dialog"):
            if self.success:
                yield widgets.Label("[bold green]Upload Complete[/bold green]")
                yield widgets.Static(f"Uploaded {self.message}")
            else:
                yield widgets.Label("[bold red]Upload Failed[/bold red]")
                yield widgets.Static(self.message)
            yield widgets.Static()
            yield widgets.Label("[bold]Files in Cloud Storage[/bold]")
            with containers.VerticalScroll(id="upload-results-files"):
                if self.uploads is None:
                    yield widgets.Static("[red]Unable to list files.[/red]")
                elif not self.uploads:
                    yield widgets.Static("No files have been uploaded.")
                else:
                    for key in self.uploads:
                        if self.success and key == self.message:
                            yield widgets.Static(f"[bold]{key}[/bold] (new)")
                        else:
                            yield widgets.Static(key)
            with containers.Horizontal():
                yield widgets.Button("OK", variant="primary", id="upload-results-ok")

    def on_button_pressed(self, event: widgets.Button.Pressed) -> None:
        """Dismiss the dialog when OK is pressed."""
        if event.button.id == "upload-results-ok":
            self.dismiss(None)


class DownloadChooseFileDialog(screen.ModalScreen[str | None]):
    """Choose which database file to download from object storage.

    The file with the largest checkin_id and latest timestamp is preselected.
    If no file has both, the user is warned and must choose a file. Dismisses
    with the chosen object key, or None if the user cancels.
    """

    CSS_PATH = frcattend.view.CSS_FOLDER / "sync_dialogs.tcss"

    db_objects: list[sync.DbObject]
    """Database files in object storage, newest first."""
    default: sync.DbObject | None
    """File that is preselected, or None if the user must choose."""

    def __init__(self, keys: list[str]) -> None:
        """Specify the object keys in object storage on initialization."""
        super().__init__()
        self.db_objects = sync.get_db_objects(keys)
        self.default = sync.get_default_db_object(self.db_objects)

    def compose(self) -> app.ComposeResult:
        """Layout the dialog box."""
        with containers.Vertical(id="download-choose-dialog", classes="modal-dialog"):
            yield widgets.Label("[bold]Download Database[/bold]")
            yield widgets.Static()
            if not self.db_objects:
                yield widgets.Static("No database files have been uploaded.")
            else:
                if self.default is None:
                    yield widgets.Static(self._conflict_warning())
                else:
                    yield widgets.Static(
                        "Choose a file to download. The most recent file is selected."
                    )
                yield widgets.Static(
                    "[yellow]The current database will be backed up and then "
                    "overwritten.[/yellow]"
                )
                with widgets.RadioSet(id="download-choose-files"):
                    for obj in self.db_objects:
                        yield widgets.RadioButton(
                            obj.key, value=obj == self.default, name=obj.key
                        )
            with containers.Horizontal():
                yield widgets.Button(
                    "OK",
                    variant="primary",
                    id="download-choose-ok",
                    disabled=self.default is None,
                )
                yield widgets.Button("Cancel", id="download-choose-cancel")

    def _conflict_warning(self) -> str:
        """Explain that the newest files disagree, so the user must choose."""
        most_checkins = self.db_objects[0]
        latest = max(self.db_objects, key=lambda obj: obj.timestamp)
        return (
            "[bold yellow]Warning:[/bold yellow] The file with the most check-ins "
            f"([bold]{most_checkins.key}[/bold]) is not the most recently "
            f"modified file ([bold]{latest.key}[/bold]). The databases on "
            "different computers may have diverged. Choose the file to download."
        )

    @textual.on(widgets.RadioSet.Changed, "#download-choose-files")
    def enable_ok(self) -> None:
        """Allow the user to press OK once a file has been chosen."""
        self.query_one("#download-choose-ok", widgets.Button).disabled = False

    def on_button_pressed(self, event: widgets.Button.Pressed) -> None:
        """Return the chosen object key, or None if cancelled."""
        if event.button.id == "download-choose-ok":
            radio_set = self.query_one("#download-choose-files", widgets.RadioSet)
            if radio_set.pressed_button is not None:
                self.dismiss(radio_set.pressed_button.name)
        elif event.button.id == "download-choose-cancel":
            self.dismiss(None)


class DownloadResultsDialog(screen.ModalScreen[None]):
    """Inform user whether the download succeeded and where the backup is."""

    CSS_PATH = frcattend.view.CSS_FOLDER / "sync_dialogs.tcss"

    success: bool
    """True if the database was downloaded."""
    message: str
    """Downloaded object key on success, or error message on failure."""
    backup_path: pathlib.Path | None
    """Backup of the previous database file, or None if no backup was made."""

    def __init__(
        self, success: bool, message: str, backup_path: pathlib.Path | None = None
    ) -> None:
        """Specify download outcome and backup file on initialization."""
        super().__init__()
        self.success = success
        self.message = message
        self.backup_path = backup_path

    def compose(self) -> app.ComposeResult:
        """Layout the dialog box."""
        with containers.Vertical(id="download-results-dialog", classes="modal-dialog"):
            if self.success:
                yield widgets.Label("[bold green]Download Complete[/bold green]")
                yield widgets.Static()
                yield widgets.Static(f"Downloaded [bold]{self.message}[/bold]")
                yield widgets.Static()
                yield widgets.Static("The previous database was backed up to:")
                yield widgets.Static(str(self.backup_path))
            else:
                yield widgets.Label("[bold red]Download Failed[/bold red]")
                yield widgets.Static()
                yield widgets.Static(self.message)
                yield widgets.Static()
                yield widgets.Static("The current database was not changed.")
            with containers.Horizontal():
                yield widgets.Button("OK", variant="primary", id="download-results-ok")

    def on_button_pressed(self, event: widgets.Button.Pressed) -> None:
        """Dismiss the dialog when OK is pressed."""
        if event.button.id == "download-results-ok":
            self.dismiss(None)
