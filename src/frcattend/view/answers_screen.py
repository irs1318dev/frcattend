"""View survey results."""

import csv
import datetime
import pathlib
import re
from collections.abc import Callable
from typing import Any, cast

import textual
from textual import app, binding, containers, reactive, screen, widgets
from textual.widgets.data_table import ColumnKey

import frcattend.view
from frcattend import config, model
from frcattend.view import file_widgets, selector_widgets


def _sort_key_for_column(column_key: str | None) -> Callable[[Any], Any] | None:
    """Return a sort-key function for columns whose cell values need special handling.

    freetext_answer is None for answers without free text, which can't be
    compared to a string.
    """
    match column_key:
        case "freetext_answer":
            return lambda value: value or ""
        case _:
            return None


class SurveysTable(widgets.DataTable):
    """Table of surveys and the number of answers to each."""

    dbase: model.DBase
    """Connection to Sqlite Database."""
    surveys: dict[str, model.Survey]
    """Surveys that are displayed in the table."""

    def __init__(self, dbase: model.DBase, *args, **kwargs) -> None:
        """Set link to database."""
        super().__init__(*args, **kwargs, zebra_stripes=True)
        self.dbase = dbase
        self.surveys = {}

    def on_mount(self) -> None:
        """Initialize the table."""
        self.initialize_table()
        self.update_table()

    def initialize_table(self) -> None:
        """Define table columns."""
        self.cursor_type = "row"
        for col in [
            ("Title", "title"),
            ("Answers", "answer_count"),
            ("Multiselect", "multiselect"),
            ("Freetext", "allow_freetext"),
            ("Question", "question"),
        ]:
            self.add_column(col[0], key=col[1])

    def update_table(self) -> None:
        """Populate the table with surveys."""
        self.clear(columns=False)
        self.surveys = {
            survey.title: survey for survey in model.Survey.get_all(self.dbase)
        }
        answer_counts: dict[str, int] = {}
        for answer in model.Answer.get_all(self.dbase):
            answer_counts[answer.survey_title] = (
                answer_counts.get(answer.survey_title, 0) + 1
            )
        for title, survey in self.surveys.items():
            self.add_row(
                survey.title,
                answer_counts.get(title, 0),
                "Yes" if survey.multiselect else "No",
                "Yes" if survey.allow_freetext else "No",
                survey.question,
                key=title,
            )
        self.refresh()


class AnswersTable(widgets.DataTable):
    """Table of student answers to the selected survey."""

    dbase: model.DBase
    """Connection to Sqlite Database."""
    answers: dict[str, model.Answer]
    """Answers displayed in the table, keyed by student ID and answer date."""
    _sort_column_key: ColumnKey | None
    """Column the table is currently sorted by, if any."""
    _sort_reverse: bool
    """Whether the current column sort is descending."""

    def __init__(self, dbase: model.DBase, *args, **kwargs) -> None:
        """Set link to database."""
        super().__init__(*args, **kwargs, zebra_stripes=True)
        self.dbase = dbase
        self.answers = {}
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
        self.apply_sort()

    def apply_sort(self) -> None:
        """Sort the table by the current sort column, if one has been selected."""
        if self._sort_column_key is None:
            return
        self.sort(
            self._sort_column_key,
            key=_sort_key_for_column(self._sort_column_key.value),
            reverse=self._sort_reverse,
        )

    def initialize_table(self) -> None:
        """Define table columns."""
        self.cursor_type = "row"
        for col in [
            ("Last Name", "last_name"),
            ("First Name", "first_name"),
            ("Status", "status"),
            ("Grad Year", "grad_year"),
            ("Date", "answer_date"),
            ("Choices", "choices"),
            ("Freetext", "freetext_answer"),
        ]:
            self.add_column(col[0], key=col[1])

    def update_table(
        self,
        survey_title: str | None,
        stages: list[model.Stage] | None = None,
        grad_year: str | None = None,
        asof_date: datetime.date | None = None,
    ) -> None:
        """Populate the table with answers, filtered by the given criteria.

        The current sort column and direction are retained.
        """
        self.clear(columns=False)
        self.answers = {}
        if survey_title is None:
            return
        students = {
            student.student_id: student
            for student in model.Student.get_with_status(
                self.dbase, asof_date=asof_date, stages=stages
            )
        }
        if grad_year and len(grad_year) == 4:
            students = {
                student_id: student
                for student_id, student in students.items()
                if student.grad_year == int(grad_year)
            }
        for answer in model.Answer.get_by_title(self.dbase, survey_title):
            student = students.get(answer.student_id)
            if student is None:
                continue
            key = f"{answer.student_id}::{answer.iso_date}"
            self.answers[key] = answer
            self.add_row(
                student.last_name,
                student.first_name,
                student.status.stage.value if student.status else "",
                student.grad_year,
                answer.iso_date,
                ", ".join(answer.choices),
                answer.freetext_answer,
                key=key,
            )
        self.apply_sort()
        self.refresh()

    def export_csv(self, csv_path: pathlib.Path) -> int:
        """Write the displayed answers to a CSV file, in the displayed order.

        Returns:
            The number of answers written.
        """
        headers = ["Student ID"] + [col.label.plain for col in self.ordered_columns]
        # utf-8-sig so Excel detects the encoding.
        with open(csv_path, "w", newline="", encoding="utf-8-sig") as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow(headers)
            for row in self.ordered_rows:
                answer = self.answers[cast(str, row.key.value)]
                writer.writerow([answer.student_id, *self.get_row(row.key)])
        return self.row_count


