"""Create, edit, and view surveys."""

import datetime
from typing import Optional, TYPE_CHECKING

import textual
from textual import app, binding, containers, message, screen, validation, widgets
from textual.widgets import option_list

from frcattend import config, model
import frcattend.view
from frcattend.view import validators

if TYPE_CHECKING:
    from frcattend.view import take_attendance


class SurveyScreen(screen.Screen):
    """Manage surveys."""

    dbase: model.DBase
    """Connection to Sqlite Database."""
    survey_table: widgets.DataTable
    """Table that holds survey data."""
    _selected_survey_title: Optional[str]
    """Currently selected survey."""
    _surveys: dict[str, model.Survey]
    """List of surveys currently loaded in the datatable."""

    CSS_PATH = frcattend.view.CSS_FOLDER / "survey_screen.tcss"
    BINDINGS = [
        binding.Binding("escape", "app.pop_screen", "Back to Main Screen", show=True),
    ]

    def __init__(self) -> None:
        """Initialize the database connection."""
        super().__init__()
        if config.settings.db_path is None:
            raise model.DBaseError("No database file selected.")
        self.dbase = model.DBase(config.settings.db_path)
        self._surveys = {}

    def compose(self) -> app.ComposeResult:
        """Build the survey screen's user interface."""
        yield widgets.Header()
        with containers.Horizontal(classes="menu"):
            yield widgets.Button(
                "Add Survey",
                variant="success",
                id="add-survey",
                tooltip="Add a new survey to the database.",
            )
            yield widgets.Button(
                "Edit Selected",
                id="edit-survey",
                disabled=True,
                tooltip="Edit the selected survey.",
            )
            yield widgets.Button(
                "Delete Selected",
                variant="error",
                id="delete-survey",
                disabled=True,
                tooltip="Delete the selected survey.",
            )
        yield widgets.Label("Survey List")
        yield widgets.DataTable(zebra_stripes=True, id="survey-table")
        yield widgets.Label("Survey Details", classes="emphasis")
        with containers.ScrollableContainer():
            yield widgets.Static(
                "Select a survey to view details",
                id="survey-details",
                classes="item-details",
            )
        yield widgets.Footer()

    def on_mount(self) -> None:
        """Initialize the datatable widget."""
        self.initialize_survey_table()
        self.load_survey_table()

    def initialize_survey_table(self) -> None:
        """Create the columns in the survey table."""
        self.survey_table = self.query_one(widgets.DataTable)
        self.survey_table.cursor_type = "row"
        for col in [
            ("Title", "title", 40),
            ("Question", "question", None),
        ]:
            self.survey_table.add_column(col[0], key=col[1], width=col[2])

    def load_survey_table(self) -> None:
        """Load survey data into the datatable widget."""
        self.survey_table.clear(columns=False)
        self._surveys = {
            survey.title: survey for survey in model.Survey.get_all(self.dbase)
        }
        for survey in self._surveys.values():
            self.survey_table.add_row(survey.title, survey.question, key=survey.title)
        self._selected_survey_title = None

    def on_data_table_row_selected(self, event: widgets.DataTable.RowSelected) -> None:
        """Select a row in the datatable."""
        self._selected_survey_title = event.row_key.value
        if self._selected_survey_title is None:
            return
        self.query_one("#edit-survey", widgets.Button).disabled = False
        self.query_one("#delete-survey", widgets.Button).disabled = False
        survey = self._surveys[self._selected_survey_title]
        self.update_details(survey)

    def update_details(self, survey: model.Survey) -> None:
        """Update the survey details panel."""
        details = f"[bold]Title:[/bold] {survey.title}\n\n"
        details += f"[bold]Question:[/bold] {survey.question}\n\n"
        details += "[bold]Choices:[/bold]\n"
        for i, choice in enumerate(survey.choices, 1):
            details += f"  {i}. {choice}\n"
        details += (
            f"\n[bold]Multiselect:[/bold] {'Yes' if survey.multiselect else 'No'}\n"
        )
        details += (
            f"[bold]Allow Freetext:[/bold] {'Yes' if survey.allow_freetext else 'No'}\n"
        )
        if survey.max_length:
            details += f"[bold]Max Length:[/bold] {survey.max_length}\n"
        replace = "Yes" if survey.allow_freetext else "No"
        details += f"[bold]Replace Prior Answer:[/bold] {replace}\n"
        self.query_one("#survey-details", widgets.Static).update(details)

    @textual.work
    @textual.on(widgets.Button.Pressed, "#add-survey")
    async def action_add_survey(self) -> None:
        """Show the survey dialog and add a new survey."""
        if await self.app.push_screen_wait(
            EditSurveyDialog(dbase=self.dbase, survey=None)
        ):
            self.load_survey_table()

    @textual.work
    @textual.on(widgets.Button.Pressed, "#edit-survey")
    async def action_edit_survey(self) -> None:
        """Edit the selected survey."""
        if self._selected_survey_title is None:
            return
        if await self.app.push_screen_wait(
            EditSurveyDialog(
                dbase=self.dbase, survey=self._surveys[self._selected_survey_title]
            )
        ):
            self.load_survey_table()

    @textual.on(widgets.Button.Pressed, "#delete-survey")
    async def action_delete_survey(self) -> None:
        """Delete the selected survey."""
        if self._selected_survey_title is None:
            return
        model.Survey.delete_by_title(self.dbase, self._selected_survey_title)
        self.load_survey_table()


