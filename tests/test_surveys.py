"""Test the surveys table and Survey objects."""

import pytest
import rich  # noqa: F401

from frcattend import model


def test_add_survey(noevents_dbase: model.DBase) -> None:
    """Create a survey and add it to the database."""
    # Arrange
    survey = model.Survey(
        title="Zodiacs",
        question="What's your sign?",
        answers=[
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
            "Virgo"
        ]
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
def test_get_survey_by_title(full_dbase: model.DBase, title: str, success: bool) -> None:
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
    survey.answers = ["Mario Kart", "Zelda"]
    survey.multiselect = True
    survey.allow_freetext = True
    survey.max_length = 25
    # Act
    survey.update(full_dbase)
    # Assert
    survey2 = model.Survey.get_by_title(full_dbase, "Subgroup")
    assert survey2 is not None
    assert survey2.question == survey.question
    assert survey2.answers == survey.answers
    assert survey2.multiselect
    assert survey2.allow_freetext
    assert survey2.max_length == 25
