"""Show attendance results."""

import datetime
from collections.abc import Callable
from typing import Any

import rich.text
import textual
from textual import app, binding, containers, reactive, screen, widgets
from textual.widgets.data_table import ColumnKey

from frcattend import config, model, view
from frcattend.view import selector_widgets


def _sort_key_for_column(column_key: str | None) -> Callable[[Any], Any] | None:
    """Return a sort-key function for columns whose cell values need special handling.

    build_checkins is wrapped in Rich markup for display, so it must be parsed
    back to an int to sort numerically. last_checkin is an ISO date string or
    None for students with no checkins, which can't be compared to a string.
    """
    match column_key:
        case "build_checkins":
            return lambda value: int(rich.text.Text.from_markup(value).plain)
        case "last_checkin":
            return lambda value: value or ""
        case _:
            return None


class StudentsTable(widgets.DataTable):
    """Table of students and number of checkins for current season."""

    dbase: model.DBase
    """Connection to Sqlite Database."""
    students: dict[str, model.AttendanceStudent]
    """Students with checkin totals."""
    _sort_column_key: ColumnKey | None
    """Column the table is currently sorted by, if any."""
    _sort_reverse: bool
    """Whether the current column sort is descending."""

    def __init__(self, dbase: model.DBase, *args, **kwargs) -> None:
        """Set link to database."""
        super().__init__(*args, **kwargs, zebra_stripes=True)
        self.dbase = dbase
        self.students = {}
        self._sort_column_key = None
        self._sort_reverse = False

    def on_mount(self) -> None:
        """Initialize the table."""
        self.initialize_table()

    def on_data_table_header_selected(
        self, event: widgets.DataTable.HeaderSelected
    ) -> None:
        """Sort the table by the clicked column, toggling direction on repeat clicks."""
        if event.column_key == self._sort_column_key:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_column_key = event.column_key
            self._sort_reverse = False
        self.sort(
            event.column_key,
            key=_sort_key_for_column(event.column_key.value),
            reverse=self._sort_reverse,
        )

    def initialize_table(self) -> None:
        """Set up table columns."""
        self.cursor_type = "row"
        for col in [
            ("[green]Last Name[/]", "last_name"),
            ("First Name", "first_name"),
            ("Status", "status"),
            ("Grad Year", "grad_year"),
            ("[green]Build Checkins[/]", "build_checkins"),
            ("All Checkins", "season_checkins"),
            ("Last Checkin", "last_checkin"),
        ]:
            self.add_column(col[0], key=col[1])

    def update_table(
        self,
        stages: list[model.Stage] | None = None,
        grad_year: str | None = None,
        asof_date: datetime.date | None = None,
    ) -> None:
        """Populate the table with students, filtered by the given criteria."""
        self.clear(columns=False)
        students = model.Attendance.get_student_attendance_students(self.dbase)
        statuses = {
            student.student_id: student.status
            for student in model.Student.get_with_status(
                self.dbase, asof_date=asof_date
            )
        }
        if stages is not None:
            students = [
                student
                for student in students
                if (status := statuses.get(student.student_id)) is not None
                and status.stage in stages
            ]
        if grad_year and len(grad_year) == 4:
            students = [
                student for student in students if student.grad_year == int(grad_year)
            ]
        self.students = {student.student_id: student for student in students}
        for key, stu in self.students.items():
            status = statuses.get(key)
            self.add_row(
                f"[green]{stu.last_name}[/]",
                stu.first_name,
                status.stage.value if status else "",
                stu.grad_year,
                f"[green]{stu.build_checkins}[/]",
                stu.year_checkins,
                stu.last_checkin,
                key=key,
            )
        self.refresh()


class CheckinTable(widgets.DataTable):
    """Table of checkins for student selected in student table."""

    dbase: model.DBase
    """Connection to Sqlite Database."""
    checkins: dict[int, model.Checkin]
    """Checkins for selected student."""
    student_id: reactive.reactive[str | None] = reactive.reactive(None)
    """ID of selected student."""

    def __init__(self, dbase: model.DBase, *args, **kwargs) -> None:
        """Set link to database."""
        super().__init__(*args, **kwargs, zebra_stripes=True)
        self.dbase = dbase
        self.checkins = {}

    def on_mount(self) -> None:
        """Initialize the table."""
        self.initialize_table()

    def initialize_table(self) -> None:
        """Define table columns."""
        self.cursor_type = "row"
        for col in [
            ("Date", "iso_date"),
            ("Day", "day_of_week"),
            ("Type", "event_type"),
            ("Timestamp", "timestamp"),
        ]:
            self.add_column(col[0], key=col[1])

    def watch_student_id(self) -> None:
        """Add checkins for the specified student to the table."""
        textual.log(f"Updating Checkin table. ID: {self.student_id}")
        if self.student_id is None:
            return
        self.clear(columns=False)
        self.checkins = {
            checkin.checkin_id: checkin
            for checkin in model.Checkin.get_checkins_by_student(
                self.dbase, self.student_id
            )
        }
        for checkin_id, checkin in self.checkins.items():
            self.add_row(
                checkin.iso_date,
                checkin.day_of_week,
                checkin.event_type.value,
                checkin.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                key=str(checkin_id),
            )
        self.refresh()


class AttendanceScreen(screen.Screen):
    """Add, delete, and edit students."""

    dbase: model.DBase
    """Connection to Sqlite Database."""
    student_id: reactive.reactive[str | None] = reactive.reactive(None)
    """ID of selected student."""

    CSS_PATH = view.CSS_FOLDER / "attendance_screen.tcss"
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

    def compose(self) -> app.ComposeResult:
        """Add the datatable and other controls to the screen."""
        yield widgets.Header()
        with containers.Horizontal(id="attendance-top-container"):
            yield StudentsTable(dbase=self.dbase, id="attendance-students-table")
            with containers.Vertical(id="attendance-actions-container"):
                yield selector_widgets.StatusSelector(id="status-selector")
                yield selector_widgets.GradYearSelector(
                    self.dbase, id="grad-year-selector"
                )
                yield selector_widgets.GoBackSelector(value=None, id="asof-selector")
        yield widgets.Static(
            "Events that Student Attended", classes="separator emphasis"
        )
        yield (
            CheckinTable(dbase=self.dbase, id="attendance-checkins-table").data_bind(
                AttendanceScreen.student_id
            )
        )

    def on_mount(self) -> None:
        """Load the student table using the default filter selections."""
        self.load_student_data()

    def load_student_data(self) -> None:
        """Reload the student table using the current filter selections."""
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
            asof_date = None
        self.query_one("#attendance-students-table", StudentsTable).update_table(
            stages=selected_stages, grad_year=grad_year, asof_date=asof_date
        )

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

    @textual.on(StudentsTable.RowHighlighted, "#attendance-students-table")
    def on_students_table_row_highlighted(
        self, message: StudentsTable.RowHighlighted
    ) -> None:
        """Set the new student_id, which will trigger a checkin table update."""
        self.student_id = message.row_key.value
