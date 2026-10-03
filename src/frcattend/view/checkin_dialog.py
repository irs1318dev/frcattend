"""Manually add a checkin for a single student."""

import datetime
import sqlite3

import textual
from textual import app, containers, screen, widgets

import frcattend.view
from frcattend import model
from frcattend.view import validators

RECENT_EVENT_DAYS = 30
"""Checkins can only be added for events that occurred within this many days."""


class AddCheckinDialog(screen.ModalScreen[bool]):
    """Add a checkin for a student to a recent event.

    Dismisses with True if a checkin was added, False otherwise.
    """

    CSS_PATH = frcattend.view.CSS_FOLDER / "checkin_dialog.tcss"

    _dbase: model.DBase
    """Connection to Sqlite Database."""
    student: model.Student
    """Student who will receive the checkin."""
    status: str
    """Student's current status, as displayed in the students table."""
    events: dict[str, model.Event]
    """Events from the last RECENT_EVENT_DAYS days, keyed by Event.key."""

    def __init__(self, dbase: model.DBase, student: model.Student, status: str) -> None:
        """Set the database connection and the student to check in."""
        super().__init__()
        self._dbase = dbase
        self.student = student
        self.status = status
        today = datetime.date.today()
        earliest = today - datetime.timedelta(days=RECENT_EVENT_DAYS)
        recent_events = [
            event
            for event in model.Event.get_all(dbase)
            if earliest <= event.event_date <= today
        ]
        recent_events.sort(key=lambda event: event.event_date, reverse=True)
        self.events = {event.key: event for event in recent_events}

    def compose(self) -> app.ComposeResult:
        """Layout the dialog box."""
        with containers.Vertical(id="add-checkin-dialog", classes="modal-dialog"):
            yield widgets.Label("[bold]Add Checkin[/bold]")
            yield widgets.Static()
            yield widgets.Label(f"First Name: {self.student.first_name}")
            yield widgets.Label(f"Last Name:  {self.student.last_name}")
            yield widgets.Label(f"Status:     {self.status}")
            yield widgets.Label(f"Student ID: {self.student.student_id}")
            yield widgets.Static()
            yield widgets.Label("Event")
            yield widgets.Select(
                [
                    (f"{event.iso_date}  {event.event_type.value.title()}", key)
                    for key, event in self.events.items()
                ],
                prompt=(
                    "Select Event"
                    if self.events
                    else f"No events in last {RECENT_EVENT_DAYS} days"
                ),
                disabled=not self.events,
                id="checkin-event",
            )
            yield widgets.Label("Checkin Time")
            yield widgets.Input(
                placeholder="HH:MM",
                restrict=r"[\d:]{0,5}",
                max_length=5,
                validators=[validators.TimeValidator()],
                id="checkin-time",
            )
            yield widgets.Static(id="checkin-warning")
            with containers.Horizontal(id="add-checkin-actions"):
                yield widgets.Button("OK", variant="primary", id="ok-add-checkin")
                yield widgets.Button("Cancel", id="cancel-add-checkin")

    @textual.on(widgets.Input.Changed, "#checkin-time")
    def on_time_changed(self, event: widgets.Input.Changed) -> None:
        """Show the validation error, if any, as the user types."""
        warning = self.query_one("#checkin-warning", widgets.Static)
        if event.validation_result is None or event.validation_result.is_valid:
            warning.update("")
        else:
            warning.update(
                f"[red]{event.validation_result.failure_descriptions[0]}[/red]"
            )

    def on_button_pressed(self, event: widgets.Button.Pressed) -> None:
        """Add the checkin on OK, close the dialog on Cancel."""
        if event.button.id == "ok-add-checkin":
            self._add_checkin()
        elif event.button.id == "cancel-add-checkin":
            self.dismiss(False)

    def _add_checkin(self) -> None:
        """Validate the inputs and write the checkin to the database."""
        warning = self.query_one("#checkin-warning", widgets.Static)
        event_key = self.query_one("#checkin-event", widgets.Select).value
        if not isinstance(event_key, str) or event_key not in self.events:
            warning.update("[red]Please select an event.[/red]")
            return
        event = self.events[event_key]
        time_input = self.query_one("#checkin-time", widgets.Input)
        validation_result = time_input.validate(time_input.value)
        if validation_result is not None and not validation_result.is_valid:
            warning.update(f"[red]{validation_result.failure_descriptions[0]}[/red]")
            return
        checkin_time = datetime.datetime.strptime(
            time_input.value, validators.TimeValidator.FORMAT
        ).time()
        timestamp = datetime.datetime.combine(event.event_date, checkin_time)
        if timestamp > datetime.datetime.now():
            warning.update("[red]Checkin time cannot be in the future.[/red]")
            return

        existing = model.Checkin.get_checkin_by_student_and_date(
            self._dbase, self.student.student_id, event.event_date
        )
        if any(checkin.event_type == event.event_type for checkin in existing):
            warning.update(
                f"[red]Student already has a {event.event_type.value} checkin "
                f"on {event.iso_date}.[/red]"
            )
            return

        checkin = model.Checkin(
            checkin_id=0,
            student_id=self.student.student_id,
            event_type=event.event_type,
            timestamp=timestamp,
        )
        try:
            checkin.add(self._dbase)
        except sqlite3.IntegrityError as err:
            warning.update(f"[red]Unable to add checkin: {err}[/red]")
            return
        self.dismiss(True)
