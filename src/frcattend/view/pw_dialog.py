"""Prompt user for a password."""

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
        hashed_password = config.hash_password(password)
        error_msg = self.query_one("#password-error", widgets.Static)
        try:
            pin_hash = config.SecurityPin.get_pin_hash()
        except config.SecurityError:
            error_msg.update("[bold red]No PIN has been set[/]")
            return
        if hashed_password == pin_hash:
            self.dismiss(True)  # Dismiss with success
        else:
            error_msg.update("[bold red]Incorrect Password[/]")
            self.query_one("#password-input", widgets.Input).value = ""

    @staticmethod
    def show(
        submit_callback: screen.ScreenResultCallbackType, exit_on_cancel=True
    ) -> None:
        """Display the dialog and pass the result to the callback method.

        If no PIN has been set yet, display the dialog for setting a new PIN
        instead. Setting the PIN counts as a successful login.
        """
        try:
            config.SecurityPin.get_pin_hash()
        except config.SecurityError:
            pin_dialog = SetPinDialog()

            def _on_pin_set(pin_set: bool | None) -> None:
                if not pin_set and exit_on_cancel:
                    pin_dialog.app.exit(message="No PIN set.")
                else:
                    submit_callback(bool(pin_set))

            pin_dialog.app.push_screen(pin_dialog, callback=_on_pin_set)
            return
        password_dialog = PasswordPrompt(exit_on_cancel)
        password_dialog.app.push_screen(password_dialog, callback=submit_callback)


class SetPinDialog(screen.ModalScreen[bool]):
    """A modal screen for setting a new PIN or changing the existing PIN.

    Dismisses with True if the new PIN was saved, otherwise False.
    """

    CSS_PATH = frcattend.view.CSS_FOLDER / "pw_dialog.tcss"

    require_current: bool
    """Require the current PIN if true. False when no PIN has been set yet."""

    def __init__(self) -> None:
        """Determine if a PIN has already been set."""
        super().__init__()
        try:
            config.SecurityPin.get_pin_hash()
            self.require_current = True
        except config.SecurityError:
            self.require_current = False

    def compose(self) -> app.ComposeResult:
        """Build the set PIN dialog box."""
        title = "Change PIN" if self.require_current else "Set a New PIN"
        with containers.Vertical(id="set-pin-dialog", classes="modal-dialog"):
            yield widgets.Label(title, classes="emphasis")
            if self.require_current:
                yield widgets.Label("Current PIN")
                yield widgets.Input(password=True, id="set-pin-current")
            yield widgets.Label("New PIN")
            yield widgets.Input(password=True, id="set-pin-new")
            yield widgets.Label("Confirm New PIN")
            yield widgets.Input(password=True, id="set-pin-confirm")
            yield widgets.Static("", id="set-pin-error")
            with containers.Horizontal(classes="centered"):
                yield widgets.Button("OK", variant="primary", id="set-pin-ok")
                yield widgets.Button("Show PIN", id="set-pin-show")
                yield widgets.Button("Cancel", id="set-pin-cancel")

    def on_mount(self) -> None:
        """Put focus on the first input box."""
        self.query(widgets.Input).first().focus()

    def on_button_pressed(self, event: widgets.Button.Pressed) -> None:
        if event.button.id == "set-pin-ok":
            self.save_pin()
        elif event.button.id == "set-pin-show":
            self.toggle_show_pin(event.button)
        elif event.button.id == "set-pin-cancel":
            self.dismiss(False)

    def toggle_show_pin(self, button: widgets.Button) -> None:
        """Switch the input boxes between showing and hiding the PIN."""
        inputs = self.query(widgets.Input)
        hide = not inputs.first().password
        for pin_input in inputs:
            pin_input.password = hide
        button.label = "Show PIN" if hide else "Hide PIN"

    def on_input_submitted(self, event: widgets.Input.Submitted) -> None:
        """Move to the next input box, or save from the last one."""
        if event.input.id == "set-pin-confirm":
            self.save_pin()
        else:
            self.focus_next()

    def save_pin(self) -> None:
        """Save the new PIN if the inputs are valid."""
        error_msg = self.query_one("#set-pin-error", widgets.Static)
        new_input = self.query_one("#set-pin-new", widgets.Input)
        confirm_input = self.query_one("#set-pin-confirm", widgets.Input)
        current_pin = ""
        if self.require_current:
            current_pin = self.query_one("#set-pin-current", widgets.Input).value
        if not new_input.value:
            error_msg.update("[bold red]New PIN cannot be blank[/]")
            new_input.focus()
            return
        if new_input.value != confirm_input.value:
            error_msg.update("[bold red]New PINs do not match[/]")
            new_input.value = ""
            confirm_input.value = ""
            new_input.focus()
            return
        if not config.SecurityPin.set_pin(current_pin, new_input.value):
            error_msg.update("[bold red]Incorrect current PIN[/]")
            current_input = self.query_one("#set-pin-current", widgets.Input)
            current_input.value = ""
            current_input.focus()
            return
        self.dismiss(True)
