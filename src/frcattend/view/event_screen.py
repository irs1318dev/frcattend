"""Manage team events."""

import datetime

import dateutil.parser
import rich.text
import textual
from textual import app, binding, containers, reactive, screen, widgets

import frcattend.view
from frcattend import config, model
from frcattend.features import events
from frcattend.view import selector_widgets, validators


class EventsTable(widgets.DataTable):
    """Table of team events and number of students who attended."""

    dbase: model.DBase
    """Connection to Sqlite Database."""
    checkin_events: dict[str, events.CheckinEvent]
    """Event data that's displayed in the table."""

    def __init__(self, dbase: model.DBase, *args, **kwargs) -> None:
        """Set link to database."""
        super().__init__(*args, **kwargs, zebra_stripes=True)
        self.dbase = dbase
        self.checkin_events = {}

    def on_mount(self) -> None:
        """Initialize the table."""
        self.initialize_table()
        self.update_table()

    def initialize_table(self) -> None:
        """Load attendance totals into the data table."""
        self.cursor_type = "row"
        for col in [
            ("Date", "event_date"),
            ("Day of Week", "day_of_week"),
            ("Type", "event_type"),
            ("Count", "checkin_count"),
            ("Description", "description"),
        ]:
            self.add_column(col[0], key=col[1])

    def update_table(self) -> None:
        """Populate the table with data."""
        self.clear(columns=False)
        self.checkin_events = {
            event.key: event
            for event in events.CheckinEvent.get_checkin_events(self.dbase)
        }
        for key, event in self.checkin_events.items():
            self.add_row(
                event.iso_date,
                rich.text.Text(event.weekday_name, justify="center"),
                event.event_type,
                event.checkin_count,
                event.description,
                key=key,
            )
        self.refresh()


class StudentsTable(widgets.DataTable):
    """Table of students who checked in at the selected event."""

    dbase: model.DBase
    """Connection to Sqlite Database."""
    students: dict[str, events.EventStudent]
    """Students who checked in at that selected event."""
    event_key = reactive.reactive("")
    """Contains the currently selected event."""
    selected_stages: reactive.reactive[tuple[model.Stage, ...]] = reactive.reactive(())
    """Only students with one of these stages are shown."""
    grad_year: reactive.reactive[str] = reactive.reactive("")
    """Only students with this graduation year are shown, if four digits."""
    show_current_status: reactive.reactive[bool] = reactive.reactive(False)
    """If True, the Status column shows each student's current status instead
    of their status as of the selected event's date."""

    CSS_PATH = frcattend.view.CSS_FOLDER / "event_screen.tcss"

    def __init__(self, dbase: model.DBase, *args, **kwargs) -> None:
        """Set link to database."""
        super().__init__(*args, **kwargs, zebra_stripes=True)
        self.dbase = dbase
        self.students = {}

    def on_mount(self) -> None:
        """Initialize the table."""
        self.initialize_table()

    def initialize_table(self) -> None:
        """Define table columns."""
        for col in [
            ("First Name", "first_name"),
            ("Last Name", "last_name"),
            ("Grad Year", "grad_year"),
            ("Status", "status"),
            ("Check-in time", "timestamp"),
        ]:
            self.add_column(col[0], key=col[1])

    def watch_event_key(self) -> None:
        """Reload the table when the selected event changes."""
        self.update_table()

    def watch_selected_stages(self) -> None:
        """Reload the table when the stage filter changes."""
        self.update_table()

    def watch_grad_year(self) -> None:
        """Reload the table when the graduation year filter changes."""
        self.update_table()

    def watch_show_current_status(self) -> None:
        """Reload the table when the current-status toggle changes."""
        self.update_table()

    def update_table(self) -> None:
        """Populate the table with students checked in to the selected event.

        Only students whose displayed Status matches one of the selected
        stages, and whose graduation year matches the graduation year
        filter, are shown.
        """
        if not self.event_key:
            return
        self.clear(columns=False)
        self.students = {
            student.student_id: student
            for student in events.EventStudent.get_students_for_event(
                self.dbase, self.event_key
            )
        }
        if self.show_current_status:
            status_asof_date = None
        else:
            status_asof_date = datetime.date.fromisoformat(
                self.event_key.split("::")[0]
            )
        statuses = {
            student.student_id: student.status
            for student in model.Student.get_with_status(
                self.dbase, asof_date=status_asof_date
            )
        }
        self.students = {
            student_id: student
            for student_id, student in self.students.items()
            if (status := statuses.get(student_id)) is not None
            and status.stage in self.selected_stages
        }
        if len(self.grad_year) == 4:
            self.students = {
                student_id: student
                for student_id, student in self.students.items()
                if student.grad_year == int(self.grad_year)
            }
        for key, student in self.students.items():
            status = statuses.get(key)
            self.add_row(
                student.first_name,
                student.last_name,
                student.grad_year,
                status.stage.value if status else "",
                student.timestamp.replace(microsecond=0),
                key=key,
            )


