"""View roster and add new students."""

import sqlite3
from typing import Optional

import textual
import textual.css.query
from textual import app, binding, containers, screen, widgets

from frcattend import config, model
from frcattend.features import emailer, qr_code_generator
import frcattend.view
from frcattend.view import confirm_dialogs, student_dialog, inactive_toggle


def success(message: str) -> str:
    """Format a success message for display in the status widget."""
    return f"[ansi_bright_green]{message}[/]"


def error(message: str) -> str:
    """Format an error message for display in the status widget."""
    return f"[ansi_bright_red]{message}[/]"


class StudentScreen(screen.Screen):
    """Add and edit students."""

    dbase: model.DBase
    """Connection to Sqlite Database."""
    _selected_student_id: Optional[str]
    """Currently selected student."""
    _students: dict[str, model.Student]
    """List of students currently loaded in the datatable."""

    CSS_PATH = frcattend.view.CSS_FOLDER / "student_screen.tcss"
    BINDINGS = [
        binding.Binding("escape", "app.pop_screen", "Back to Main Screen", show=True),
    ]

    def __init__(self) -> None:
        """Initialize the databae connection."""
        super().__init__()
        if config.settings.db_path is None:
            raise model.DBaseError("No database file selected.")
        self.dbase = model.DBase(config.settings.db_path)
        self._students = {}

    def compose(self) -> app.ComposeResult:
        """Build the management screen's user interface."""
        yield widgets.Header()
        with containers.Horizontal():
            with containers.Vertical(id="student-list-container"):
                yield widgets.Label("Student List")
                yield widgets.DataTable(zebra_stripes=True, id="student-table")
            with containers.Vertical(id="students-actions-container"):
                yield widgets.Label("Actions", classes="emphasis")
                with containers.ScrollableContainer():
                    yield inactive_toggle.InactiveStudentToggle(
                        id="students-show-inactive-toggle"
                    )
                    yield widgets.Static(
                        "No student selected",
                        id="students-selection-indicator",
                        classes="selection-info",
                    )
                    yield widgets.Static()
                    yield widgets.Button(
                        "Add Student",
                        variant="success",
                        id="add-student",
                        tooltip="Add a new student to the database.",
                    )
                    yield widgets.Button(
                        "Edit Selected",
                        id="edit-student",
                        disabled=True,
                        tooltip="Edit data for a student.",
                    )
                    yield widgets.Static()
                    yield widgets.Label("Communication", classes="emphasis")
                    yield widgets.Button(
                        "Generate QR Codes",
                        id="generate-qr-codes",
                        tooltip=(
                            "Generate QR codes for all students and "
                            "save them to the QR code folder."
                        ),
                    )
                    yield widgets.Button(
                        "Email QR Code to Selected",
                        id="email-qr",
                        disabled=True,
                        tooltip="Email a QR code to the selected student.",
                    )
                    yield widgets.Button(
                        "Email All QR Codes",
                        id="email-all-qr",
                        tooltip="Email QR codes to ALL students.",
                    )
                    yield widgets.Static(id="status-message", classes="status")
        yield widgets.Footer()

    def on_mount(self) -> None:
        """Initialize the datatable widget."""
        self.table = self.query_one(widgets.DataTable)
        self.table.cursor_type = "row"
        self.table.add_columns(
            "ID", "Last Name", "First Name", "Email", "Grad Year", "Deactivated On"
        )
        self.load_student_data(False)
        self._selected_student_id = None

    def _add_progress_bar(self, total: int | None, name: str) -> widgets.ProgressBar:
        """Add a progress bar for sending emails or generating QR Codes."""
        pbar = widgets.ProgressBar(total, name=name, id="qr-progress-bar")
        container = self.query_one("#students-actions-container", containers.Vertical)
        container.mount(pbar)
        return pbar

    def _update_progress_bar(self, total: int, progress: int) -> None:
        """Update the progress bar."""
        try:
            pbar = self.query_one("#qr-progress-bar", widgets.ProgressBar)
        except textual.css.query.NoMatches:
            return
        pbar.update(total=total, progress=progress)

    def _advance_progress_bar(self) -> None:
        """Advanced the progress bar one step."""
        try:
            pbar = self.query_one("#qr-progress-bar", widgets.ProgressBar)
        except textual.css.query.NoMatches:
            return
        pbar.advance()

    def _remove_progress_bar(self) -> None:
        """Remove the progress bar if mounted."""
        try:
            pbar = self.query_one("#qr-progress-bar", widgets.ProgressBar)
        except textual.css.query.NoMatches:
            return
        pbar.remove()

    def load_student_data(self, show_inactive: bool) -> None:
        """Load student data into the datatable widget."""
        self.table.clear()
        textual.log(f"Loading student data, show_inactive={show_inactive}")
        self._students = {
            student.student_id: student
            for student in model.Student.get_all(
                self.dbase, include_inactive=show_inactive
            )
        }
        for student in self._students.values():
            self.table.add_row(
                student.student_id,
                student.last_name,
                student.first_name,
                student.email,
                str(student.grad_year),
                student.deactivated_on,
                key=student.student_id,
            )
        status_widget = self.query_one("#status-message", widgets.Static)
        status_widget.update(success(f"Loaded {len(self._students)} students."))

    def on_data_table_row_selected(self, event: widgets.DataTable.RowSelected) -> None:
        """Select a row in the datatable."""
        self._selected_student_id = event.row_key.value
        if self._selected_student_id is None:
            return
        self.query_one("#edit-student", widgets.Button).disabled = False
        student = self._students[self._selected_student_id]
        self.query_one("#email-qr", widgets.Button).disabled = not (
            student and student.email
        )
        self.update_selected(
            f"[bold]Selected:[/bold]\n{student.first_name} "
            f"{student.last_name}\nID: {student.student_id}"
        )

    @textual.on(widgets.Switch.Changed, ".toggle-inactive-students-switch")
    def on_active_toggle_changed(self, message: widgets.Switch.Changed) -> None:
        """Reload student data when the active/inactive toggle is changed."""
        self.notify(f"Show inactive: {message.value}", timeout=4)
        self.load_student_data(message.value)
        self._selected_student_id = None
        self.query_one("#edit-student", widgets.Button).disabled = True
        self.query_one("#email-qr", widgets.Button).disabled = True
        self.update_selected("No student selected")

    async def on_button_pressed(self, event: widgets.Button.Pressed) -> None:
        """Respond to button presses."""
        if event.button.id == "add-student":
            await self.action_add_student()
        elif event.button.id == "edit-student":
            await self.action_edit_student()
        elif event.button.id == "email-qr":
            await self.action_email_qr(all_students=False)
        elif event.button.id == "email-all-qr":
            await self.action_email_qr(all_students=True)
        elif event.button.id == "generate-qr-codes":
            self._add_progress_bar(None, "Generate QR Codes")
            self.generate_qr_codes()

    async def action_add_student(self) -> None:
        """Show the student dialog and add a new student."""

        def on_dialog_closed(student: model.Student | None):
            if student is None:
                return
            try:
                student.add(self.dbase)
            except sqlite3.IntegrityError as err:
                self.update_status(
                    "[red]Error adding student "
                    f"{student.first_name} {student.last_name}.[/]\n"
                    f"Error Description:\n{err}"
                )
            else:
                self.load_student_data(
                    self.query_one(
                        "#students-show-inactive-switch", widgets.Switch
                    ).value
                )
                self.query_one("#status-message", widgets.Static).update(
                    success(f"Student added successfully. ID: {student.student_id}")
                )

        await self.app.push_screen(
            student_dialog.StudentDialog(), callback=on_dialog_closed
        )

    async def action_edit_student(self) -> None:
        if self._selected_student_id is None:
            return
        student = self._students[self._selected_student_id]

        def on_dialog_closed(student: model.Student | None):
            if student is None or self._selected_student_id is None:
                return
            student.update(self.dbase)
            self.update_status(success("Student updated successfully."))
            inactive_switch = self.query_one(
                    "#students-show-inactive-toggle Switch", widgets.Switch)
            self.load_student_data(inactive_switch.value)
        await self.app.push_screen(
            student_dialog.StudentDialog(student=student), callback=on_dialog_closed
        )

    @textual.work(thread=True)
    async def generate_qr_codes(self) -> None:
        """Generate all QR codes."""
        if config.settings.qr_code_dir is None:
            self.update_status(
                "[red] Cannot generate QR codes because "
                "no QR code path is defined in config file.[/]"
            )
            return
        qr_generator = qr_code_generator.generate_all_qr_codes(
            config.settings.qr_code_dir, self.dbase
        )
        total_students = next(qr_generator)[1]
        self.app.call_from_thread(lambda: self._update_progress_bar(total_students, 0))
        failed_codes = []
        for student_id, status in qr_generator:
            if not status:
                failed_codes.append(student_id)
            self.app.call_from_thread(self._advance_progress_bar)
        status_message = success(
            f"Created {total_students - len(failed_codes)} QR Codes in folder "
            f"{config.settings.qr_code_dir}\n"
        )
        if failed_codes:
            status_message += error("Failed Codes: " + ", ".join(failed_codes))
        self.update_status(status_message)
        self.app.call_from_thread(self._remove_progress_bar)

    async def action_email_qr(self, all_students: bool) -> None:
        """Email QR codes to students."""
        if all_students:
            students_to_email = model.Student.get_all(self.dbase)
            self._add_progress_bar(len(students_to_email), "Send Emails")
        elif self._selected_student_id:
            student = model.Student.get_by_id(self.dbase, self._selected_student_id)
            if student is None:
                self.update_status(
                    error(f"Unable to locate student {self._selected_student_id}")
                )
                return
            else:
                students_to_email = [student]
        else:
            self.update_status(error("No student selected."))
            return

        def _email_all_students(confirmed: bool | None) -> None:
            if confirmed:
                self.send_emails_worker(students_to_email)
                self.update_status(
                    success(f"Emailed QR codes to {len(students_to_email)}")
                )

        if all_students:
            await self.app.push_screen(
                confirm_dialogs.GeneralConfirmDialog("email all students"),
                callback=_email_all_students,
            )
        else:
            self.send_emails_worker(students_to_email)

    @textual.work(thread=True)
    async def send_emails_worker(self, students: list[model.Student]) -> None:
        """Send QR emails to students."""
        if config.settings.qr_code_dir is None:
            self.update_status(
                success(
                    "Cannot send emails with QR codes because "
                    "no QR code path is defined in config file."
                )
            )
            return
        email_sender = emailer.send_all_emails(config.settings.qr_code_dir, students)
        failed_codes = []
        for student_id, status in email_sender:
            if not status:
                failed_codes.append(student_id)
            self.app.call_from_thread(self._advance_progress_bar)
        status_message = (
            f"[birght_green]Sent {len(students) - len(failed_codes)} email messages "
            f"with QR codes in folder {config.settings.qr_code_dir}\n"
        )
        if failed_codes:
            status_message += error("Failed Emails: " + ", ".join(failed_codes))
        self.update_status(status_message)
        self.app.call_from_thread(self._remove_progress_bar)

    def update_status(self, message: str) -> None:
        """Update the text in the status widget."""
        self.query_one("#status-message", widgets.Static).update(message)

    def update_selected(self, message: str) -> None:
        self.query_one("#students-selection-indicator", widgets.Static).update(message)
