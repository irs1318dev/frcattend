"""Test the surveys table and Survey objects."""

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


def test_get_surveys(noevents_dbase: model.DBase) -> None:
    """Retrieve a survey from the database."""
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
    survey.add(noevents_dbase)
    # Act
    surveys = model.Survey.get_all(noevents_dbase)
    # Assert
    assert len(surveys) == 1
    retrieved_survey = surveys[0]
    assert retrieved_survey.title == "Zodiacs"
    assert retrieved_survey.question == "What's your sign?"
    assert len(retrieved_survey.answers) == 12
    assert retrieved_survey.answers[0] == "Aquarius"
    assert not retrieved_survey.multiselect
    assert not retrieved_survey.allow_freetext
    assert retrieved_survey.max_length is None