"""Data entry validator classes."""

import dateutil.parser

from textual import validation


class DateValidator(validation.Validator):
    """Validate user input."""

    def validate(self, value: str) -> validation.ValidationResult:
        """Verify input is a valid date."""
        try:
            dateutil.parser.parse(value, dayfirst=False).date()
            return self.success()
        except dateutil.parser.ParserError as err:
            return self.failure(str(err))
