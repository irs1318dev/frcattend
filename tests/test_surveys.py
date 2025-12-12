"""Test the surveys table and Survey objects."""

import copy
import datetime
import random

import pytest
import rich  # noqa: F401

from frcattend import model


def test_add_survey(noevents_dbase: model.DBase) -> None:
    """Create a survey and add it to the database."""
    # Arrange
    survey = model.Survey(
        title="Zodiacs",
        question="What's your sign?",
        choices=[
            "Aquarius",
            "Aries",
            "Cancer",
            "Capricorn",
            "Gemini",
            "Leo",
            "Libra",
            "Pisces",
            "Sagittarius",
            "Scorpio",
            "Taurus",
            "Virgo",
        ],
    )
    # Act
    result = survey.add(noevents_dbase)
    # Assert
    assert result
    assert not survey.multiselect
    assert not survey.allow_freetext
    assert survey.max_length is None


def test_get_surveys(full_dbase: model.DBase) -> None:
    """Retrieve a survey from the database."""
    # Act
    surveys = model.Survey.get_all(full_dbase)
    # Assert
    assert len(surveys) == 3
    assert all(isinstance(survey, model.Survey) for survey in surveys)


@pytest.mark.parametrize(
    "title,success", [("Subgroup", True), ("Favorite Videogame", False)]
)
def test_get_survey_by_title(
    full_dbase: model.DBase, title: str, success: bool
) -> None:
    """Get a survey from the database, or None if it doesn't exist."""
    # Act
    survey = model.Survey.get_by_title(full_dbase, title)
    # Assert
    if success:
        assert survey is not None
        assert isinstance(survey, model.Survey)
        assert survey.title == title
    else:
        assert survey is None


def test_update_survey(full_dbase: model.DBase) -> None:
    """Update a survey entry in the database."""
    # Arrange
    survey = model.Survey.get_by_title(full_dbase, "Subgroup")
    assert survey is not None
    survey.question = "Favorite video game?"
    survey.choices = ["Mario Kart", "Zelda"]
    survey.multiselect = True
    survey.allow_freetext = True
    survey.max_length = 25
    # Act
    survey.update(full_dbase)
    # Assert
    survey2 = model.Survey.get_by_title(full_dbase, "Subgroup")
    assert survey2 is not None
    assert survey2.question == survey.question
    assert survey2.choices == survey.choices
    assert survey2.multiselect
    assert survey2.allow_freetext
    assert survey2.max_length == 25


@pytest.mark.parametrize(
    "title,success", [("Subgroup", True), ("Favorite Video Game", False)]
)
def test_delete_survey(full_dbase: model.DBase, title: str, success: bool) -> None:
    """Delete a survey."""
    # Act
    delete_result = model.Survey.delete_by_title(full_dbase, title)
    # Assert
    assert delete_result == success
    assert len(model.Survey.get_all(full_dbase)) == 2 if success else 3
    assert model.Survey.get_by_title(full_dbase, title) is None


def test_add_new_answer(full_dbase: model.DBase) -> None:
    """Add an answer for a student with no prior answers."""
    # Arrange
    student_id = random.choice(model.Student.get_all_ids(full_dbase))
    survey = model.Survey.get_by_title(full_dbase, "Subgroup")
    assert survey is not None
    choice = random.choice(survey.choices)
    answer = model.Answer(student_id, survey.title, choice, datetime.date.today())
    # Act
    answer.add(full_dbase)
    # Assert
    db_answers = model.Answer.get_by_title_and_student(
        full_dbase, survey.title, student_id
    )
    assert isinstance(db_answers, list)
    assert len(db_answers) == 1
    assert db_answers[0].survey_title == survey.title
    assert db_answers[0].student_id == student_id
    assert db_answers[0].answer_date == datetime.date.today()
    selected_answers = db_answers[0].choices
    assert selected_answers is not None
    assert len(selected_answers) == 1
    assert selected_answers[0] == choice
    assert db_answers[0].freetext_answer is None


@pytest.mark.parametrize("replace", [(False, True)])
def test_replace_answer_on_same_date(full_dbase: model.DBase, replace) -> None:
    """Add answer for a survey that has already been answered on same date.

    The replace argument should have no effect. Answers on the same day should
    always be replaced.
    """
    # Arrange
    student_id = random.choice(model.Student.get_all_ids(full_dbase))
    survey = model.Survey.get_by_title(full_dbase, "Subgroup")
    assert survey is not None
    choices = copy.deepcopy(survey.choices)
    random.shuffle(choices)
    choice1 = choices.pop()
    answer = model.Answer(student_id, survey.title, choices=choice1)
    answer.add(full_dbase)
    # Act
    choice2 = choices.pop()
    answer.choices = [choice2]
    answer.add(full_dbase, replace=replace)
    # Assert
    db_answers = model.Answer.get_by_title_and_student(
        full_dbase, survey.title, student_id
    )
    assert isinstance(db_answers, list)
    assert len(db_answers) == 1
    selected_answers = db_answers[0].choices
    assert selected_answers is not None
    assert len(selected_answers) == 1
    assert selected_answers[0] == choice2


@pytest.mark.parametrize("replace", [(False, True)])
def test_add_new_answer_on_later_date(full_dbase: model.DBase, replace) -> None:
    """Add answer for a survey that was already answered on a prior date."""
    # Arrange
    student_id = random.choice(model.Student.get_all_ids(full_dbase))
    survey = model.Survey.get_by_title(full_dbase, "Subgroup")
    assert survey is not None
    choices = copy.deepcopy(survey.choices)
    random.shuffle(choices)
    choice1 = choices.pop()
    yesterday = datetime.date.today() - datetime.timedelta(days=1)
    answer = model.Answer(student_id, survey.title, choice1, yesterday, choice1)
    answer.add(full_dbase)
    # Act
    choice2 = choices.pop()
    answer.choices = [choice2]
    answer.answer_date = datetime.date.today()
    answer.add(full_dbase, replace=replace)
    # Assert
    db_answers = model.Answer.get_by_title_and_student(
        full_dbase, survey.title, student_id
    )
    assert isinstance(db_answers, list)
    assert len(db_answers) == 1 if replace else 2
    assert db_answers[-1].choices is not None
    assert len(db_answers[-1].choices) == 1
    assert db_answers[-1].choices[0] == choice2
