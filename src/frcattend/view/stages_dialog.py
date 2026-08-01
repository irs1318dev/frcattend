"""Make batch edits to student status."""

import datetime

import textual
from textual import app, containers, events, message, screen, widgets

import frcattend.view
from frcattend import config, model
from frcattend.view import confirm_dialogs, selector_widgets


class StudentTable(widgets.DataTable):
    """DataTable for the student roster that exposes raw click events.

    DataTable's own click handling calls `event.stop()` for row/cell clicks,
    so a click handler on this widget can't be registered on an ancestor.
    """

    dbase: model.DBase
    """Connection to Sqlite Database."""
    students: dict[str, model.Student]
    """Students currently loaded into the table, keyed by student_id."""
    selected: set[str]
    """IDs of students currently checked in the Select column."""

    class SelectionChanged(message.Message):
        """Sent when the set of selected students changes."""

        selected: set[str]

        def __init__(self, selected: set[str]) -> None:
            """Set the currently selected student IDs."""
            super().__init__()
            self.selected = selected

    def __init__(self, dbase: model.DBase, *args, **kwargs) -> None:
        """Set link to database."""
        super().__init__(*args, **kwargs, zebra_stripes=True)
        self.dbase = dbase
        self.students = {}
        self.selected = set()

    def on_mount(self) -> None:
        """Set up table columns."""
        self.cursor_type = "row"
        self.add_columns(
            ("Select", "select"),
            ("Last Name", "last_name"),
            ("First Name", "first_name"),
            ("Stage", "stage"),
            ("Grad Year", "grad_year"),
        )

    def update_table(
        self,
        stages: list[model.Stage] | None = None,
        grad_year: str | None = None,
    ) -> None:
        """Populate the table with students, filtered by the given criteria."""
        self.clear(columns=False)
        students = model.Student.get_with_status(self.dbase, stages=stages)
        if grad_year and len(grad_year) == 4:
            students = [
                student for student in students if student.grad_year == int(grad_year)
            ]
        self.students = {student.student_id: student for student in students}
        self.selected &= self.students.keys()
        for key, stu in self.students.items():
            self.add_row(
                self._checkbox_text(key),
                stu.last_name,
                stu.first_name,
                stu.status.stage.value if stu.status else "",
                str(stu.grad_year),
                key=key,
            )
        self.refresh()

    def _checkbox_text(self, student_id: str) -> str:
        """Return the checkbox glyph reflecting a student's selection state."""
        return "[green]☑[/]" if student_id in self.selected else "☐"

    def toggle_selection(self, student_id: str) -> None:
        """Flip a student's selection state and refresh its checkbox cell."""
        if student_id in self.selected:
            self.selected.discard(student_id)
        else:
            self.selected.add(student_id)
        self.update_cell(student_id, "select", self._checkbox_text(student_id))
        self.post_message(self.SelectionChanged(set(self.selected)))

    def select_all(self) -> None:
        """Check every row currently in the table."""
        self.selected = set(self.students.keys())
        for student_id in self.students:
            self.update_cell(student_id, "select", self._checkbox_text(student_id))
        self.post_message(self.SelectionChanged(set(self.selected)))

    def clear_selection(self) -> None:
        """Uncheck every row currently in the table."""
        cleared = self.selected & self.students.keys()
        self.selected.clear()
        for student_id in cleared:
            self.update_cell(student_id, "select", self._checkbox_text(student_id))
        self.post_message(self.SelectionChanged(set(self.selected)))

    def on_click(self, event: events.Click) -> None:
        """Toggle a student's selection when its Select checkbox is clicked."""
        row_index = event.style.meta.get("row")
        column_index = event.style.meta.get("column")
        if row_index is None or column_index is None:
            return
        if row_index < 0 or row_index >= len(self.ordered_rows):
            return
        if self.ordered_columns[column_index].key.value != "select":
            return
        student_id = self.ordered_rows[row_index].key.value
        if student_id is None:
            return
        self.toggle_selection(student_id)

    def on_data_table_row_selected(self, event: widgets.DataTable.RowSelected) -> None:
        """Toggle the highlighted student's selection when Enter is pressed."""
        student_id = event.row_key.value
        if student_id is not None:
            self.toggle_selection(student_id)


