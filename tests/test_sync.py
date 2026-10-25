"""Test synchronization between local app and Google workbook."""

import asyncio
import datetime
import pathlib
import shutil
from typing import Any

import pytest
import rich  # noqa: F401
from textual import app, widgets

from frcattend import config, model
from frcattend.features import sync
from frcattend.view import sync_dialogs


class FakeS3Client:
    """Stand-in for a boto3 S3 client that uses local files."""

    def __init__(self, source_path: pathlib.Path) -> None:
        """Specify the file that will be downloaded."""
        self.source_path = source_path
        self.uploads: dict[str, bytes] = {}

    def download_file(self, bucket: str, key: str, filename: str) -> None:
        """Copy the source file to the destination."""
        shutil.copy(self.source_path, filename)

    def upload_file(self, filename: str, bucket: str, key: str) -> None:
        """Save the uploaded file's contents under its key."""
        self.uploads[key] = pathlib.Path(filename).read_bytes()

    def list_objects_v2(
        self, Bucket: str, Prefix: str, MaxKeys: int = 1000
    ) -> dict[str, Any]:
        """List uploaded keys that start with the prefix."""
        keys = [key for key in sorted(self.uploads) if key.startswith(Prefix)]
        return {"Contents": [{"Key": key} for key in keys[:MaxKeys]]}


def test_parse_db_object_key() -> None:
    """Parse checkin_id and timestamp from object keys."""
    obj = sync.DbObject.from_key("frcattend-42-2026_10_25_13_05_09.db")
    assert obj is not None
    assert obj.checkin_id == 42
    assert obj.timestamp == datetime.datetime(2026, 10, 25, 13, 5, 9)
    assert sync.DbObject.from_key("frcattend-42.db") is None
    assert sync.DbObject.from_key("frcattend-4-2026_13_25_13_05_09.db") is None


def test_default_db_object() -> None:
    """Default file has both the largest checkin_id and latest timestamp."""
    objects = sync.get_db_objects(
        [
            "frcattend-10-2026_10_01_00_00_00.db",
            "frcattend-30-2026_10_03_00_00_00.db",
            "not-a-database.txt",
            "frcattend-20-2026_10_02_00_00_00.db",
        ]
    )
    assert [obj.checkin_id for obj in objects] == [30, 20, 10]
    default = sync.get_default_db_object(objects)
    assert default is not None
    assert default.key == "frcattend-30-2026_10_03_00_00_00.db"


def test_default_db_object_conflict() -> None:
    """No default if largest checkin_id and latest timestamp are different files."""
    objects = sync.get_db_objects(
        [
            "frcattend-30-2026_10_01_00_00_00.db",
            "frcattend-20-2026_10_02_00_00_00.db",
        ]
    )
    assert sync.get_default_db_object(objects) is None
    assert sync.get_default_db_object([]) is None


@pytest.mark.parametrize(
    ("keys", "expected"),
    [
        (
            [
                "frcattend-10-2026_10_01_00_00_00.db",
                "frcattend-30-2026_10_03_00_00_00.db",
            ],
            "frcattend-30-2026_10_03_00_00_00.db",
        ),
        (
            [
                "frcattend-30-2026_10_01_00_00_00.db",
                "frcattend-20-2026_10_02_00_00_00.db",
            ],
            None,
        ),
    ],
)
def test_download_choose_file_dialog(keys: list[str], expected: str | None) -> None:
    """Pressing OK downloads the default file, unless the user must choose."""
    results: list[str | None] = []

    class DialogApp(app.App):
        def on_mount(self) -> None:
            self.push_screen(
                sync_dialogs.DownloadChooseFileDialog(keys), results.append
            )

    async def run_dialog() -> None:
        dialog_app = DialogApp()
        async with dialog_app.run_test() as pilot:
            ok_button = dialog_app.screen.query_one(
                "#download-choose-ok", widgets.Button
            )
            assert ok_button.disabled == (expected is None)
            if expected is None:
                # User must choose a file before pressing OK.
                dialog_app.screen.query(widgets.RadioButton).last().value = True
                await pilot.pause()
                assert not ok_button.disabled
            await pilot.click("#download-choose-ok")
            await pilot.pause()

    asyncio.run(run_dialog())
    assert results == [expected or keys[-1]]