class EditSurveyDialog(screen.ModalScreen):
    """A dialog for adding or editing surveys."""

    CSS_PATH = frcattend.view.CSS_FOLDER / "survey_screen.tcss"

    survey: model.Survey | None
    """Survey to be edited. None if adding a new survey."""
    dbase: model.DBase
    """Database containing survey data."""
    _validator_results: dict[str, validation.ValidationResult | None]
    """Validation results for dialog inputs, [id: ValidationResult]."""

    def __init__(self, dbase: model.DBase, survey: model.Survey | None = None) -> None:
        """Set survey information if provided."""
        super().__init__()
        self.dbase = dbase
        self.survey = survey
        self._validator_results = {
            "survey-title-input": None,
            "survey-question-input": None,
            "survey-max-length-input": None,
        }

    def compose(self) -> app.ComposeResult:
        """Create and arrange dialog widgets."""
        dialog_title = "Create Survey" if self.survey is None else "Edit Survey"
        with containers.Vertical(id="survey-dialog", classes="modal-dialog"):
            yield widgets.Label(dialog_title, classes="emphasis")
            if self.survey is not None:
                yield widgets.Label(f"Title: {self.survey.title}")
            else:
                yield widgets.Input(
                    placeholder="Title",
                    id="survey-title-input",
                    classes="validated",
                    validators=[validators.NotEmpty()],
                    tooltip=(
                        "Add a short title that describes the surveys. "
                        "Titles must be unique, so ensure this title is different from "
                        "all other survey titles."
                    ),
                )
            yield widgets.Input(
                value="" if self.survey is None else self.survey.question,
                placeholder="Question",
                id="survey-question-input",
                classes="validated",
                validators=[validators.NotEmpty()],
                tooltip=("Enter the survey question."),
            )
            yield widgets.TextArea(
                text="" if self.survey is None else "\n".join(self.survey.choices),
                id="survey-choices-text",
                tooltip=("Enter each choice on a separate line."),
            )
            with containers.Horizontal(id="survey-freetext-row"):
                freetext_checkbox = widgets.Checkbox(
                    "Allow freetext answer",
                    self.survey is not None and self.survey.allow_freetext,
                    id="survey-freetext-checkbox",
                    tooltip="Check this box to allow students to type an answer.",
                )
                yield freetext_checkbox
                if self.survey is None or self.survey.max_length is None:
                    max_length_text = ""
                else:
                    max_length_text = str(self.survey.max_length)
                yield widgets.Input(
                    value=max_length_text,
                    id="survey-max-length-input",
                    classes="validated",
                    placeholder="Max freetext length",
                    disabled=not freetext_checkbox.value,
                    tooltip=(
                        "Set to a positive to integer to limit the length of "
                        "answers that are typed in by a student. There is no limit "
                        "if left empty. Has no effect if 'Allow freetext answer' is "
                        "not checked."
                    ),
                    validators=[validators.IsPositiveInteger()],
                )
            yield widgets.Checkbox(
                "Allow student to select multiple choices.",
                self.survey is not None and self.survey.multiselect,
                id="survey-multiselect-checkbox",
                tooltip=(
                    "Check this box to allow students to select multiple choices "
                    "from the list."
                ),
            )
            yield widgets.Checkbox(
                "Replace prior answers",
                self.survey is not None and self.survey.replace,
                id="survey-replace-checkbox",
                tooltip=(
                    "Check this box if newer answers should replace older answers."
                ),
            )
            yield widgets.Static()
            with containers.Horizontal(classes="ok-cancel-row"):
                yield widgets.Button("Save", variant="primary", id="save-survey")
                yield widgets.Button("Cancel", id="cancel-survey")

    @textual.on(widgets.Checkbox.Changed, "#survey-freetext-checkbox")
    def on_freetext_check(self, message: widgets.Checkbox.Changed) -> None:
        """Toggle max-length disabled state when freetext checkbox is changed."""
        freetext_len = self.query_one("#survey-max-length-input", widgets.Input)
        freetext_len.disabled = not message.checkbox.value

    @textual.on(widgets.Input.Blurred, ".validated")
    def on_blur(self, message: widgets.Input.Blurred) -> None:
        """Track input validation status."""
        if message.input.id is not None and message.input.id in self._validator_results:
            self._validator_results[message.input.id] = message.validation_result

    @textual.on(widgets.Button.Pressed, "#cancel-survey")
    def cancel_dialog(self) -> None:
        """Close the dialog and take no action."""
        self.dismiss(False)

    @textual.on(widgets.Button.Pressed, "#save-survey")
    def save_survey(self) -> None:
        """Save the survey information when the user clicks the Save button."""
        valid = True
        add_new = self.survey is None
        for widget_id, val_result in self._validator_results.items():
            if (
                isinstance(val_result, validation.ValidationResult)
                and not val_result.is_valid
            ):
                valid = False
                self.notify(
                    f"Invalid input for {widget_id}: {val_result.failure_descriptions}"
                )
        if not valid:
            return
        question = self.query_one("#survey-question-input", widgets.Input).value
        choice_input = self.query_one("#survey-choices-text", widgets.TextArea)
        choices = [choice.strip() for choice in choice_input.text.split("\n")]
        multiselect = self.query_one(
            "#survey-multiselect-checkbox", widgets.Checkbox
        ).value
        freetext = self.query_one("#survey-freetext-checkbox", widgets.Checkbox).value
        max_length_raw = self.query_one("#survey-max-length-input", widgets.Input).value
        if not max_length_raw or max_length_raw is None:
            max_length = None
        else:
            max_length = int(max_length_raw)
        replace = self.query_one("#survey-replace-checkbox", widgets.Checkbox).value
        if self.survey is None:
            title = self.query_one("#survey-title-input", widgets.Input).value
        else:
            title = self.survey.title
        self.survey = model.Survey(
            title=title,
            question=question,
            choices=choices,
            multiselect=multiselect,
            allow_freetext=freetext,
            max_length=max_length,
            replace=replace,
        )
        if add_new:
            success = self.survey.add(self.dbase)
        else:
            success = self.survey.update(self.dbase)
        if not success:
            self.notify("Error updating survey.")
        self.dismiss(success)


