"""An attendance summary report in markdown format."""

from frcattend import model


def get_summary(dbase: model.DBase) -> str:
    """Get attendance summary report in markdown."""