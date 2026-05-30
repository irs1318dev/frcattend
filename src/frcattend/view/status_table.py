"""A DataTable widget for viewing and editing student status."""

from textual import widgets

from frcattend import config, model

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
        self.log("Building status table.")
        self.log(self.student)
        if self.student is not None:
            statuses = model.Status.get_by_student_id(
                self._dbase,
                self.student.student_id
            )
            self.log(statuses)
            for status in statuses:
                self.add_row(
                    status.start_date.isoformat(),
                    status.stage,
                    status.reason,
                    status.notes
                )
