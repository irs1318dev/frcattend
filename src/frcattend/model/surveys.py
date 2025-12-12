"""Surveys present a qustion to students when they checkin."""

import dataclasses
import datetime
import json
from typing import Any, ClassVar, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from frcattend.model import database


class SurveyError(Exception):
    """Error related to surveys and answers."""


@dataclasses.dataclass
class Survey:
    """A question and a set of choices."""

    title: str
    """Short, unique (a few words) title that identifies the survey."""
    question: str
    """Question that is presented to students who are taking the survey."""
    choices: list[str]
    """Possible answers displayed in the multiple-choice section of the survey. """
    multiselect: bool = False
    """True if students can selected more than one choice."""
    allow_freetext: bool = False
    """Students are allowed to type their answer into an input box if True."""
    max_length: int | None = None
    """Max length in characters of freetext answer. None if not allow_freetext."""
    replace: bool = True
    """If True, older answers are always replaced by the most recent answer.
    
    For some surveys, if they are given every year, we'll want to retain
    answers from prior years in the database (replace=True). For others, we only
    want the most recent answer.

    Note: If a student answers a survey twice on the same day, only the latest
    answer is retained, regardless of the value of replace. This allows a
    student to change their answer if they realized they initially gave an
    incorrect answer.
    """

    table_def: ClassVar[str] = """
        CREATE TABLE IF NOT EXISTS surveys (
                  title TEXT PRIMARY KEY,
               question TEXT NOT NULL,
                choices TEXT NOT NULL,
            multiselect BOOL NOT NULL,
         allow_freetext BOOL NOT NULL,
             max_length INT,
                replace BOOL NOT NULL
        );
    """

    def __init__(
        self,
        title: str,
        question: str,
        choices: list[str] | str,
        multiselect: bool = False,
        allow_freetext: bool = False,
        max_length: Optional[int] = None,
        replace: bool = True,
    ) -> None:
        """Convert fields from Sqlite to Python datataypes as needed."""
        self.title = title
        self.question = question
        if isinstance(choices, str):
            self.choices = json.loads(choices)
        else:
            self.choices = choices
        self.multiselect = multiselect
        self.allow_freetext = allow_freetext
        self.max_length = max_length
        self.replace = replace

    @property
    def choices_json(self) -> str:
        """Convert survey options list to a string containing a JSON array."""
        return json.dumps(self.choices)

    def to_dict(self) -> dict[str, Any]:
        """Convert survey to a dictionary."""
        return dataclasses.asdict(self)

    def add(self, dbase: "database.DBase") -> bool:
        """Add a survey to the database."""
        query = """
                INSERT INTO surveys
                            (title, question, choices, multiselect,
                            allow_freetext, max_length, replace)
                     VALUES (:title, :question, :choices_json, :multiselect,
                            :allow_freetext, :max_length, :replace);
        """
        with dbase.get_db_connection() as conn:
            cursor = conn.execute(
                query, {**self.to_dict(), "choices_json": self.choices_json}
            )
        rowcount = cursor.rowcount
        conn.close()
        return rowcount == 1

    def update(self, dbase: "database.DBase") -> bool:
        """Update the survey in the database."""
        query = """
                UPDATE surveys
                   SET question = :question,
                       choices = :choices_json,
                       multiselect = :multiselect,
                       allow_freetext = :allow_freetext,
                       max_length = :max_length,
                       replace = :replace
                 WHERE title = :title;
        """
        with dbase.get_db_connection() as conn:
            cursor = conn.execute(
                query, {**self.to_dict(), "choices_json": self.choices_json}
            )
        rowcount = cursor.rowcount
        conn.close()
        return rowcount == 1

    @staticmethod
    def delete_by_title(dbase: "database.DBase", title: str) -> bool:
        """Delete the survey's database record."""
        query = """
                DELETE FROM surveys
                      WHERE title = :title;
        """
        with dbase.get_db_connection() as conn:
            cursor = conn.execute(query, {"title": title})
        rowcount = cursor.rowcount
        conn.close()
        return rowcount == 1

    @staticmethod
    def get_by_title(dbase: "database.DBase", title: str) -> "Survey | None":
        """Get the survey with the givent title, or None if it doesn't exist."""
        query = """
                SELECT title, question, choices, multiselect,
                       allow_freetext, max_length, replace
                  FROM surveys
                 WHERE title = :title;
        """
        conn = dbase.get_db_connection(as_dict=True)
        result = conn.execute(query, {"title": title}).fetchone()
        conn.close()
        if result:
            return Survey(**result)
        return None

    @staticmethod
    def get_all(dbase: "database.DBase") -> list["Survey"]:
        """Retrive all surveys from the database."""
        query = """
                SELECT title, question, choices, multiselect,
                       allow_freetext, max_length, replace
                  FROM surveys
              ORDER BY title;
        """
        conn = dbase.get_db_connection(as_dict=True)
        surveys = [Survey(**survey) for survey in conn.execute(query)]
        conn.close()
        return surveys


