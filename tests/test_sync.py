"""Test synchronization between local app and Google workbook."""
import rich

from frcattend import config, model
from frcattend.features import synchronizer


def test_getdict(settings: config.Settings, full_dbase: model.DBase) -> None:
    """Get all data as a dictionary."""
    synker = synchronizer.Synchronizer()
    rich.print(full_dbase.to_dict()["answers"])
    