class EventScreen(screen.Screen):
    """Add, delete, and edit students."""

    dbase: model.DBase
    """Connection to Sqlite Database."""
    event_key: reactive.reactive[str | None] = reactive.reactive(None)
    """Contains the currently selected event."""
    selected_stages: reactive.reactive[tuple[model.Stage, ...]] = reactive.reactive(())
    """Only students with one of these stages are shown."""
    grad_year: reactive.reactive[str] = reactive.reactive("")
    """Only students with this graduation year are shown, if four digits."""
    show_current_status: reactive.reactive[bool] = reactive.reactive(False)
    """If True, the Status column shows each student's current status instead
    of their status as of the selected event's date."""

    CSS_PATH = frcattend.view.CSS_FOLDER / "event_screen.tcss"
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
        with containers.Horizontal(classes="menu"):
            yield widgets.Button("Add Event")
            yield widgets.Button("Edit Event", id="events-edit")
        yield widgets.Static(
            "Events",
            classes="separator emphasis",
        )
        events_table = EventsTable(dbase=self.dbase, id="events-table")
        yield events_table
        yield widgets.Static(
            "Students at Selected Event",
            classes="separator emphasis",
        )
        with containers.Horizontal(id="events-students-container"):
            with containers.Vertical(id="events-student-list-container"):
                students_table = StudentsTable(
                    dbase=self.dbase, id="events-students-table"
                )
                students_table.data_bind(
                    EventScreen.event_key,
                    EventScreen.selected_stages,
                    EventScreen.grad_year,
                    EventScreen.show_current_status,
                )
                yield students_table
            with containers.Vertical(id="events-students-actions-container"):
                yield selector_widgets.StatusSelector(id="status-selector")
                yield selector_widgets.GradYearSelector(
                    self.dbase, id="grad-year-selector"
                )
                yield widgets.Checkbox(
                    "Show Current Status",
                    False,
                    id="show-current-status-checkbox",
                    tooltip=(
                        "Check this box to show each student's current status "
                        "instead of their status as of the selected event's date."
                    ),
                )
        yield widgets.Footer()

    def on_mount(self) -> None:
        """Initialize the stage filter to match the status selector's default."""
        status_selector = self.query_one(
            "#status-selector", selector_widgets.StatusSelector
        )
        self.selected_stages = tuple(status_selector.selected)

    @textual.on(widgets.SelectionList.SelectedChanged, "#status-selector")
    def on_status_selector_changed(self) -> None:
        """Update the stage filter when the selected stages change."""
        status_selector = self.query_one(
            "#status-selector", selector_widgets.StatusSelector
        )
        self.selected_stages = tuple(status_selector.selected)

    @textual.on(widgets.Input.Changed, "#grad-year-selector")
    def on_grad_year_selector_changed(self, message: widgets.Input.Changed) -> None:
        """Update the graduation year filter when its value changes."""
        self.grad_year = message.value

    @textual.on(widgets.Checkbox.Changed, "#show-current-status-checkbox")
    def on_show_current_status_changed(self, message: widgets.Checkbox.Changed) -> None:
        """Toggle between current status and status as of the event date."""
        self.show_current_status = message.checkbox.value

    @textual.on(EventsTable.RowHighlighted)
    def on_events_table_row_highlighted(
        self, message: widgets.DataTable.RowSelected
    ) -> None:
        """Set the new event key, which will trigger a student table update."""
        self.event_key = message.row_key.value

    @textual.on(EventsTable.RowSelected)
    def on_events_table_row_selected(
        self, message: widgets.DataTable.RowSelected
    ) -> None:
        """Set the new event key, which will trigger a student table update."""
        self.event_key = message.row_key.value

    @textual.work
    @textual.on(widgets.Button.Pressed, "#events-edit")
    async def edit_event(self) -> None:
        """Edit the selected event."""
        events_table = self.query_one("#events-table", EventsTable)
        if self.event_key is None:
            return
        edit_dialog = EditEventDialog(
            dbase=self.dbase, event=events_table.checkin_events[self.event_key]
        )
        if await self.app.push_screen_wait(edit_dialog):
            events_table.update_table()