@dataclasses.dataclass
class Answer:
    """An answer to a survey question."""

    student_id: str
    survey_title: str
    answer_date: datetime.date
    choices: list[str]
    freetext_answer: str | None = None

    table_def: ClassVar[str] = """
        CREATE TABLE IF NOT EXISTS answers (
             student_id TEXT NOT NULL,
           survey_title TEXT NOT NULL,
            answer_date DATE NOT NULL,
                choices TEXT,
        freetext_answer INT,
            PRIMARY KEY (student_id, survey_title, answer_date) ON CONFLICT REPLACE,
            FOREIGN KEY (survey_title) REFERENCES surveys (title)
        );
    """

    def __init__(
        self,
        student_id: str,
        survey_title: str,
        choices: list[str] | str,
        answer_date: datetime.date | str | None = None,
        freetext_answer: str | None = None,
    ) -> None:
        """Convert fields from Sqlite to Python datatypes as needed."""
        self.student_id = student_id
        self.survey_title = survey_title
        match answer_date:
            case None:
                self.answer_date = datetime.date.today()
            case str():
                self.answer_date = datetime.datetime.fromisoformat(answer_date).date()
            case datetime.date():
                self.answer_date = answer_date
            case _:
                raise SurveyError(
                    "Invalid answer_date argument. "
                    "Must be None, datetime.date, or ISO date as string."
                )
        if isinstance(choices, str):
            try:
                self.choices = json.loads(choices)
                if not isinstance(self.choices, list):
                    self.choices = [choices]
            except json.JSONDecodeError:
                self.choices = [choices]
        else:
            self.choices = choices
        self.freetext_answer = freetext_answer

    @property
    def choices_json(self) -> str:
        """Selected answers as a JSON string."""
        return json.dumps(self.choices)

    def to_dict(self) -> dict[str, Any]:
        """Convert answer object to a dictionary."""
        return {**dataclasses.asdict(self), "choices_json": self.choices_json}

    def add(self, dbase: "database.DBase", replace: bool = True) -> bool:
        """Add an answer to the answers table."""
        prior_answers = self.get_by_title_and_student(
            dbase, self.survey_title, self.student_id
        )
        prior_dates = set(answer.answer_date for answer in prior_answers)
        if len(prior_answers) == 0 or self.answer_date in prior_dates or not replace:
            query = """
                    INSERT INTO answers
                                (student_id, survey_title, answer_date,
                                choices, freetext_answer)
                        VALUES (:student_id, :survey_title, :answer_date,
                                :choices_json, :freetext_answer);
            """
        else:
            query = """
                    UPDATE answers
                       SET answer_date = :answer_date,
                           choices = :choices_json,
                           freetext_answer = :freetext_answer
                     WHERE survey_title = :survey_title AND
                           student_id = :student_id;
            """
        with dbase.get_db_connection() as conn:
            cursor = conn.execute(query, self.to_dict())
        rowcount = cursor.rowcount
        conn.close()
        return rowcount == 1

    def update(self, dbase: "database.DBase") -> bool:
        """Update the answer in the database."""
        query = """
                UPDATE answers
                   SET choices = :choices_json,
                       freetext_answer = :freetext_answer
                 WHERE student_id = :student_id
                   AND survey_title = :survey_title
                   AND answer_date = :answer_date;
        """
        with dbase.get_db_connection() as conn:
            cursor = conn.execute(query, self.to_dict())
        rowcount = cursor.rowcount
        conn.close()
        return rowcount == 1

    @staticmethod
    def get_all(dbase: "database.DBase") -> list["Answer"]:
        """Retrive all answers from the database."""
        query = """
                SELECT student_id, survey_title, answer_date,
                       choices, freetext_answer
                  FROM answers
              ORDER BY survey_title, student_id, answer_date DESC;
        """
        conn = dbase.get_db_connection(as_dict=True)
        answers = [Answer(**answer) for answer in conn.execute(query)]
        conn.close()
        return answers

    @staticmethod
    def get_by_title_and_student(
        dbase: "database.DBase", survey_title: str, student_id: str
    ) -> list["Answer"]:
        """Get all answers for a specific survey and student."""
        query = """
                SELECT student_id, survey_title, answer_date,
                       choices, freetext_answer
                  FROM answers
                 WHERE survey_title = :survey_title
                   AND student_id = :student_id
              ORDER BY answer_date DESC;
        """
        conn = dbase.get_db_connection(as_dict=True)
        cursor = conn.execute(
            query, {"survey_title": survey_title, "student_id": student_id}
        )
        answers = [Answer(**answer) for answer in cursor]
        conn.close()
        return answers
