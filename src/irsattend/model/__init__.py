"""The frcattend.model namespace."""

# ruff: noqa: F401
from irsattend.model.students import Student
from irsattend.model.events import Event, EventType, EventUpateError, Checkin
from irsattend.model.database import DBase, DBaseError