"""Create, edit, and view surveys."""

from typing import Optional

import textual
from textual import app, binding, containers, screen, validation, widgets

from frcattend import config, model
import frcattend.view
from frcattend.view import validators


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
            survey.title: survey
            for survey in model.Survey.get_all(self.dbase)
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
        details += f"[bold]Answer Options:[/bold]\n"
        for i, answer in enumerate(survey.answers, 1):
            details += f"  {i}. {answer}\n"
        details += f"\n[bold]Multiselect:[/bold] {'Yes' if survey.multiselect else 'No'}\n"
        details += f"[bold]Allow Freetext:[/bold] {'Yes' if survey.allow_freetext else 'No'}\n"
        if survey.max_length:
            details += f"[bold]Max Length:[/bold] {survey.max_length}\n"
        self.query_one("#survey-details", widgets.Static).update(details)

    @textual.work
    @textual.on(widgets.Button.Pressed, "#add-survey")
    async def action_add_survey(self) -> None:
        """Show the survey dialog and add a new survey."""
        if await self.app.push_screen_wait(
            SurveyDialog(dbase=self.dbase, survey=None)
        ):
            self.load_survey_table()

    @textual.work
    @textual.on(widgets.Button.Pressed, "#edit-survey")
    async def action_edit_survey(self) -> None:
        """Edit the selected survey."""
        if self._selected_survey_title is None:
            return
        if await self.app.push_screen_wait(
            SurveyDialog(
                dbase=self.dbase,
                survey=self._surveys[self._selected_survey_title])
        ):
            self.load_survey_table()

    @textual.on(widgets.Button.Pressed, "#delete-survey")
    async def action_delete_survey(self) -> None:
        """Delete the selected survey."""
        if self._selected_survey_title is None:
            return
        model.Survey.delete_by_title(self.dbase, self._selected_survey_title)
        self.load_survey_table()


class SurveyDialog(screen.ModalScreen):
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
            "survey-max-length-input": None
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
                )
            )
            yield widgets.Input(
                value="" if self.survey is None else self.survey.question,
                placeholder="Question",
                id="survey-question-input",
                classes="validated",
                validators=[validators.NotEmpty()],
                tooltip=("Enter the survey question.")
            )
            yield widgets.TextArea(
                text="" if self.survey is None else "\n".join(self.survey.answers),
                id="survey-answers-text",
                tooltip=("Enter each possible answer on a separate line.")
            )
            yield widgets.Checkbox(
                "Allow multiple answers",
                self.survey is not None and self.survey.multiselect,
                id="survey-multiselect-checkbox",
                tooltip=(
                    "Check this box to allow students to select multiple answers "
                    "from the list."
                )
            )
            with containers.Horizontal():
                freetext_checkbox = widgets.Checkbox(
                    "Allow freetext answer",
                    self.survey is not None and self.survey.allow_freetext,
                    id="survey-freetext-checkbox",
                    tooltip="Check this box to allow students to type an answer."
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
                    validators=[validators.IsPositiveInteger()]
                )
            yield widgets.Static()
            with containers.Horizontal(classes="dialog-row"):
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
                isinstance(val_result, validation.ValidationResult) and
                not val_result.is_valid
            ):
                valid = False
                self.notify(
                    f"Invalid input for {widget_id}: {val_result.failure_descriptions}")
        if not valid:
            return
        question = self.query_one("#survey-question-input", widgets.Input).value
        answer_input = self.query_one("#survey-answers-text", widgets.TextArea)
        answers = [answer.strip() for answer in answer_input.text.split("\n")]
        multiselect = (
            self.query_one("#survey-multiselect-checkbox", widgets.Checkbox).value
        )
        freetext = (
            self.query_one("#survey-freetext-checkbox", widgets.Checkbox).value
        )
        max_length_raw = self.query_one("#survey-max-length-input", widgets.Input).value
        if not max_length_raw or max_length_raw is None:
            max_length = None
        else:
            max_length = int(max_length_raw)
        if self.survey is None:
            title = self.query_one("#survey-title-input", widgets.Input).value
        else:
            title = self.survey.title
        self.survey = model.Survey(
            title=title,
            question=question,
            answers=answers,
            multiselect=multiselect,
            allow_freetext=freetext,
            max_length=max_length
            )
        if add_new:
            success = self.survey.add(self.dbase)
        else:
            success = self.survey.update(self.dbase)
        if not success:
            self.notify("Error updating survey.")
        self.dismiss(success)