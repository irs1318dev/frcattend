"""Test synchronization between local app and Google workbook."""

import datetime

import pytest
import rich  # noqa: F401

from frcattend import model
from frcattend.features import sync

# pytestmark = pytest.mark.skip(
#     reason="Prevent exceeding Google sheet rate limits. Run tests one at a time."
# )


def test_connect_to_sheet(empty_database: model.DBase) -> None:
    """Get all data as a dictionary."""
    # Act
    synker = sync.Synchronizer()
    # Assert
    assert isinstance(synker, sync.Synchronizer)


def test_local_metadata(full_synchro: sync.Synchronizer) -> None:
    """Generate metadata that describes database contents."""
    # Act
    metadata = full_synchro._get_local_metadata()
    # Assert
    for fieldname in ["update_time", "user", "computer_name", "db_hash"]:
        assert isinstance(metadata[fieldname], str)
    assert isinstance(metadata["table_hashes"], str)
    assert len(metadata["table_hashes"]) == 6


def test_remote_metadata(full_synchro: sync.Synchronizer) -> None:
    """Read metadata from remote Google sheet."""
    # Act
    metadata = full_synchro._get_remote_metadata()
    # Assert
    for fieldname in ["update-time", "user", "computer-name", "db-hash"]:
        assert isinstance(metadata[fieldname], str)
    assert isinstance(metadata["table-hashes"], dict)
    for tdata in metadata["table-hashes"].values():
        assert isinstance(tdata["hash"], str)
        assert isinstance(tdata["max-id"], int)
        assert isinstance(tdata["max-row"], int)
    assert len(metadata["table-hashes"]) == 6


def test_write_surveys(
    empty_synchro: sync.Synchronizer, full_dbase: model.DBase
) -> None:
    """Write the surveys table to the synchro sheet."""
    # Arrange
    data = full_dbase.to_dict()
    # Act
    num_rows = empty_synchro.write_entire_table_to_sheet("surveys", data["surveys"])
    assert num_rows > 0


def test_write_db(empty_synchro: sync.Synchronizer, full_dbase: model.DBase) -> None:
    """Write all database data table to the synchro sheet."""
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


def test_append_checkins(full_synchro: sync.Synchronizer) -> None:
    """Append records to the checkins Google sheet."""
    # Arrange
    new_event = model.Event(
        datetime.date(2026, 12, 25),
        model.EventType.MEETING,
        "test-append-checkins"
    )
    new_event.add(full_synchro.dbase)
    student_ids = model.Student.get_all_ids(full_synchro.dbase)
    for min_delta, sid in enumerate(student_ids[:5]):
        checkin = model.Checkin(
            -1,
            sid,
            model.EventType.MEETING,
            datetime.datetime(2026, 12, 25, 17, 30 + min_delta),
        )
        checkin.add(full_synchro.dbase)
    # Act
    full_synchro.upload(upload_all=False)

