"""Modal dialog definitions."""

import sqlite3

from textual import app, containers, screen, widgets

import frcattend.view
from frcattend import config, model
from frcattend.view import status_table, validators


class StudentDialog(screen.ModalScreen):
    """A dialog for adding or editing student details."""

    CSS_PATH = frcattend.view.CSS_FOLDER / "student_dialog.tcss"

    student: model.Student | None
    _dbase: model.DBase
    _is_new_student: bool
    """Whether this dialog was opened to add a new student (vs. edit one)."""

    def __init__(self, student: model.Student | None = None) -> None:
        """Initialize with student information if provided."""
        super().__init__()
        self.student = student
        self._is_new_student = student is None
        if config.settings.db_path is None:
            raise model.DBaseError("No database file selected.")
        self._dbase = model.DBase(config.settings.db_path)

    def compose(self) -> app.ComposeResult:
        """Create and arrange dialog widgets."""
        title = "Add New Student" if self.student is None else "Edit Student"
        with containers.Vertical(id="student-dialog", classes="modal-dialog"):
            yield widgets.Label(title, classes="emphasis")
            # Display read-only ID for existing students, but don't show input for new students
            if self.student is not None:
                yield widgets.Label(f"Student ID: {self.student.student_id}")
            yield widgets.Input(
                value=self.student.first_name if self.student else "",
                placeholder="First Name",
                id="s-fname",
                validators=[validators.NotEmpty()],
            )
            yield widgets.Input(
                value=self.student.last_name if self.student else "",
                placeholder="Last Name",
                id="s-lname",
                validators=[validators.NotEmpty()],
            )
            yield widgets.Input(
                value=self.student.email if self.student else "",
                placeholder="Email",
                id="s-email",
                validators=[validators.NotEmpty()],
            )
            yield widgets.Input(
                value=(
                    str(self.student.grad_year)
                    if self.student and self.student.grad_year
                    else ""
                ),
                placeholder="Graduation Year",
                id="s-gyear",
                validators=[validators.NotEmpty(), validators.IsYear()],
            )
            yield status_table.StatusTable(self.student, widget_id="s-status")
            yield widgets.Button("Add Status", id="add-status")

            yield widgets.Static()
            with containers.Horizontal(id="attendance-actions"):
                yield widgets.Button("Save", variant="primary", id="save-student")
                yield widgets.Button("Cancel", id="cancel-student")

    def on_mount(self) -> None:
        self.query_one("#s-fname", widgets.Input).focus()

    def _student_from_form(self) -> model.Student:
        """Build a Student object from the current form field values."""
        data = {
            "first_name": self.query_one("#s-fname", widgets.Input).value,
            "last_name": self.query_one("#s-lname", widgets.Input).value,
            "email": self.query_one("#s-email", widgets.Input).value or None,
            "grad_year": (
                int(self.query_one("#s-gyear", widgets.Input).value)
                if self.query_one("#s-gyear", widgets.Input).value
                else None
            ),
            "student_id": self.student.student_id if self.student else "",
        }
        return model.Student(**data)

    def _form_is_valid(self) -> bool:
        """Check whether the required student fields have valid values."""
        inputs = [
            self.query_one("#s-fname", widgets.Input),
            self.query_one("#s-lname", widgets.Input),
            self.query_one("#s-email", widgets.Input),
            self.query_one("#s-gyear", widgets.Input),
        ]
        for field in inputs:
            field.validate(field.value)
        if all(field.is_valid for field in inputs):
            return True
        self.app.notify(
            "Please fill in name, email, and graduation year before adding a status.",
            severity="error",
        )
        return False

    def _on_status_dialog_closed(self, saved: bool | None) -> None:
        """Refresh the status table, removing an orphaned student if unsaved."""
        table = self.query_one("#s-status", status_table.StatusTable)
        if saved:
            table.populate_rows()
            return
        if (
            self._is_new_student
            and self.student is not None
            and not model.Status.get_by_student_id(
                self._dbase, self.student.student_id
            )
        ):
            self.student.delete(self._dbase)
            self.student = None
            table.student = None
            table.populate_rows()

    def on_button_pressed(self, event: widgets.Button.Pressed) -> None:
        if event.button.id == "add-status":
            if self.student is None:
                if not self._form_is_valid():
                    return
                student = self._student_from_form()
                try:
                    student.add(self._dbase)
                except sqlite3.IntegrityError as err:
                    self.app.notify(f"Error adding student: {err}", severity="error")
                    return
                self.student = student
                table = self.query_one("#s-status", status_table.StatusTable)
                table.student = self.student
                table.populate_rows()
                self.app.notify(f"Student record created. ID: {student.student_id}")

            self.app.push_screen(
                status_table.EditStatusDialog(
                    dbase=self._dbase, student=self.student, status_id=None
                ),
                callback=self._on_status_dialog_closed,
            )

        elif event.button.id == "save-student":
            if self.student is None or not model.Status.get_by_student_id(
                self._dbase, self.student.student_id
            ):
                self.app.notify(
                    "Please add a status before saving the student.",
                    severity="error",
                )
                return
            student = self._student_from_form()
            try:
                student.update(self._dbase)
            except sqlite3.IntegrityError as err:
                self.app.notify(f"Error saving student: {err}", severity="error")
                return
            self.dismiss(student)
        elif event.button.id == "cancel-student":
            self.dismiss(None)
