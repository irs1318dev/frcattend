"""Pytest fixtures."""

import argparse
import json
import pathlib
import shutil

import pytest

from irsattend import config, model


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
def settings(full_dbase: model.DBase) -> config.Settings:
    """Get default settings for tests."""
    args = argparse.Namespace(
        db_path=full_dbase.db_path,
        config_path=CONFIG_PATH,
    )
    config.settings.update_from_args(args)
    return config.settings


@pytest.fixture
def empty_database(empty_output_folder: pathlib.Path) -> model.DBase:
    """An empty IrsAttend database, with tables created."""
    return model.DBase(OUTPUT_FOLDER / "testdatabase.db", create_new=True)


@pytest.fixture
def full_dbase(empty_database: model.DBase) -> model.DBase:
    """Database with students, appearances, and events."""
    with open(DATA_FOLDER / "testdata-full.json") as jfile:
        attendance_data = json.load(jfile)
    empty_database.load_from_dict(attendance_data)
    return empty_database


@pytest.fixture
def noevents_dbase(empty_database: model.DBase) -> model.DBase:
    """Database with students."""
    with open(DATA_FOLDER / "testdata-full.json") as jfile:
        attendance_data = json.load(jfile)
    attendance_data["events"] = []
    attendance_data["checkins"] = []
    empty_database.load_from_dict(attendance_data)
    return empty_database


@pytest.fixture
def empty_database2(empty_output_folder: pathlib.Path) -> model.DBase:
    """An empty IrsAttend database, with tables created."""
    return model.DBase(OUTPUT_FOLDER / "testdatabase2.db", create_new=True)


@pytest.fixture
def attendance_test_data() -> dict[str, list]:
    """Get test data as a dictionary.

    Dictionary has three keys: students, attendance, and events, where each
    key is a list of dictionaries.
    """
    with open(DATA_FOLDER / "testdata-full.json") as jfile:
        test_data = json.load(jfile)
    return test_data
