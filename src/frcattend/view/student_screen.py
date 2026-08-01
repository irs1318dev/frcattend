"""View roster and add new students."""

import datetime
import sqlite3

import textual
import textual.css.query
from textual import app, binding, containers, events, message, screen, widgets
from textual.widgets.data_table import ColumnKey

import frcattend.view
from frcattend import config, model
from frcattend.features import emailer, qr_code_generator
from frcattend.view import confirm_dialogs, selector_widgets, student_dialog


def success(message: str) -> str:
    """Format a success message for display in the status widget."""
    return f"[ansi_bright_green]{message}[/]"


def error(message: str) -> str:
    """Format an error message for display in the status widget."""
    return f"[ansi_bright_red]{message}[/]"


def format_rookie(is_rookie: bool | None) -> str:
    """Format the is_rookie field for display in the student table."""
    return "[yellow]yes[/]" if is_rookie else ""


class StudentTable(widgets.DataTable):
    """DataTable for the student roster that exposes raw click events.

    DataTable's own click handling calls `event.stop()` for row/cell clicks,
    so a click handler on this widget can't be registered on an ancestor.
    """

    class RowDoubleClicked(message.Message):
        """Sent when a row is double-clicked."""

        student_id: str

        def __init__(self, student_id: str) -> None:
            """Set the student ID of the double-clicked row."""
            super().__init__()
            self.student_id = student_id

    def on_click(self, event: events.Click) -> None:
        """Notify the parent screen when a row is double-clicked."""
        if event.chain < 2:
            return
        row_index = event.style.meta.get("row")
        if row_index is None or row_index < 0 or row_index >= len(self.ordered_rows):
            return
        student_id = self.ordered_rows[row_index].key.value
        if student_id is None:
            return
        self.post_message(self.RowDoubleClicked(student_id))


class StudentScreen(screen.Screen):
    """Add and edit students."""

    dbase: model.DBase
    """Connection to Sqlite Database."""
    _selected_student_id: str | None
    """Currently selected student."""
    _students: dict[str, model.Student]
    """List of students currently loaded in the datatable."""
    _sort_column_key: ColumnKey | None
    """Column the student table is currently sorted by, if any."""
    _sort_reverse: bool
    """Whether the current column sort is descending."""

    CSS_PATH = frcattend.view.CSS_FOLDER / "student_screen.tcss"
    # ruff: ignore[RUF012]
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
                yield StudentTable(zebra_stripes=True, id="student-table")
            with containers.Vertical(id="students-actions-container"):
                yield selector_widgets.StatusSelector(id="status-selector")
                yield selector_widgets.GradYearSelector(
                    self.dbase, id="grad-year-selector"
                )
                yield selector_widgets.GoBackSelector(value=None, id="asof-selector")
                yield widgets.Static(id="status-message", classes="status")
                yield widgets.Static(
                    "No student selected",
                    id="students-selection-indicator",
                    classes="selection-info",
                )
                with containers.ScrollableContainer():
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
                    yield widgets.Static(classes="spacer")
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
        yield widgets.Footer()

    def on_mount(self) -> None:
        """Initialize the datatable widget."""
        self.table = self.query_one(widgets.DataTable)
        self.table.cursor_type = "row"
        self.table.add_columns(
            ("ID", "id"),
            ("Last Name", "last_name"),
            ("First Name", "first_name"),
            ("Status", "status"),
            ("Grad Year", "grad_year"),
        )
        self._sort_column_key = None
        self._sort_reverse = False
        self.load_student_data()
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

    def load_student_data(self) -> None:
        """Load student data into the datatable widget."""
        self.table.clear()
        selected_stages = self.query_one(
            "#status-selector", selector_widgets.StatusSelector
        ).selected
        grad_year = self.query_one(
            "#grad-year-selector", selector_widgets.GradYearSelector
        ).value
        asof_selector = self.query_one(
            "#asof-selector", selector_widgets.GoBackSelector
        )
        if asof_selector.is_valid and asof_selector.value:
            asof_date = datetime.date.fromisoformat(asof_selector.value)
        else:
            asof_date = datetime.date.today()
        students = model.Student.get_with_status(
            self.dbase, asof_date=asof_date, stages=selected_stages
        )
        if len(grad_year) == 4:
            students = [
                student for student in students if student.grad_year == int(grad_year)
            ]
        self._students = {student.student_id: student for student in students}
        for student in self._students.values():
            self.table.add_row(
                student.student_id,
                student.last_name,
                student.first_name,
                student.status.stage.value if student.status else "",
                # format_rookie(student.is_rookie),
                str(student.grad_year),
                key=student.student_id,
            )
        status_widget = self.query_one("#status-message", widgets.Static)
        status_widget.update(success(f"Loaded {len(self._students)} students."))

    @textual.on(widgets.SelectionList.SelectedChanged, "#status-selector")
    def on_status_selector_changed(self) -> None:
        """Reload student data when the selected stages change."""
        self.load_student_data()

    @textual.on(widgets.Input.Changed, "#grad-year-selector")
    def on_grad_year_selector_changed(self) -> None:
        """Reload student data when the grad year filter changes."""
        self.load_student_data()

    @textual.on(widgets.Input.Changed, "#asof-selector")
    def on_asof_selector_changed(self, event: widgets.Input.Changed) -> None:
        """Reload student data when the as-of date filter changes."""
        if event.input.is_valid:
            self.load_student_data()

    async def on_student_table_row_double_clicked(
        self, event: StudentTable.RowDoubleClicked
    ) -> None:
        """Open the edit dialog for the double-clicked student."""
        self._selected_student_id = event.student_id
        await self.action_edit_student()

    def on_data_table_row_highlighted(
        self, event: widgets.DataTable.RowHighlighted
    ) -> None:
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

    def on_data_table_header_selected(
        self, event: widgets.DataTable.HeaderSelected
    ) -> None:
        """Sort the table by the clicked column, toggling direction on repeat clicks."""
        if event.column_key == self._sort_column_key:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_column_key = event.column_key
            self._sort_reverse = False
        sort_key = int if event.column_key.value == "grad_year" else None
        self.table.sort(event.column_key, key=sort_key, reverse=self._sort_reverse)

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
                self.load_student_data()
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
            self.load_student_data()

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
