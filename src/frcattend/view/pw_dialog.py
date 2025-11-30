"""Prompt user for a password."""

import hashlib

from textual import app, containers, screen, widgets

import frcattend.view
from frcattend import config


class PasswordPrompt(screen.ModalScreen[bool]):
    """A modal screen to ask for the management password."""

    CSS_PATH = frcattend.view.CSS_FOLDER / "pw_dialog.tcss"

    exit_on_cancel: bool
    """Exit from application when dialog canceled if true."""

    def __init__(self, exit_on_cancel: bool) -> None:
        """Set behavior for cancel button."""
        super().__init__()
        self.exit_on_cancel = exit_on_cancel

    def compose(self) -> app.ComposeResult:
        """Build the password dialog box."""
        with containers.Vertical(id="password-dialog", classes="modal-dialog"):
            yield widgets.Label("Enter Management Password", classes="emphasis")
            yield widgets.Input(password=True, id="password-input")
            yield widgets.Static("", id="password-error")
            with containers.Horizontal(classes="centered"):
                yield widgets.Button("Submit", variant="primary", id="submit-password")
                yield widgets.Button("Cancel", id="cancel-password")

    def on_mount(self) -> None:
        """Put focus on the input box."""
        self.query_one("#password-input", widgets.Input).focus()

    def on_button_pressed(self, event: widgets.Button.Pressed) -> None:
        if event.button.id == "submit-password":
            self.check_password()
        elif event.button.id == "cancel-password":
            if self.exit_on_cancel:
                self.app.exit(message="No password provided.")
            else:
                self.app.pop_screen()

    def on_input_submitted(self, event: widgets.Input.Submitted) -> None:
        self.check_password()

    def check_password(self) -> None:
        password = self.query_one("#password-input", widgets.Input).value
        hashed_password = hashlib.sha256(password.encode()).hexdigest()
        error_msg = self.query_one("#password-error", widgets.Static)
        if hashed_password == config.settings.password_hash:
            self.dismiss(True)  # Dismiss with success
        else:
            error_msg.update("[bold red]Incorrect Password[/]")
            self.query_one("#password-input", widgets.Input).value = ""

    @staticmethod
    def show(
        submit_callback: screen.ScreenResultCallbackType, exit_on_cancel=True
    ) -> None:
        """Display the dialog and pass the result to the callback method."""
        password_dialog = PasswordPrompt(exit_on_cancel)
        password_dialog.app.push_screen(password_dialog, callback=submit_callback)
