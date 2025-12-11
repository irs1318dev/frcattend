"""Turn on camera and scan QR Codes."""

import asyncio
import dataclasses
import datetime
import time
from typing import cast, Optional

import cv2

import textual
from textual import app, containers, message, screen, widgets
from textual.widgets import option_list

from frcattend import config, model
import frcattend.view
from frcattend.view import pw_dialog, survey_screen


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
    survey: Optional[model.Survey]
    """Students can be asked to complete a survey when they checkin."""
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
            for student in model.Student.get_all(self.dbase, include_inactive=True)
        }

    class QrCodeFound(message.Message):
        def __init__(self, code: str) -> None:
            self.code = code
            super().__init__()

    def compose(self) -> app.ComposeResult:
        yield widgets.Header()
        with containers.Vertical(id="log-container"):
            yield widgets.Static("Logs", classes="log-title")
            yield widgets.RichLog(id="attendance-log", highlight=False, markup=True)
        yield widgets.Footer()

    def on_mount(self) -> None:
        """Request type of event then start the scanner."""
        self.log_widget = self.query_one("#attendance-log", widgets.RichLog)
        self.app.push_screen(
            ChooseTypeAndSurveyDialog(self.dbase),
            callback=self.set_event_type_and_start_scanning
        )

    def set_event_type_and_start_scanning(
        self, result: Optional["DialogResult"]
    ) -> None:
        """Set the event type"""
        if result is None or result.event_type is None:
            self.app.pop_screen()
            return
        self.event_type = result.event_type
        self.survey = result.survey
        today = datetime.date.today()
        event = model.Event(today, result.event_type)
        event.add(self.dbase)
        # Prevent codes from being scanned more than once for same event.
        self._checkedin_students = set(
            model.Checkin.get_checkedin_students(self.dbase, today, result.event_type)
        )
        # Force a small delay to ensure dialog is fully dismissed before camera opens
        self.set_timer(0.1, self.scan_qr_codes)  # Timer allows dialog to be dismissed.

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
                    if self.survey is not None and qr_data in self._students:
                        if self._students[qr_data].deactivated_on is None:
                            self.app.push_screen(
                                survey_screen.TakeSurveyDialog(
                                    self.dbase,
                                    self,
                                    self.survey,
                                    self._students[qr_data]
                                )
                            )
                            vcap.release()
                            cv2.destroyAllWindows()
                            return
                    await asyncio.sleep(0.1)  # Allow log to update.
            wait_key = cv2.waitKey(50)  # Wait 50 miliseconds for key press.
            if wait_key in [ord("q"), ord("Q")]:
                break
        vcap.release()
        cv2.destroyAllWindows()
        await self.run_action("exit_scan_mode")      

    def restart_scanning(self) -> None:
        """Restart scanning for QR codes."""
        self.log_widget.write("Restarting Scanninig!!!!")
        self.set_timer(0.1, self.scan_qr_codes)  # Timer allows dialog to be dismissed.


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
                checkin_id=0,
                student_id=student_id,
                event_type=self.event_type,
                timestamp=timestamp,
            )
            checkin.add(self.dbase)
            self._write_checkin_message(student, checkin)
        self.discard_scanned_code(student_id)

    def _write_checkin_message(
        self, student: model.Student, checkin: model.Checkin
    ) -> None:
        """Get message that's displayed on the screen when a student checks in."""
        if not checkin.checkin_id:
            self.log_widget.write(
                "\n[red]"
                "************************* ERROR ********************************\n"
                "** Valid QR code, but error occurred while recording checkin. **\n"
                "**                 "
                "[reverse]Please speak to a mentor.[/]                  **\n"
                "****************************************************************"
                "[/]\n"
            )
            return
        if student.deactivated_on is None:
            self.log_widget.write(
                f"[green]Success: {student.first_name} {student.last_name} "
                f"checked in at {checkin.timestamp.strftime('%H:%M:%S')}[/]"
            )
        else:
            self.log_widget.write(
                "\n[yellow]"
                "*********************** WARNING ***********************************\n"
                "** Your QR code has been marked as inactive! This is most likely **\n"
                "** due to not completing all membership requirements.            **\n"
                "**    [/][reverse]Please speak to Stacy or another mentor.[/]"
                "[yellow]                   **\n"
                "*******************************************************************"
                "[/]\n"
            )

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


