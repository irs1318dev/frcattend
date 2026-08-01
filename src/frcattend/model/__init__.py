"""The frcattend.model namespace.

For convenience, import commonly-used model classes into the frcattend.model
namespace.

The frcattend.model.students import must occurr first to prevent circular
imports. Ignoring the I001 error prevents Ruff from resorting these imports.

Suppressing the F401 rule allows unused variables.
"""

# ruff: file-ignore[F401, I001]
from frcattend.model.students import (
    Reason,
    Stage,
    Status,
    StatusError,
    StatusErrorTypes,
    Student,
)
from frcattend.model.attendance import Attendance, AttendanceStudent
from frcattend.model.database import DBase, DBaseError
from frcattend.model.events_checkins import Checkin, Event, EventType, EventUpateError
from frcattend.model.surveys import Answer, Survey