class SurveyResults(screen.Screen):
    """View survey results."""

    dbase: model.DBase
    """Connection to Sqlite Database."""
    survey_title: reactive.reactive[str | None] = reactive.reactive(None, init=False)
    """Title of the currently selected survey."""

    CSS_PATH = frcattend.view.CSS_FOLDER / "answers_screen.tcss"
    # ruff: ignore[RUF012]
    BINDINGS = [
        binding.Binding("escape", "app.pop_screen", "Back to Main Screen", show=True),
    ]

    def __init__(self) -> None:
        """Initialize the database connection."""
        super().__init__()
        if config.settings.db_path is None:
            raise model.DBaseError("No database file selected.")
        self.dbase = model.DBase(config.settings.db_path)

    def compose(self) -> app.ComposeResult:
        """Add the datatables and filter controls to the screen."""
        yield widgets.Header()
        yield widgets.Static("Surveys", classes="separator emphasis")
        yield SurveysTable(dbase=self.dbase, id="answers-surveys-table")
        yield widgets.Static("Answers to Selected Survey", classes="separator emphasis")
        with containers.Horizontal(id="answers-container"):
            yield AnswersTable(dbase=self.dbase, id="answers-table")
            with containers.Vertical(id="answers-actions-container"):
                yield selector_widgets.StatusSelector(id="status-selector")
                yield selector_widgets.GradYearSelector(
                    self.dbase, id="grad-year-selector"
                )
                yield selector_widgets.GoBackSelector(value=None, id="asof-selector")
                yield widgets.Button(
                    "Export to CSV",
                    id="export-csv-button",
                    tooltip="Save the answers shown in the table to a CSV file.",
                )
        yield widgets.Footer()

    def watch_survey_title(self) -> None:
        """Reload the answers table when the selected survey changes."""
        self.load_answer_data()

    def load_answer_data(self) -> None:
        """Reload the answers table using the current filter selections."""
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
        self.query_one("#answers-table", AnswersTable).update_table(
            self.survey_title,
            stages=selected_stages,
            grad_year=grad_year,
            asof_date=asof_date,
        )

    @textual.on(widgets.SelectionList.SelectedChanged, "#status-selector")
    def on_status_selector_changed(self) -> None:
        """Reload answers when the selected stages change."""
        self.load_answer_data()

    @textual.on(widgets.Input.Changed, "#grad-year-selector")
    def on_grad_year_selector_changed(self) -> None:
        """Reload answers when the grad year filter changes."""
        self.load_answer_data()

    @textual.on(widgets.Input.Changed, "#asof-selector")
    def on_asof_selector_changed(self, event: widgets.Input.Changed) -> None:
        """Reload answers when the as-of date filter changes."""
        if event.input.is_valid or not event.value:
            self.load_answer_data()

    @textual.on(SurveysTable.RowHighlighted, "#answers-surveys-table")
    def on_surveys_table_row_highlighted(
        self, message: SurveysTable.RowHighlighted
    ) -> None:
        """Set the new survey title, which will trigger an answers table update."""
        self.survey_title = message.row_key.value

    @textual.on(widgets.Button.Pressed, "#export-csv-button")
    def on_export_csv_pressed(self) -> None:
        """Ask for a file name, then export the displayed answers to it."""
        if self.survey_title is None:
            self.notify("Select a survey first.", severity="warning")
            return
        answers_table = self.query_one("#answers-table", AnswersTable)

        def _export(csv_path: pathlib.Path | None) -> None:
            """Write the CSV file if a path was chosen."""
            if csv_path is None:
                return
            if csv_path.suffix.lower() != ".csv":
                csv_path = csv_path.with_name(csv_path.name + ".csv")
            if csv_path.exists():
                self.notify(f"{csv_path} already exists.", severity="error")
                return
            try:
                count = answers_table.export_csv(csv_path)
            except OSError as err:
                self.notify(f"Unable to write {csv_path}: {err}", severity="error")
                return
            self.notify(f"Exported {count} answers to {csv_path}.")

        default_filename = (
            re.sub(r"[^\w\-]+", "_", self.survey_title).strip("_")
            + f"_answers_{datetime.date.today().isoformat()}.csv"
        )
        self.app.push_screen(
            file_widgets.FileSelector(
                pathlib.Path.cwd(),
                [".csv"],
                create=True,
                default_filename=default_filename,
                id="answers-export-file",
                instructions=(
                    "Click on [i]Create File[/] to save the answers shown in the "
                    "table to a CSV file in the folder displayed in the directory "
                    "tree, or select [i]Cancel[/] to take no action."
                ),
            ),
            _export,
        )