@dataclasses.dataclass
class DialogResult:
    """The Event type and survey selected in the dialog."""
    event_type: Optional[model.EventType]
    survey: Optional[model.Survey]

class ChooseTypeAndSurveyDialog(screen.ModalScreen[Optional[DialogResult]]):
    """Select event type and a survey when opening scan attendance screen."""

    dbase: model.DBase
    """Manages database."""
    surveys: dict[str, model.Survey]
    """Surveys that can be taken with attendance."""
    _default_survey_status_message: str = "Select a survey to view details"
    """Message shown when no survey is selected."""

    def __init__(self, dbase: model.DBase) -> None:
        super().__init__()
        self.title = "[bold]Select Event Type[/]"
        self.dbase = dbase
        self.surveys = {
            survey.title: survey for survey in model.Survey.get_all(self.dbase)
        }

    def compose(self) -> app.ComposeResult:
        """Arrange widgets within the dialog."""
        with containers.Vertical(id="event-type-dialog", classes="modal-dialog"):
            with containers.Horizontal():
                with containers.Vertical():
                    yield widgets.Label("Event Type", classes="emphasis")
                    event_options = widgets.OptionList(
                        *[option_list.Option(t.value.title(), id=t) for t in model.EventType],
                        id="event-type-option",
                    )
                    yield event_options
                    yield widgets.Label("Select a Survey (optional)", classes="emphasis")
                    yield widgets.Select(
                        [(survey.title, survey.title) for survey in self.surveys.values()],
                        allow_blank=True,
                        prompt="No Survey",
                        id="attendance-survey-select"
                    )
                yield widgets.Static(
                    self._default_survey_status_message,
                    id="attendance-survey-details",
                    classes="item-details"
                )
            with containers.Horizontal(classes="ok-cancel-row"):
                yield widgets.Button("Ok", id="event-type-select-ok-button")
                yield widgets.Button("Cancel", id="event-type-select-cancel-button")
        type_map = {opt.id: idx for idx, opt in enumerate(event_options.options)}
        event_options.highlighted = type_map[model.EventType.MEETING]

    @textual.on(widgets.Select.Changed, "#attendance-survey-select")
    def update_survey_details(self, message: widgets.Select.Changed) -> None:
        """Update the survey details panel."""
        status_widget = self.query_one("#attendance-survey-details", widgets.Static)
        if message.value == widgets.Select.BLANK:
            status_widget.update(self._default_survey_status_message)
            return
        survey = self.surveys.get(str(message.value))
        if survey is None:
            status_widget.update(self._default_survey_status_message)
            return
        details = [
            f"[bold]Title:[/bold] {survey.title}\n",
            f"[bold]Question:[/bold] {survey.question}\n",
            "[bold]Answer Options:[/bold]"
        ]
        for i, answer in enumerate(survey.answers, 1):
            details.append(f"  {i}. {answer}")
        details.extend([
            f"\n[bold]Multiselect:[/bold] {'Yes' if survey.multiselect else 'No'}",
            f"[bold]Allow Freetext:[/bold] {'Yes' if survey.allow_freetext else 'No'}"
        ])
        if survey.max_length:
            details.append(f"[bold]Max Length:[/bold] {survey.max_length}")
        status_widget.update("\n".join(details))

    @textual.on(widgets.Button.Pressed, "#event-type-select-ok-button")
    def on_ok_button_pressed(self) -> None:
        """Close the dialog and display the QR code scanning screen."""
        event_type_list = self.query_one("#event-type-option", widgets.OptionList)
        survey_select = self.query_one("#attendance-survey-select", widgets.Select)
        selected_index = event_type_list.highlighted
        if selected_index is None:
            self.dismiss(None)  # Don't take attendance if no event type selected.
        else:
            selected_event = cast(
                model.EventType, event_type_list.options[selected_index].id
            )
            if survey_select.selection is None:
                survey = None
            else:
                survey = self.surveys.get(survey_select.selection)
            self.dismiss(DialogResult(selected_event, survey))

    @textual.on(widgets.Button.Pressed, "#event-type-select-cancel-button")
    def on_cancel_button_pressed(self) -> None:
        """Close the dialog and return to the main screen."""
        self.dismiss(None)
