"""Confirmation Dialogs."""

from textual import app, containers, screen, widgets

import frcattend.view


class DeleteConfirmDialog(screen.ModalScreen):
    """A confirmation dialog for deleting students."""

    CSS_PATH = frcattend.view.CSS_FOLDER / "confirm_dialogs.tcss"

    student_name: str
    student_id: str

    def __init__(self, student_name: str, student_id: str) -> None:
        """Include student name and ID in confirmation dialog."""
        self.student_name = student_name
        self.student_id = student_id
        super().__init__()

    def compose(self) -> app.ComposeResult:
        """Layout the dialog screen."""
        with containers.Vertical(id="delete-dialog", classes="modal-dialog"):
            yield widgets.Label("[bold red]Confirm Deletion[/bold red]")
            yield widgets.Static()
            yield widgets.Label("Are you sure you want to delete:")
            yield widgets.Label(f"[bold]{self.student_name}[/bold]")
            yield widgets.Label(f"ID: {self.student_id}")
            yield widgets.Static()
            yield widgets.Label("[yellow]This action cannot be undone![/yellow]")
            yield widgets.Static()
            with containers.Horizontal():
                yield widgets.Button("Delete", variant="error", id="confirm-delete")
                yield widgets.Button("Cancel", variant="primary", id="cancel-delete")

    def on_button_pressed(self, event: widgets.Button.Pressed) -> None:
        if event.button.id == "confirm-delete":
            self.dismiss(True)
        elif event.button.id == "cancel-delete":
            self.dismiss(False)


class GeneralConfirmDialog(screen.ModalScreen):
    """General confirmation dialog."""

    CSS_PATH = frcattend.view.CSS_FOLDER / "confirm_dialogs.tcss"

    message: str
    """Message displayed to user in confirmation dialog."""

    def __init__(self, message: str) -> None:
        """Include task message in confirmation dialog."""
        super().__init__()
        self.message = message

    def compose(self) -> app.ComposeResult:
        """Layout the dialog box."""
        with containers.Vertical(id="confirm-dialog", classes="modal-dialog"):
            yield widgets.Label("[bold red]Confirm Action[/bold red]")
            yield widgets.Static()
            yield widgets.Label(f"Are you sure you want to {self.message}?")
            with containers.Horizontal():
                yield widgets.Button("Delete", variant="error", id="confirm-action")
                yield widgets.Button("Cancel", variant="primary", id="cancel-action")

    def on_button_pressed(self, event: widgets.Button.Pressed) -> None:
        """Take action if confirmed."""
        if event.button.id == "confirm-action":
            self.dismiss(True)
        elif event.button.id == "cancel-action":
            self.dismiss(False)