class EditEventDialog(screen.ModalScreen[bool]):
    """Edit or add events."""

    dbase: model.DBase
    """Database interface."""
    event: events.CheckinEvent
    """The event to be edited."""

    CSS_PATH = frcattend.view.CSS_FOLDER / "event_screen.tcss"

    def __init__(self, dbase: model.DBase, event: events.CheckinEvent) -> None:
        """Set the event to be edited."""
        super().__init__()
        self.dbase = dbase
        self.event = event

    def compose(self) -> app.ComposeResult:
        """Build the dialog."""
        event = self.event
        with containers.Vertical(id="edit-event-dialog", classes="modal-dialog"):
            yield widgets.Label("Selected Event:", classes="bold-label")
            yield widgets.Static(f"\t{event.event_type.value}")
            yield widgets.Static(
                f"\t{event.weekday_name}, {event.event_date.isoformat()}"
            )
            yield widgets.Label("Event Date:")
            yield widgets.Input(
                value=event.iso_date,
                disabled=(self.event.checkin_count > 0),
                id="event-date-input",
                validators=[validators.DateValidator()],
            )
            yield widgets.Label("Event Type:")
            yield widgets.Select(
                [(etype.value.title(), etype.value) for etype in model.EventType],
                value=event.event_type,
                id="event-type-select",
            )
            yield widgets.Label("Description:")
            yield widgets.Input(value=event.description, id="event-description-input")
            with containers.Horizontal(classes="dialog-row"):
                yield widgets.Button("Ok", id="events-edit-ok")
                yield widgets.Button("Cancel", id="events-edit-cancel")

    @textual.on(widgets.Button.Pressed, "#events-edit-cancel")
    def cancel_dialog(self) -> None:
        """Close the dialog and take no action."""
        self.dismiss(False)

    @textual.on(widgets.Button.Pressed, "#events-edit-ok")
    def apply_dialog(self) -> None:
        """Close the dialog and update the event."""
        new_date = dateutil.parser.parse(
            self.query_one("#event-date-input", widgets.Input).value, dayfirst=False
        ).date()
        new_type = model.EventType(
            self.query_one("#event-type-select", widgets.Select).value
        )
        new_description: str | None = self.query_one(
            "#event-description-input", widgets.Input
        ).value
        # Update method calls do nothing if value hasn't changed.
        self.event.update_description(self.dbase, new_description)
        self.event.update_event_date(self.dbase, new_date)
        # update_event_type adds a new event and deletes the old one, then
        #   updates the linked checkin data. This avoids referential integrity
        #   issues.
        self.event.update_event_type(self.dbase, new_type)
        self.dismiss(True)
