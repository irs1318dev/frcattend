"""Test Excel file functionality."""

import pathlib

from frcattend.features import excel
from frcattend.model import database


OUTPUT_PATH = pathlib.Path(__file__).parent / "output"


def test_write_excel(full_dbase: database.DBase) -> None:
    """Write contents of database to an Excel file."""
    # Act
    excel.write(full_dbase, OUTPUT_PATH / "excel-export.xlsx")
