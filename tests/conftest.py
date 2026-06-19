"""Pytest fixtures."""

import argparse
import json
import pathlib
import shutil
from typing import Any

import pytest

from frcattend import config, model
from frcattend.features import sync


TEST_FOLDER = pathlib.Path(__file__).parent
DATA_FOLDER = TEST_FOLDER / "data"
PRIVATE_FOLDER = DATA_FOLDER / "private"
OUTPUT_FOLDER = TEST_FOLDER / "output"
CONFIG_PATH = PRIVATE_FOLDER / "test-config.toml"


@pytest.fixture()
def empty_output_folder() -> pathlib.Path:
    """Create an empty output folder prior to each test."""
    if OUTPUT_FOLDER.exists():
        for item in OUTPUT_FOLDER.iterdir():
            if item.is_dir():
                shutil.rmtree(item, ignore_errors=True)
            else:
                item.unlink()
    else:
        OUTPUT_FOLDER.mkdir(parents=True)
    return OUTPUT_FOLDER


@pytest.fixture()
def settings() -> config.Settings:
    """Get default settings for tests."""
    args = argparse.Namespace(
        db_path=None,
        config_path=CONFIG_PATH,
    )
    config.settings.update_from_args(args)
    return config.settings


@pytest.fixture
def empty_database(
    empty_output_folder: pathlib.Path, settings: config.Settings
) -> model.DBase:
    """An empty IrsAttend database, with tables created."""
    settings.db_path = OUTPUT_FOLDER / "testdatabase.db"
    return model.DBase(settings.db_path, create_new=True)


@pytest.fixture
def empty_database2(
    empty_output_folder: pathlib.Path, settings: config.Settings
) -> model.DBase:
    """An empty IrsAttend database, with tables created.
    
    Some tests require two different database files. Use this fixture
    and the empty_database fixture to create two different database files.
    """
    settings.db_path = OUTPUT_FOLDER / "testdatabase2.db"
    return model.DBase(settings.db_path, create_new=True)


@pytest.fixture
def attendance_test_data() -> dict[str, list[Any]]:
    """Get test data as a dictionary."""
    with open(DATA_FOLDER / "testdata.json") as jfile:
        test_data = json.load(jfile)
    return test_data


@pytest.fixture
def full_dbase(
    empty_database: model.DBase,
    attendance_test_data: dict[str, list[Any]]
) -> model.DBase:
    """Database with students, statuses, appearances, and events."""
    empty_database.load_from_dict(attendance_test_data)
    return empty_database


@pytest.fixture
def noevents_dbase(empty_database: model.DBase) -> model.DBase:
    """Database with students."""
    with open(DATA_FOLDER / "testdata.json") as jfile:
        attendance_data = json.load(jfile)
    attendance_data["events"] = []
    attendance_data["checkins"] = []
    empty_database.load_from_dict(attendance_data)
    return empty_database


@pytest.fixture
def empty_synchro(
    settings: config.Settings, full_dbase: model.DBase
) -> sync.Synchronizer:
    """A Synchronizer that points to an empty spreadsheet."""
    synchro = sync.Synchronizer()
    synchro.clear_all_sheets()
    return synchro


@pytest.fixture
def full_synchro(
    empty_synchro: sync.Synchronizer,
    attendance_test_data: dict[str, list[Any]]
) -> sync.Synchronizer:
    """A synchronizer that points to a full spreadsheet."""
    # data = full_dbase.to_dict()
    empty_synchro.write_data_to_workbook(attendance_test_data)
    return empty_synchro