class BatchAddStagesDialog(screen.ModalScreen):
    """Change status on multiple students at once."""

    _dbase: model.DBase
    """Connection to Sqlite Database."""

    CSS_PATH = frcattend.view.CSS_FOLDER / "stages_dialog.tcss"

    def __init__(self) -> None:
        """Initialize the screen."""
        super().__init__()
        if config.settings.db_path is None:
            raise model.DBaseError("No database file selected.")
        self._dbase = model.DBase(config.settings.db_path)

    def compose(self) -> app.ComposeResult:
        """Create and arrange UI widgets."""
        with containers.Vertical(id="batch-stages-dialog", classes="modal-dialog"):
            yield widgets.Label("Add new Stages", classes="emphasis")
            with containers.Horizontal(id="batch-stages-body"):
                yield StudentTable(self._dbase, id="batch-student-table")
                with containers.Vertical(id="batch-stages-selectors"):
                    yield selector_widgets.StatusSelector(id="batch-status-selector")
                    yield selector_widgets.GradYearSelector(
                        self._dbase, id="batch-grad-year-selector"
                    )
                    yield widgets.Button("Select All", id="select-all-students")
                    yield widgets.Button(
                        "Clear Selection", id="clear-selection-students"
                    )
                    yield widgets.Label("New Status")
                    yield widgets.Select(
                        [(stage.value.title(), stage) for stage in model.Stage],
                        prompt="Select Stage",
                        id="new-status-select",
                    )
                    yield widgets.Label("New Reason")
                    yield widgets.Select(
                        [],
                        prompt="Select Reason",
                        id="new-reason-select",
                        disabled=True,
                    )
                    yield widgets.Label("New Stage Date")
                    yield selector_widgets.StageDateSelector(id="new-stage-date")
                    yield widgets.Static(id="new-stage-warning")
            with containers.Horizontal(id="batch-stages-actions"):
                yield widgets.Button("Cancel", id="cancel-batch-stages")
                yield widgets.Button(
                    "Add New Stages", variant="primary", id="add-new-stages"
                )

    def on_mount(self) -> None:
        """Load students into the table."""
        self._reload_table()

    def _reload_table(self) -> None:
        """Refresh the student table using the current selector values."""
        status_selector = self.query_one(
            "#batch-status-selector", selector_widgets.StatusSelector
        )
        grad_year_selector = self.query_one(
            "#batch-grad-year-selector", selector_widgets.GradYearSelector
        )
        self.query_one(StudentTable).update_table(
            stages=list(status_selector.selected),
            grad_year=grad_year_selector.value,
        )

    @textual.on(widgets.SelectionList.SelectedChanged, "#batch-status-selector")
    def on_status_selector_changed(self) -> None:
        """Reload the student table when the selected stages change."""
        self._reload_table()

    @textual.on(widgets.Input.Changed, "#batch-grad-year-selector")
    def on_grad_year_selector_changed(self) -> None:
        """Reload the student table when the grad year filter changes."""
        self._reload_table()

    @textual.on(widgets.Select.Changed, "#new-status-select")
    def on_new_status_changed(self, event: widgets.Select.Changed) -> None:
        """Update New Reason options when the New Status selection changes."""
        reason_select = self.query_one("#new-reason-select", widgets.Select)
        if not isinstance(event.value, model.Stage):
            reason_select.set_options([])
            reason_select.disabled = True
        else:
            valid = model.Stage.valid_reasons[event.value]
            if valid:
                prior_reason = reason_select.value
                reason_select.set_options([(r.value.title(), r) for r in valid])
                reason_select.disabled = False
                if prior_reason in valid:
                    reason_select.value = prior_reason
            else:
                reason_select.set_options([])
                reason_select.disabled = True

    def on_button_pressed(self, event: widgets.Button.Pressed) -> None:
        """Handle button presses in the dialog."""
        if event.button.id == "cancel-batch-stages":
            self.dismiss(None)
        elif event.button.id == "select-all-students":
            self.query_one(StudentTable).select_all()
        elif event.button.id == "clear-selection-students":
            self.query_one(StudentTable).clear_selection()
        elif event.button.id == "add-new-stages":
            self._add_new_stages()

    def _add_new_stages(self) -> None:
        """Add the selected stage/date to every selected student."""
        warning = self.query_one("#new-stage-warning", widgets.Static)
        stage_select = self.query_one("#new-status-select", widgets.Select)
        reason_select = self.query_one("#new-reason-select", widgets.Select)
        date_input = self.query_one(
            "#new-stage-date", selector_widgets.StageDateSelector
        )

        stage = stage_select.value
        if (
            not isinstance(stage, model.Stage)
            or not date_input.value
            or not date_input.is_valid
        ):
            warning.update(
                "[red]Please select a New Status and a valid New Stage Date.[/red]"
            )
            return
        warning.update("")

        reason = (
            reason_select.value
            if isinstance(reason_select.value, model.Reason)
            else None
        )
        start_date = datetime.date.fromisoformat(date_input.value)
        table = self.query_one(StudentTable)
        errors: list[tuple[str, str]] = []
        for student_id in table.selected:
            status = model.Status(
                status_id=0,
                student_id=student_id,
                stage=stage,
                start_date=start_date,
                reason=reason,
            )
            try:
                status.add_safe(self._dbase)
            except model.StatusError as err:
                errors.append((student_id, str(err)))

        if errors:
            message = "\n".join(f"{sid}: {msg}" for sid, msg in errors)
            heading = "[red]Errors Adding Stages[/red]"
        else:
            message = "All new stages were added successfully."
            heading = "Success"
        self._reload_table()
        self.app.push_screen(
            confirm_dialogs.InfoDialog(heading, message),
            self._on_info_dialog_closed,
        )

    def _on_info_dialog_closed(self, _: None) -> None:
        """Close the batch dialog once the user acknowledges the result."""
        self.dismiss(None)
