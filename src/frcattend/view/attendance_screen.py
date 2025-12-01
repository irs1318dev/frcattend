"""Show attendance results."""

from textual import app, binding, screen, widgets

from frcattend import config, model


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
        yield widgets.DataTable(id="attendance-table", zebra_stripes=True)
        yield widgets.Footer()

    def on_mount(self) -> None:
        """Load data into the table."""
        self.load_table()

    def load_table(self) -> None:
        """Load attendance totals into the data table."""
        table = self.query_one("#attendance-table", widgets.DataTable)
        for col in [
            ("Last Name", "last_name"),
            ("First Name", "first_name"),
            ("Season Apps", "season_apps"),
            ("Build Apps", "build_apps"),
            ("Last Check-in", "last_checkin"),
        ]:
            table.add_column(col[0], key=col[1])
        cursor = model.Attendance.get_student_attendance_data(self.dbase)
        for row in cursor:
            table.add_row(row[1], row[2], row[4], row[5], row[6], key=row[0])
        cursor.connection.close()
