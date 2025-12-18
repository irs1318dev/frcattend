"""Test synchronization between local app and Google workbook."""

import pytest
import rich  # noqa: F401

from frcattend import config, model
from frcattend.features import sync


pytestmark = pytest.mark.skip(
    reason="Prevent exceeding Google sheet rate limits. Run tests one at a time."
)


def test_connect_to_sheet(settings: config.Settings) -> None:
    """Get all data as a dictionary."""
    # Act
    synker = sync.Synchronizer()
    # Assert
    assert isinstance(synker, sync.Synchronizer)


def test_write_surveys(
    empty_synchro: sync.Synchronizer, full_dbase: model.DBase
) -> None:
    """Write the surveys table to the synchro sheet."""
    # Arrange
    data = full_dbase.to_dict()
    # Act
    num_rows = empty_synchro.write_table_to_sheet("surveys", data["surveys"])
    assert num_rows > 0


def test_write_db(empty_synchro: sync.Synchronizer, full_dbase: model.DBase) -> None:
    """Write the surveys table to the synchro sheet."""
    # Arrange
    data = full_dbase.to_dict()
    # Act
    write_result = empty_synchro.write_db_to_workbook(data)
    assert isinstance(write_result, dict)
