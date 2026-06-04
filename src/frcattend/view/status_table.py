"""A DataTable widget for viewing and editing student status."""

import datetime
import textual
from textual import app, containers, screen, widgets

from frcattend import config, model, view
from frcattend.view import validators


class StatusError(Exception):
    """Error occuring when setting student status."""


class StatusTable(widgets.DataTable):
    """Display status records for a single student."""
    student: model.Student | None
    """Spcecify student whose data will be displayed."""
    _dbase: model.DBase
    """Connection to Sqlite database."""


    def __init__(self, student: model.Student | None, widget_id: str) -> None:
        """Set the student ID on initialization."""
        super().__init__(id=widget_id, zebra_stripes=True)
        self.student = student
        if config.settings.db_path is None:
            raise model.DBaseError("No database file selected.")
        self._dbase = model.DBase(config.settings.db_path)

    def on_mount(self) -> None:
        """Configure and load table."""
        self.cursor_type="row"
        self.add_columns("start_date", "stage", "reason", "notes")
        self.populate_rows()

    def populate_rows(self) -> None:
        """Clear and reload all status rows from the database."""
        self.clear()
        if self.student is not None:
            statuses = model.Status.get_by_student_id(
                self._dbase,
                self.student.student_id
            )
            for status in statuses:
                self.add_row(
                    status.start_date.isoformat(),
                    status.stage,
                    status.reason,
                    status.notes,
                    key=str(status.status_id)
                )

    @textual.on(widgets.DataTable.RowSelected)
    async def edit_status(self, event: widgets.DataTable.RowSelected) -> None:
        """Edit the status when a row is selected."""
        if self.student is None:
            raise StatusError("No student selected when changing status.")
        match event.row_key.value:
            case None:
                raise StatusError("Row key can't be None!")
            case "new":
                self.app.notify("Adding a new status!!!")
                status_id = None
            case str():
                status_id = int(event.row_key.value)
        saved = await self.app.push_screen(
            EditStatusDialog(
                dbase=self._dbase, student=self.student, status_id=status_id)
        )
        if saved:
            self.populate_rows()


class EditStatusDialog(screen.ModalScreen):
    """For editing student status records."""

    CSS_PATH = view.CSS_FOLDER / "student_dialog.tcss"

    student: model.Student
    status: model.Status | None
    _dbase: model.DBase


    def __init__(
        self,
        dbase: model.DBase,
        student: model.Student,
        status_id: int | None
    ) -> None:
        """Initialize for a specific student and status record."""
        super().__init__()
        self._dbase = dbase
        self.student = student
        if status_id is None:
            self.status = None
        else:
            self.status = model.Status.get_by_status_id(self._dbase, status_id)


    def compose(self) -> app.ComposeResult:
        """Create and arrange dialog widgets."""
        title = "Add Change in Status" if self.status is None else "Edit Status"
        with containers.Vertical(id="student-status", classes="modal-dialog"):
            yield widgets.Label(title, classes="emphasis")
            yield widgets.Input(
                value=self.status.start_date.isoformat() if self.status else "",
                placeholder="YYYY-MM-DD",
                validators=[validators.DateValidator()],
                id="status-start-date",
            )
            if self.status is None:
                initial_stage = widgets.Select.NULL
                initial_reason = widgets.Select.NULL
            else:
                initial_stage = self.status.stage
                initial_reason = (
                    widgets.Select.NULL if self.status.reason is None
                    else self.status.reason
                )

            if not isinstance(initial_stage, model.Stage):
                valid_reasons: list[model.Reason] = []
                reason_disabled = True
                initial_reason = widgets.Select.NULL
            else:
                valid_reasons = model.Stage.valid_reasons[initial_stage]
                reason_disabled = len(valid_reasons) == 0
                if reason_disabled or initial_reason not in valid_reasons:
                    initial_reason = widgets.Select.NULL

            yield widgets.Select(
                [(stage.value.title(), stage) for stage in model.Stage],
                value=initial_stage,
                prompt="Select Stage",
                id="stage-select",
            )
            yield widgets.Select(
                [(r.value.title(), r) for r in valid_reasons],
                value=initial_reason,
                prompt="Select Reason",
                id="status-reason",
                disabled=reason_disabled,
            )
            with containers.Horizontal(id="status-actions"):
                yield widgets.Button("Cancel", id="cancel-status")
                yield widgets.Button("OK", id="ok-status", variant="primary")

    @textual.on(widgets.Select.Changed, "#stage-select")
    def stage_changed(self, event: widgets.Select.Changed) -> None:
        """Update Reason options when Stage selection changes."""
        reason_select = self.query_one("#status-reason", widgets.Select)
        if not isinstance(event.value, model.Stage):
            reason_select.set_options([])
            reason_select.disabled = True
        else:
            valid = model.Stage.valid_reasons[event.value]
            if valid:
                reason_select.set_options([(r.value.title(), r) for r in valid])
                reason_select.disabled = False
            else:
                reason_select.set_options([])
                reason_select.disabled = True

    def on_button_pressed(self, event: widgets.Button.Pressed) -> None:
        """Respond to dialog OK or Cancel buttons."""
        if event.button.id == "cancel-status":
            self.dismiss(False)
        elif event.button.id == "ok-status":
            self._save_status()

    def _save_status(self) -> None:
        """Validate form and save status to the database."""
        date_input = self.query_one("#status-start-date", widgets.Input)
        stage_select = self.query_one("#stage-select", widgets.Select)
        reason_select = self.query_one("#status-reason", widgets.Select)

        if not date_input.is_valid or not date_input.value:
            self.app.notify("Please enter a valid date (YYYY-MM-DD).", severity="error")
            return
        if not isinstance(stage_select.value, model.Stage):
            self.app.notify("Please select a stage.", severity="error")
            return

        start_date = datetime.date.fromisoformat(date_input.value)
        stage = stage_select.value
        reason = reason_select.value if isinstance(reason_select.value, model.Reason) else None

        if self.status is None:
            new_status = model.Status(
                status_id=0,
                student_id=self.student.student_id,
                stage=stage,
                start_date=start_date,
                reason=reason,
                notes=None,
            )
            new_status.add(self._dbase)
        else:
            self.status.stage = stage
            self.status.start_date = start_date
            self.status.reason = reason
            self.status.update(self._dbase)

        self.dismiss(True)


