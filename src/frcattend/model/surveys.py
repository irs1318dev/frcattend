"""Surveys present a qustion to students when they checkin."""

import dataclasses
import json
from typing import Any, ClassVar, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from frcattend.model import database


@dataclasses.dataclass
class Survey:
    """A question and a set of possible answers."""
    title: str
    question: str
    answers: list[str]
    multiselect: bool = False
    allow_freetext: bool = False
    max_length: int | None = None

    table_def: ClassVar[str] = """
        CREATE TABLE IF NOT EXISTS surveys (
                  title TEXT PRIMARY KEY,
               question TEXT NOT NULL,
                answers TEXT NOT NULL,
            multiselect INT NOT NULL,
         allow_freetext INT NOT NULL,
             max_length INT
        );
    """

    def __init__(
        self,
        title: str,
        question: str,
        answers: list[str] | str,
        multiselect: bool | int = False,
        allow_freetext: bool | int = False,
        max_length: Optional[int] = None
    ) -> None:
        """Convert fields from Sqlite to Python datataypes as needed."""
        self.title = title
        self.question = question
        if isinstance(answers, str):
            self.answers = json.loads(answers)
        else:
            self.answers = answers
        self.multiselect = bool(multiselect)
        self.allow_freetext = bool(allow_freetext)
        self.max_length = max_length

    @property
    def answers_json(self) -> str:
        """Convert survey options list to a string containing a JSON array."""
        return json.dumps(self.answers)
    
    def as_dict(self) -> dict[str, Any]:
        """Convert survey to a dictionary."""
        survey = dataclasses.asdict(self)
        survey["answers_json"] = self.answers_json
        return survey

    def add(self, dbase: "database.DBase") -> bool:
        """Add a survey to the database."""
        query = """
                INSERT INTO surveys
                            (title, question, answers, multiselect,
                            allow_freetext, max_length)
                     VALUES (:title, :question, :answers_json, :multiselect,
                            :allow_freetext, :max_length);
        """
        with dbase.get_db_connection() as conn:
            cursor = conn.execute(query, self.as_dict())
        rowcount = cursor.rowcount
        conn.close()
        return rowcount == 1
    
    @staticmethod
    def get_all(dbase: "database.DBase") -> list["Survey"]:
        """Retrive all surveys from the database."""
        query = """
                SELECT title, question, answers, multiselect,
                       allow_freetext, max_length
                  FROM surveys
              ORDER BY title;
        """
        conn = dbase.get_db_connection(as_dict=True)
        surveys = [Survey(**survey) for survey in conn.execute(query)]
        conn.close()
        return surveys