"""Classes for verifying user enters valid input into Textual widgets."""

import datetime
import re

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


class TimeValidator(validation.Validator):
    """Validate a 24-hour time in HH:MM format."""

    FORMAT = "%H:%M"
    _format_re = re.compile(r"\d{2}:\d{2}")

    def validate(self, value: str) -> validation.ValidationResult:
        """Check the format and that the hour and minute are in range."""
        if not self._format_re.fullmatch(value):
            return self.failure("Must be in HH:MM format.", value)
        try:
            datetime.datetime.strptime(value, self.FORMAT)
        except ValueError:
            return self.failure("Not a valid time.", value)
        return self.success()


class IsPositiveInteger(validation.Validator):
    """Input value must be convertable to an integer."""

    def validate(self, value: str) -> validation.ValidationResult:
        """Input must be a postive integer."""
        if value and value.isdigit() and int(value) > 0:
            return self.success()
        return self.failure("Must be an integer greater than 0.")


class IsYear(validation.Validator):
    """Input value must be convertable to an integer."""

    def validate(self, value: str) -> validation.ValidationResult:
        """Input must be a 4-digit year between 1900 and 2100."""
        if value and value.isdigit() and 1900 < int(value) < 2100:
            return self.success()
        return self.failure("Must be a 4-digit year (e.g., 2028).")


class NotEmpty(validation.Validator):
    """Input widget can't be empty."""

    def validate(self, value: str) -> validation.ValidationResult:
        """Validate successfully if value is not an empty string."""
        if not value:
            return self.failure("Field cannot be empty.")
        return self.success()
