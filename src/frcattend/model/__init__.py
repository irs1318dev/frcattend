"""The frcattend.model namespace."""

# ruff: noqa: F401
from frcattend.model.students import Student
from frcattend.model.events_checkins import Event, EventType, EventUpateError, Checkin
from frcattend.model.database import DBase, DBaseError
from frcattend.model.attendance import Attendance, AttendanceStudent
