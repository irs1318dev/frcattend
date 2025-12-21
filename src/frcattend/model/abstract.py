"""Abstact base class that represets a table.

Table dataclasses defined in other modules should inherit from TableDef.
"""

import abc
import sqlite3
from typing import ClassVar, TYPE_CHECKING

if TYPE_CHECKING:
    from frcattend.model import database


# TODO: Implement table_name as a classmethod property that automatically
#   retrieves the table name from the CREATE TABLE statement using regex
#   or sqlparse package.


class TableDef(abc.ABC):
    """A class that represents a database table."""

    table_name: ClassVar[str]
    """The SQL name of the table."""
    table_def: ClassVar[str]
    """The CREATE TABLE SQL statement that creates the table."""

    @classmethod
    def create(cls, conn: sqlite3.Connection) -> None:
        """Create the table and other associated items (views, indexes, etc.)."""
        conn.execute(cls.table_def)

    @classmethod
    def delete_all(cls, conn: sqlite3.Connection) -> None:
        """Delete all data in the table."""
        with conn:
            conn.execute(f"DELETE FROM {cls.table_name}")

    @classmethod
    def count(cls, dbase: "database.DBase") -> int:
        """Get number of records in table."""
        query = f"SELECT COUNT(*) FROM {cls.table_name};"
        conn = dbase.get_db_connection()
        row_count = conn.execute(query).fetchone()[0]
        conn.close()
        return row_count

    @classmethod
    def get_nongenerated_columns(cls, dbase: "database.DBase") -> list[str]:
        """Get list of non-generated columns used when importing and exporting."""
        query = f"PRAGMA table_info({cls.table_name});"
        conn = dbase.get_db_connection(as_dict=True)
        columns = [col["name"] for col in conn.execute(query)]
        conn.close()
        return columns
