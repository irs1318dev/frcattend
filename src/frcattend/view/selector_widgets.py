"""Widgets for selecting student status."""

import datetime
import re
from typing import Optional

from textual import validation, widgets

from frcattend import model


class StatusSelector(widgets.SelectionList[model.Stage]):
    """Selection list of student stages."""

    def __init__(
        self,
        name: Optional[str] = None,
        id: Optional[str] = None,
        classes: Optional[str] = None,
        disabled: bool = False,
    ) -> None:
        """Populate options from the Stage enum.

        MEMBER and PROSPECT stages are checked by default.
        """
        checked_stages = (
            model.Stage.MEMBER,
            model.Stage.PROSPECT,
            model.Stage.ROOKIE,
            model.Stage.VETERAN
        )
        super().__init__(
            *[
                (stage.value.title(), stage, stage in checked_stages)
                for stage in model.Stage
            ],
            name=name,
            id=id,
            classes=classes,
            disabled=disabled,
        )


class GradYearValidator(validation.Validator):
    """Validate that a value is a four-digit graduation year in the database."""

    def __init__(
        self,
        grad_years: set[int],
        failure_description: Optional[str] = None,
    ) -> None:
        """Store the graduation years considered valid."""
        super().__init__(failure_description=failure_description)
        self.grad_years = grad_years

    def validate(self, value: str) -> validation.ValidationResult:
        """Check that the value is a four-digit year present in the database."""
        if len(value) != 4 or not value.isdigit():
            return self.failure("Must be a four-digit year.", value)
        if int(value) not in self.grad_years:
            return self.failure("Year not found in database.", value)
        return self.success()


class GradYearSelector(widgets.Input):
    """Input restricted to graduation years present in the database."""

    def __init__(
        self,
        dbase: model.DBase,
        value: Optional[str] = None,
        name: Optional[str] = None,
        id: Optional[str] = None,
        classes: Optional[str] = None,
        disabled: bool = False,
    ) -> None:
        """Populate the validator with graduation years from the database."""
        grad_years = set(model.Student.grad_years(dbase))
        super().__init__(
            value=value,
            placeholder="Grad Year",
            restrict=r"\d{0,4}",
            max_length=4,
            validators=[GradYearValidator(grad_years)],
            name=name,
            id=id,
            classes=classes,
            disabled=disabled,
        )


class AsOfValidator(validation.Validator):
    """Validate that a value is a real date in YYYY-MM-DD format."""

    _format_re = re.compile(r"\d{4}-\d{2}-\d{2}")

    def validate(self, value: str) -> validation.ValidationResult:
        """Check that the value is a real date in YYYY-MM-DD format."""
        if not self._format_re.fullmatch(value):
            return self.failure("Must be a date in YYYY-MM-DD format.", value)
        try:
            datetime.date.fromisoformat(value)
        except ValueError:
            return self.failure("Not a valid date.", value)
        return self.success()


class AsOfSelector(widgets.Input):
    """Input restricted to dates in ISO Format."""

    def __init__(
        self,
        value: Optional[str] = None,
        name: Optional[str] = None,
        id: Optional[str] = None,
        classes: Optional[str] = None,
        disabled: bool = False,
    ) -> None:
        """Restrict input to dates formatted as YYYY-MM-DD."""
        super().__init__(
            value=value,
            placeholder="YYYY-MM-DD",
            restrict=r"[\d-]{0,10}",
            max_length=10,
            validators=[AsOfValidator()],
            name=name,
            id=id,
            classes=classes,
            disabled=disabled,
        )
