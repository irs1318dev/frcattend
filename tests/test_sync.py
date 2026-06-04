"""Test synchronization between local app and Google workbook."""

import pytest  # noqa: F401
import rich  # noqa: F401

from frcattend import model
from frcattend.features import sync


pytestmark = pytest.mark.skip(
    reason="Prevent exceeding Google sheet rate limits. Run tests one at a time."
)


def test_connect_to_sheet(empty_database: model.DBase) -> None:
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
    write_result = empty_synchro.write_data_to_workbook(data)
    assert isinstance(write_result, dict)


def test_read_db(full_synchro: sync.Synchronizer, empty_database2: model.DBase) -> None:
    """Read data from the synchro sheet."""
    # Act
    wb_data = full_synchro.download()
    empty_database2.load_from_dict(wb_data)
    # Assert
    db_data = empty_database2.to_dict()
    for table_name, min_len in [
        ("students", 100),
        ("events", 50),
        ("checkins", 4000),
        ("surveys", 2),
        ("answers", 2),
    ]:
        assert len(db_data[table_name]) > min_len
