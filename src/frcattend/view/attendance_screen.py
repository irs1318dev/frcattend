"""Show attendance results."""

import dataclasses

from textual import app, binding, screen, widgets

from frcattend import config, model


class StudentsTable(widgets.DataTable):
    """Table of students and number of checkins for current season."""

    dbase: model.DBase
    """Connection to Sqlite Database."""
    students: dict[str, model.AttendanceStudent]

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
            ("[yellow]Deactivated On[/]", "deactivated_on")
        ]:
            self.add_column(col[0], key=col[1])

    def update_table(self) -> None:
        """Populae the table with students."""
        self.clear(columns=False)
        self.students = {
            student.student_id: student
            for student in model.Attendance.get_student_attendance_students(self.dbase)
        }
        for key, stu in self.students.items():
            deactivated_on = '' if stu.deactivated_on is None else stu.deactivated_on
            self.add_row(
                f"[green]{stu.last_name}[/]",
                stu.first_name,
                stu.grad_year,
                f"[green]{stu.build_checkins}[/]",
                stu.last_checkin,
                stu.grad_year,
                f"[yellow]{deactivated_on}[/]",
                key=key,
            )
        self.refresh


class AttendanceScreen(screen.Screen):
    """Add, delete, and edit students."""

    dbase: model.DBase
    """Connection to Sqlite Database."""
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
