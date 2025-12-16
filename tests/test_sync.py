"""Test synchronization between local app and Google workbook."""
import rich

from frcattend import config, model
from frcattend.features import synchronizer


def test_connect_to_sheet(settings: config.Settings, full_dbase: model.DBase) -> None:
    """Get all data as a dictionary."""
    # Act
    synker = synchronizer.Synchronizer()
    # Assert
    assert isinstance(synker, synchronizer.Synchronizer)


def test_write_surveys(settings: config.Settings, full_dbase: model.DBase) -> None:
    """Write the surveys table to the synchro sheet."""
    # Arrange
    synker = synchronizer.Synchronizer()
    data = full_dbase.to_dict()
    # Act
    num_rows = synker.write_table_to_sheet("surveys", data["surveys"])
    assert num_rows > 0


def test_write_db(settings: config.Settings, full_dbase: model.DBase) -> None:
    """Write the surveys table to the synchro sheet."""
    # Arrange
    synker = synchronizer.Synchronizer()
    data = full_dbase.to_dict()
    # Act
    write_result = synker.write_db_to_workbook(data)
    rich.print(write_result)
    