def test_download(
    full_dbase: model.DBase,
    empty_database2: model.DBase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Back up the current database and replace it with the download."""
    # Arrange
    monkeypatch.setattr(config.settings, "backup_dir", None)
    current_path = empty_database2.db_path
    monkeypatch.setattr(
        sync.Synchronizer,
        "_get_s3_client",
        staticmethod(lambda: FakeS3Client(full_dbase.db_path)),
    )
    synchro = sync.Synchronizer()
    # Act
    backup_path = synchro.download("frcattend-1-2026_10_25_00_00_00.db")
    # Assert
    assert backup_path.parent == current_path.parent
    assert backup_path.name.startswith("testdatabase2-backup-")
    assert model.DBase(backup_path).get_record_counts()["checkins"] == 0
    counts = model.DBase(current_path).get_record_counts()
    assert counts == full_dbase.get_record_counts()
    assert not current_path.with_name(current_path.name + ".downloading").exists()


def test_download_invalid_file(
    empty_database: model.DBase, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Current database is not changed if downloaded file is invalid."""
    # Arrange
    monkeypatch.setattr(config.settings, "backup_dir", None)
    bad_path = empty_database.db_path.with_name("bad.db")
    bad_path.write_bytes(b"not a database")
    original = empty_database.db_path.read_bytes()
    monkeypatch.setattr(
        sync.Synchronizer,
        "_get_s3_client",
        staticmethod(lambda: FakeS3Client(bad_path)),
    )
    synchro = sync.Synchronizer()
    # Act / Assert
    with pytest.raises(model.DBaseError):
        synchro.download("frcattend-1-2026_10_25_00_00_00.db")
    assert empty_database.db_path.read_bytes() == original


def test_synchronizer_requires_db_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """Synchronizer raises an error if the db_path setting is missing."""
    # Arrange
    monkeypatch.setattr(config.settings, "db_path", None)
    # Act / Assert
    with pytest.raises(config.ConfigError) as excinfo:
        sync.Synchronizer()
    assert excinfo.value.error_type == config.ConfigError.ErrorType.UNDEFINED_SETTING


def test_upload(full_dbase: model.DBase, monkeypatch: pytest.MonkeyPatch) -> None:
    """Upload a copy of the database, named with max checkin_id and mtime."""
    # Arrange
    model.Event(
        datetime.date(2026, 12, 25), model.EventType.MEETING, "test-upload"
    ).add(full_dbase)
    student_id = model.Student.get_all_ids(full_dbase)[0]
    checkin_id = model.Checkin(
        -1,
        student_id,
        model.EventType.MEETING,
        datetime.datetime(2026, 12, 25, 17, 30),
    ).add(full_dbase)
    modified = datetime.datetime.fromtimestamp(full_dbase.db_path.stat().st_mtime)
    expected_key = f"frcattend-{checkin_id}-{modified.strftime('%Y_%m_%d_%H_%M_%S')}.db"
    client = FakeS3Client(full_dbase.db_path)
    monkeypatch.setattr(
        sync.Synchronizer, "_get_s3_client", staticmethod(lambda: client)
    )
    synchro = sync.Synchronizer()
    # Act
    object_key = synchro.upload()
    # Assert
    assert object_key == expected_key
    uploaded_path = full_dbase.db_path.with_name("uploaded.db")
    uploaded_path.write_bytes(client.uploads[object_key])
    counts = model.DBase(uploaded_path).get_record_counts()
    assert counts == full_dbase.get_record_counts()


def test_upload_duplicate(
    full_dbase: model.DBase, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Uploading the same file twice is refused unless forced."""
    # Arrange
    client = FakeS3Client(full_dbase.db_path)
    monkeypatch.setattr(
        sync.Synchronizer, "_get_s3_client", staticmethod(lambda: client)
    )
    synchro = sync.Synchronizer()
    object_key = synchro.upload()
    # Act / Assert
    with pytest.raises(sync.SynchronizerError) as excinfo:
        synchro.upload()
    assert excinfo.value.error_type == sync.SynchronizerError.ErrorType.DUPLICATE_UPLOAD
    assert synchro.upload(force=True) == object_key
