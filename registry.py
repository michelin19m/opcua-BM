import aiosqlite
from typing import Optional
from pydantic import BaseModel, field_validator
from config import REGISTRY_DB, MIN_POLL_MS

VALID_TYPES = {"Float", "Int32", "Boolean", "String", "FloatArray"}


class Tag(BaseModel):
    id: Optional[int] = None
    name: str
    sql_query: str
    poll_interval_ms: int = 1000
    enabled: bool = True
    data_type: str = "Float"

    @field_validator("poll_interval_ms")
    @classmethod
    def clamp_interval(cls, v: int) -> int:
        return max(v, MIN_POLL_MS)

    @field_validator("data_type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        if v not in VALID_TYPES:
            raise ValueError(f"data_type must be one of {VALID_TYPES}")
        return v


async def init_db() -> None:
    async with aiosqlite.connect(REGISTRY_DB) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tags (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                name             TEXT    NOT NULL UNIQUE,
                sql_query        TEXT    NOT NULL,
                poll_interval_ms INTEGER NOT NULL DEFAULT 1000,
                enabled          INTEGER NOT NULL DEFAULT 1,
                data_type        TEXT    NOT NULL DEFAULT 'Float'
            )
        """)
        await db.commit()


async def _rows(db, sql, params=()):
    db.row_factory = aiosqlite.Row
    async with db.execute(sql, params) as cur:
        return [dict(r) for r in await cur.fetchall()]


async def get_all_tags() -> list[dict]:
    async with aiosqlite.connect(REGISTRY_DB) as db:
        return await _rows(db, "SELECT * FROM tags ORDER BY id")


async def get_enabled_tags() -> list[dict]:
    async with aiosqlite.connect(REGISTRY_DB) as db:
        return await _rows(db, "SELECT * FROM tags WHERE enabled=1")


async def get_tag_by_id(tag_id: int) -> Optional[dict]:
    async with aiosqlite.connect(REGISTRY_DB) as db:
        rows = await _rows(db, "SELECT * FROM tags WHERE id=?", (tag_id,))
        return rows[0] if rows else None


async def add_tag(tag: Tag) -> dict:
    async with aiosqlite.connect(REGISTRY_DB) as db:
        cur = await db.execute(
            "INSERT INTO tags (name, sql_query, poll_interval_ms, enabled, data_type)"
            " VALUES (?,?,?,?,?)",
            (tag.name, tag.sql_query, tag.poll_interval_ms, int(tag.enabled), tag.data_type),
        )
        await db.commit()
        rows = await _rows(db, "SELECT * FROM tags WHERE id=?", (cur.lastrowid,))
        return rows[0]


async def update_tag(tag_id: int, tag: Tag) -> None:
    async with aiosqlite.connect(REGISTRY_DB) as db:
        await db.execute(
            "UPDATE tags SET name=?, sql_query=?, poll_interval_ms=?, enabled=?, data_type=?"
            " WHERE id=?",
            (tag.name, tag.sql_query, tag.poll_interval_ms, int(tag.enabled), tag.data_type, tag_id),
        )
        await db.commit()


async def set_enabled(tag_id: int, enabled: bool) -> None:
    async with aiosqlite.connect(REGISTRY_DB) as db:
        await db.execute("UPDATE tags SET enabled=? WHERE id=?", (int(enabled), tag_id))
        await db.commit()


async def delete_tag(tag_id: int) -> None:
    async with aiosqlite.connect(REGISTRY_DB) as db:
        await db.execute("DELETE FROM tags WHERE id=?", (tag_id,))
        await db.commit()


# ── Seed demo tags on first run ───────────────────────────────────────────────
DEMO_TAGS = [
    Tag(name="Temperature_1",   sql_query="SELECT value FROM sensors WHERE tag='TEMP1'",   data_type="Float",      poll_interval_ms=1000),
    Tag(name="Pressure_Main",   sql_query="SELECT value FROM sensors WHERE tag='PRESS1'",  data_type="Float",      poll_interval_ms=1000),
    Tag(name="Pump_Running",    sql_query="SELECT running FROM equipment WHERE id=1",       data_type="Boolean",    poll_interval_ms=2000),
    Tag(name="Batch_Count",     sql_query="SELECT COUNT(*) FROM batches WHERE date=CAST(GETDATE() AS DATE)", data_type="Int32", poll_interval_ms=5000),
    Tag(name="Vibration_Array", sql_query="SELECT v1,v2,v3,v4,v5 FROM vibration WHERE id=1", data_type="FloatArray", poll_interval_ms=500),
    Tag(name="Machine_Status",  sql_query="SELECT status FROM machines WHERE id=1",         data_type="String",     poll_interval_ms=2000),
]


async def seed_demo_tags() -> None:
    """Insert demo tags only if the table is empty."""
    async with aiosqlite.connect(REGISTRY_DB) as db:
        async with db.execute("SELECT COUNT(*) FROM tags") as cur:
            count = (await cur.fetchone())[0]
    if count == 0:
        for t in DEMO_TAGS:
            await add_tag(t)