class TakeSurveyDialog(screen.ModalScreen):
    """Take a survey when checking in."""

    class FinishedSurvey(message.Message):
        """Send when finishing survey."""

    CSS_PATH = frcattend.view.CSS_FOLDER / "survey_screen.tcss"

    survey: model.Survey
    """Survey to be edited. None if adding a new survey."""
    student: model.Student
    """Student taking the survey."""
    dbase: model.DBase
    """Database containing survey data."""
    _validator_results: dict[str, validation.ValidationResult | None]
    """Validation results for dialog inputs, [id: ValidationResult]."""
    _scan_screen: "take_attendance.ScanScreen"

    def __init__(
        self,
        dbase: model.DBase,
        scan_screen: "take_attendance.ScanScreen",
        survey: model.Survey,
        student: model.Student,
    ) -> None:
        """Set database, survey, and student ID for the dialog."""
        super().__init__()
        self.dbase = dbase
        self._scan_screen = scan_screen
        self.survey = survey
        self.student = student
        self._validator_results = {}

    def compose(self) -> app.ComposeResult:
        """Create and arrange dialog widgets."""
        with containers.Vertical(id="attendance-take-survey", classes="modal-dialog"):
            yield widgets.Static(self.survey.title, id="take-survey-title")
            yield widgets.Label(
                f"Hello {self.student.first_name}!", id="take-survey-student-name"
            )
            yield widgets.Static(
                self.survey.question, id="take-survey-question", classes="emphasis"
            )
            if self.survey.multiselect:
                selections = [(s, s) for s in self.survey.choices]
                yield widgets.SelectionList[str](*selections, id="take-survey-multi")
            else:
                options = [option_list.Option(s, id=s) for s in self.survey.choices]
                yield widgets.OptionList(*options, id="take-survey-single")
            if self.survey.allow_freetext:
                yield widgets.Label("Custom Answer", id="take-survey-freetext-label")
                yield widgets.Input(id="take-survey-freetext")
            with containers.Horizontal(classes="ok-cancel-row"):
                yield widgets.Button("Ok", id="take-survey-ok-button")
                yield widgets.Button("Cancel", id="take-survey-cancel-button")

    @textual.on(widgets.Button.Pressed, "#take-survey-cancel-button")
    def on_cancel_button_pressed(self) -> None:
        """Close the dialog and return to the main screen."""
        self.dismiss()
        self._scan_screen.restart_scanning()

    @textual.on(widgets.Button.Pressed, "#take-survey-ok-button")
    def on_ok_button_pressed(self) -> None:
        if self.survey.multiselect:
            selector = self.query_one("#take-survey-multi", widgets.SelectionList)
            choices: list[str] = selector.selected
        else:
            option_list = self.query_one("#take-survey-single", widgets.OptionList)
            highlighted = option_list.highlighted_option
            if highlighted is None or highlighted.id is None:
                choices = []
            else:
                choices = [highlighted.id]
        if self.survey.allow_freetext:
            freetext_input = self.query_one("#take-survey-freetext", widgets.Input)
            freetext = freetext_input.value if freetext_input.value else None
        else:
            freetext = None
        """Close the dialog and return to the main screen."""
        answer = model.Answer(
            self.student.student_id,
            self.survey.title,
            choices,
            datetime.datetime.today(),
            freetext_answer=freetext,
        )
        answer.add(self.dbase)
        self.dismiss()
        self._scan_screen.restart_scanning()
