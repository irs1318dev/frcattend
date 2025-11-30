"""Turn on camera and scan QR Codes."""

import asyncio
import datetime
import time
from typing import cast, Optional

import cv2

import textual
from textual import app, containers, message, screen, widgets
from textual.widgets import option_list

from frcattend import config, model
import frcattend.view
from frcattend.view import pw_dialog


class ScanScreen(screen.Screen):
    """UI for scanning QR codes while taking attendance."""

    CSS_PATH = [frcattend.view.CSS_FOLDER / "take_attendance.tcss"]

    dbase: model.DBase
    """Sqlte database connection object."""
    _students: dict[str, model.Student]
    """Mapping of student IDs to student records."""
    log_widget: widgets.RichLog
    """Displays checking results."""
    event_type: model.EventType
    """Type of event at which we're taking attendance."""
    _checkedin_students: set[str]
    """Recently scanned student IDs."""
    _scanned_students: set[str]
    """Students who have scanned their QR code within the last few seconds."""

    BINDINGS = [
        (
            "q",
            "exit_scan_mode",
            "Quit QR Code Scan Mode.",
        ),
    ]

    def __init__(self) -> None:
        """Initialize databae connection."""
        #
        super().__init__()
        if config.settings.db_path is None:
            raise model.DBaseError("No database file selected.")
        self.dbase = model.DBase(config.settings.db_path)
        self._students = {
            student.student_id: student
            for student in model.Student.get_all(self.dbase)
        }

    class QrCodeFound(message.Message):
        def __init__(self, code: str) -> None:
            self.code = code
            super().__init__()

    def compose(self) -> app.ComposeResult:
        yield widgets.Header()
        with containers.Vertical(id="log-container"):
            yield widgets.Static("Logs", classes="log-title")
            yield widgets.RichLog(id="attendance-log", highlight=True, markup=True)
        yield widgets.Footer()

    def on_mount(self) -> None:
        """Request type of event then start the scanner."""
        self.log_widget = self.query_one("#attendance-log", widgets.RichLog)
        self.app.push_screen(
            EventTypeDialog(), callback=self.set_event_type_and_start_scanning
        )

    def set_event_type_and_start_scanning(
        self, event_type: Optional[model.EventType]
    ) -> None:
        """Set the event type"""
        if event_type is None:
            self.app.pop_screen()
            return
        self.event_type = event_type
        self.dbase.add_event(event_type)
        # Prevent codes from being scanned more than once for same event.
        self._checkedin_students = set(
            model.Checkin.get_checkedin_students(
                self.dbase, datetime.date.today(), event_type
            )
        )
        self.scan_qr_codes()

    @textual.work(exclusive=False)
    async def scan_qr_codes(self) -> None:
        """Open video window and capture QR codes."""
        vcap = cv2.VideoCapture(config.settings.camera_number)
        detector = cv2.QRCodeDetector()
        qr_data: str | None = None
        self._scanned_students = set()
        while True:
            try:
                _, img = vcap.read()
                window_title = "Scan QR Codes (Click on window and press q to exit)"
                # Mirror view for display
                disp_img = cv2.flip(img, 1)
                cv2.imshow(window_title, disp_img)

                qr_data, bbox, straight_code = detector.detectAndDecode(img)
            except cv2.error:
                continue
            if qr_data:
                if qr_data not in self._scanned_students:
                    self._scanned_students.add(qr_data)
                    self.post_message(self.QrCodeFound(qr_data))
                    await asyncio.sleep(0.1)  # Allow log to update.
            wait_key = cv2.waitKey(50)  # Wait 50 miliseconds for key press.
            if wait_key in [ord("q"), ord("Q")]:
                break
        vcap.release()
        cv2.destroyAllWindows()
        await self.run_action("exit_scan_mode")

    async def on_scan_screen_qr_code_found(self, message: QrCodeFound) -> None:
        """Add an attendance record to the database."""
        student_id = message.code
        student = self._students.get(student_id)
        if student is None:
            self.log_widget.write(
                "[yellow]Unknown ID scanned,\nplease talk to a mentor.[/]"
            )
            return
        student_name = f"{student.first_name} {student.last_name}"
        if student_id in self._checkedin_students:
            self.log_widget.write(f"[orange3]Already attended: {student_name}[/]")
        else:
            self._checkedin_students.add(student_id)
            timestamp = datetime.datetime.now()
            checkin = model.Checkin(
                checkin_id=-1,
                student_id=student_id,
                event_type=self.event_type,
                timestamp=timestamp,
            )
            checkin_id = checkin.add(self.dbase)
            if checkin_id is None:
                self.log_widget.write(
                    "[ansi_bright_red]Valid QR code, but error recording checkin.\n"
                    "Please speak to a mentor.[/]"
                )
            else:
                self.log_widget.write(
                    f"[green]Success: {student_name} "
                    f"checked in at {timestamp.strftime('%H:%M:%S')}[/]"
                )
        self.discard_scanned_code(student_id)

    # Tried using Textual's set_timer method, but that didn't work.
    #   Non-threaded async workers didn't work either. Might be due to
    #   OpenCV and while loop blocking calls?
    @textual.work(exclusive=False, thread=True)
    def discard_scanned_code(self, student_id: str) -> None:
        """Allow a QR code to be scanned after five seconds have elapsed.."""
        time.sleep(5)
        self._scanned_students.discard(student_id)

    def action_exit_scan_mode(self) -> None:
        """Require a password to exit QR code scan mode."""

        def _exit_on_success(success: bool | None) -> None:
            if success:
                self.app.pop_screen()
            else:
                self.scan_qr_codes()

        pw_dialog.PasswordPrompt.show(
            submit_callback=_exit_on_success, exit_on_cancel=False
        )


class EventTypeDialog(screen.ModalScreen[Optional[model.EventType]]):
    """Select the event type when opening scan attendance screen."""

    def __init__(self) -> None:
        super().__init__()
        self.title = "Select Event Type"

    def compose(self) -> app.ComposeResult:
        """Arrange widgets within the dialog."""
        with containers.Vertical(id="event-type-dialog", classes="modal-dialog"):
            yield widgets.Label("Event Type")
            event_options = widgets.OptionList(
                *[option_list.Option(t.value.title(), id=t) for t in model.EventType],
                id="event-type-option",
            )
            yield event_options
            with containers.Horizontal(classes="dialog-row"):
                yield widgets.Button("Ok", id="event-type-select-ok-button")
                yield widgets.Button("Cancel", id="event-type-select-cancel-button")
        type_map = {opt.id: idx for idx, opt in enumerate(event_options.options)}
        event_options.highlighted = type_map[model.EventType.MEETING]

    @textual.on(widgets.Button.Pressed, "#event-type-select-ok-button")
    def on_ok_button_pressed(self) -> None:
        """Close the dialog and display the QR code scanning screen."""
        event_type_list = self.query_one("#event-type-option", widgets.OptionList)
        selected_index = event_type_list.highlighted
        if selected_index is not None:
            selected_event = cast(
                model.EventType, event_type_list.options[selected_index].id
            )
            self.dismiss(selected_event)
        else:
            self.dismiss(None)

    @textual.on(widgets.Button.Pressed, "#event-type-select-cancel-button")
    def on_cancel_button_pressed(self) -> None:
        """Close the dialog and return to the main screen."""
        self.dismiss(None)
