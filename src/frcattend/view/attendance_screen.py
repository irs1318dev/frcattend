"""Show attendance results."""

import textual
from textual import app, binding, reactive, screen, widgets

from frcattend import config, model, view


class StudentsTable(widgets.DataTable):
    """Table of students and number of checkins for current season."""

    dbase: model.DBase
    """Connection to Sqlite Database."""
    students: dict[str, model.AttendanceStudent]
    """Students with checkin totals."""

    def __init__(self, dbase: model.DBase, *args, **kwargs) -> None:
        """Set link to database."""
        super().__init__(zebra_stripes=True, *args, **kwargs)
        self.dbase = dbase
        self.students = {}

    def on_mount(self) -> None:
        """Initialize the table."""
        self.initialize_table()
        self.update_table()

    def initialize_table(self) -> None:
        """Set up table columns."""
        self.cursor_type = "row"
        for col in [
            ("[green]Last Name[/]", "last_name"),
            ("First Name", "first_name"),
            ("Graduation Year", "grad_year"),
            ("[green]Build Season Checkins[/]", "build_checkins"),
            ("All Checkins", "season_checkins"),
            ("Last Checkin", "last_checkin"),
            ("[yellow]Deactivated On[/]", "deactivated_on"),
        ]:
            self.add_column(col[0], key=col[1])

    def update_table(self) -> None:
        """Populae the table with students."""
        self.clear(columns=False)
        self.students = {
            student.student_id: student
            for student in model.Attendance.get_student_attendance_students(
                self.dbase, include_inactive=True
            )
        }
        for key, stu in self.students.items():
            deactivated_on = "" if stu.deactivated_on is None else stu.deactivated_iso
            self.add_row(
                f"[green]{stu.last_name}[/]",
                stu.first_name,
                stu.grad_year,
                f"[green]{stu.build_checkins}[/]",
                stu.year_checkins,
                stu.last_checkin,
                f"[yellow]{deactivated_on}[/]",
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
        super().__init__(zebra_stripes=True, *args, **kwargs)
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
                checkin.timestamp,
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
        yield StudentsTable(dbase=self.dbase, id="attendance-students-table")
        yield widgets.Static(
            "Events that Student Attended", classes="separator emphasis"
        )
        yield (
            CheckinTable(dbase=self.dbase, id="attendance-checkins-table").data_bind(
                AttendanceScreen.student_id
            )
        )

    @textual.on(StudentsTable.RowHighlighted)
    def on_students_table_row_highlighted(
        self, message: StudentsTable.RowHighlighted
    ) -> None:
        """Set the new student_id, which will trigger a checkin table update."""
        if "-" not in str(message.row_key.value):
            return
        self.student_id = message.row_key.value
        textual.log(f"Row highlighted. ID: {message.row_key.value}")

    # @textual.on(StudentsTable.RowSelected)
    # def on_students_table_row_selected(
    #     self, message: widgets.DataTable.RowSelected
    # ) -> None:
    #     """Set the new student_id, which will trigger a checkin table update."""
    #     self.student_id = message.row_key.value
    #     textual.log(f"Row selected. ID: {self.student_id}")
