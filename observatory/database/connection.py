"""Database connection handling."""

import aiosqlite
from observatory.config import config


# Global write connection (shared by poller/writer)
_db: aiosqlite.Connection | None = None


async def get_db() -> aiosqlite.Connection:
    """Get the shared write connection, creating it if necessary."""
    global _db
    if _db is None:
        config.ensure_data_dir()
        _db = await aiosqlite.connect(config.DATABASE_PATH)
        _db.row_factory = aiosqlite.Row
        await _db.execute("PRAGMA foreign_keys = ON")
        await _db.execute("PRAGMA journal_mode = WAL")
        await _db.execute("PRAGMA synchronous = NORMAL")
        await _db.execute("PRAGMA cache_size = -64000")  # 64MB cache
        await _db.execute("PRAGMA temp_store = MEMORY")
        await _db.execute("PRAGMA mmap_size = 30000000")  # 30MB mmap
        await _db.execute("PRAGMA page_size = 4096")
    return _db


async def close_db() -> None:
    """Close the write connection."""
    global _db
    if _db is not None:
        await _db.close()
        _db = None


async def execute_query(query: str, params: tuple = ()) -> list[dict]:
    """Execute a read-only query using a short-lived read-only connection.

    Opens a separate connection so WAL-mode concurrent reads are never
    blocked by an in-progress write transaction on the shared write connection.
    """
    db_uri = f"file:{config.DATABASE_PATH}?mode=ro"
    async with aiosqlite.connect(db_uri, uri=True) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA journal_mode = WAL")
        await db.execute("PRAGMA cache_size = -16000")  # 16MB cache
        await db.execute("PRAGMA temp_store = MEMORY")
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
