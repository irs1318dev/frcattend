"""An attendance summary report in markdown format."""


from frcattend import config, model


def get_summary() -> str:
    """Get attendance summary report in markdown."""
    if config.settings.db_path is None:
        return ""
    dbase = model.DBase(config.settings.db_path)
    db_info = dbase.get_database_file_info()
    accessed_on = db_info.access_time.replace(microsecond=0).isoformat()
    modified_on = db_info.modification_time.replace(microsecond=0).isoformat()
    created_on = db_info.creation_time.replace(microsecond=0).isoformat()
    summary = [
        "# File Info",
        "| File | Last Accessed | Last Modified | Created On |",
        "| ---- | ------------- | ------------- | ---------- |",
        f"| {dbase.db_path.name} | {accessed_on} | {modified_on} | {created_on} |",
    ]
    return str("\n".join(summary))


# test_database.py os.stat_result(
# st_mode=33206, st_ino=32088147345585846,
# st_dev=1740870934334587460, st_nlink=1, st_uid=0, st_gid=0,
# st_size=57344, st_atime=1764601495, st_mtime=1764601495, st_ctime=1764545906)
# Sizes are in bytes, times in posix time. Use fromtimestamp datetime methods to
# convert.
# atime: access
# mtime: modification
# st_birthtime: file creation time.
