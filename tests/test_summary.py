"""Test miscelaneous features."""

import rich  # noqa: F401

from frcattend import model
from frcattend.features import summary

def test_summary(full_dbase: model.DBase) -> None:
    """Generate an attendance and database summary."""
    # Act
    print()
    rich.print(summary.get_summary(full_dbase))

