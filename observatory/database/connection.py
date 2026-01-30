"""Database connection handling."""

import aiosqlite
from pathlib import Path
from observatory.config import config

# Global database connection
_db: aiosqlite.Connection | None = None


async def get_db() -> aiosqlite.Connection:
    """Get the database connection, creating it if necessary."""
    global _db
    if _db is None:
        config.ensure_data_dir()
        _db = await aiosqlite.connect(config.DATABASE_PATH)
        _db.row_factory = aiosqlite.Row
        # Enable foreign keys
        await _db.execute("PRAGMA foreign_keys = ON")
    return _db


async def close_db() -> None:
    """Close the database connection."""
    global _db
    if _db is not None:
        await _db.close()
        _db = None


async def execute_query(query: str, params: tuple = ()) -> list[dict]:
    """Execute a query and return results as list of dicts."""
    db = await get_db()
    async with db.execute(query, params) as cursor:
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def execute_insert(query: str, params: tuple = ()) -> int:
    """Execute an insert and return the last row id."""
    db = await get_db()
    async with db.execute(query, params) as cursor:
        await db.commit()
        return cursor.lastrowid


async def execute_many(query: str, params_list: list[tuple]) -> None:
    """Execute many inserts."""
    db = await get_db()
    await db.executemany(query, params_list)
    await db.commit()
