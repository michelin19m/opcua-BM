"""
Polling engine
──────────────
• Groups enabled tags by poll_interval_ms → one asyncio Task per group.
• Each Task opens its own pyodbc connection (run in a thread pool via
  asyncio.to_thread so the event loop is never blocked).
• Results go into an in-memory Cache, then immediately forwarded to
  the OPC UA server node.
• DEMO_MODE skips SQL entirely and produces random values.
"""

import asyncio
import logging
import random
from datetime import datetime, timezone
from typing import Any, Optional

from config import DEMO_MODE, SQL_SERVER_CONN

log = logging.getLogger(__name__)


# ── Cache ─────────────────────────────────────────────────────────────────────

class Cache:
    def __init__(self):
        self._data: dict[str, dict] = {}

    def update(self, name: str, value: Any, error: Optional[str] = None) -> None:
        self._data[name] = {
            "value":     value,
            "error":     error,
            "quality":   "Good" if error is None else "Bad",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def get(self, name: str) -> Optional[dict]:
        return self._data.get(name)

    def snapshot(self) -> dict:
        return dict(self._data)


# ── Polling engine ────────────────────────────────────────────────────────────

class PollingEngine:
    def __init__(self):
        self.cache   = Cache()
        self._opc    = None          # injected after OPC server is created
        self._tasks: dict[int, asyncio.Task] = {}
        self._running = False

    # ── Wiring ────────────────────────────────────────────────────────────────

    def set_opc_server(self, opc) -> None:
        self._opc = opc

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        self._running = True
        await self._spawn_tasks()

    def stop(self) -> None:
        self._running = False
        self._cancel_all()

    async def reload(self) -> None:
        """Call whenever the tag registry changes."""
        self._cancel_all()
        if self._running:
            await self._spawn_tasks()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _cancel_all(self) -> None:
        for task in self._tasks.values():
            task.cancel()
        self._tasks.clear()

    async def _spawn_tasks(self) -> None:
        from registry import get_enabled_tags

        tags = await get_enabled_tags()
        groups: dict[int, list] = {}
        for tag in tags:
            groups.setdefault(tag["poll_interval_ms"], []).append(tag)

        for interval_ms, group in groups.items():
            t = asyncio.create_task(self._poll_loop(interval_ms, group))
            self._tasks[interval_ms] = t

    async def _poll_loop(self, interval_ms: int, tags: list) -> None:
        interval_s = interval_ms / 1000
        try:
            while True:
                results = (
                    await self._poll_demo(tags)
                    if DEMO_MODE
                    else await asyncio.to_thread(self._poll_sql, tags)
                )
                for tag in tags:
                    r = results.get(tag["name"], {})
                    value = r.get("value")
                    error = r.get("error")
                    coerced = self._coerce(value, tag["data_type"])
                    self.cache.update(tag["name"], coerced, error)
                    if self._opc:
                        await self._opc.update_node(tag["name"], coerced)
                await asyncio.sleep(interval_s)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            log.error("Poll loop crashed (interval=%dms): %s", interval_ms, e)

    # ── SQL (runs in thread pool) ──────────────────────────────────────────────

    @staticmethod
    def _poll_sql(tags: list) -> dict:
        import pyodbc
        results: dict[str, dict] = {}
        try:
            conn = pyodbc.connect(SQL_SERVER_CONN, timeout=5)
            cursor = conn.cursor()
            cursor.execute("SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED")
            for tag in tags:
                try:
                    cursor.execute(tag["sql_query"])
                    rows = cursor.fetchall()
                    if not rows:
                        results[tag["name"]] = {"value": None, "error": "No rows returned"}
                    elif tag["data_type"] == "FloatArray":
                        # Multiple columns on a single row → array
                        results[tag["name"]] = {"value": list(rows[0]), "error": None}
                    else:
                        results[tag["name"]] = {"value": rows[0][0], "error": None}
                except Exception as e:
                    results[tag["name"]] = {"value": None, "error": str(e)}
            conn.close()
        except Exception as e:
            for tag in tags:
                results[tag["name"]] = {"value": None, "error": f"DB error: {e}"}
        return results

    # ── Demo (random values) ──────────────────────────────────────────────────

    @staticmethod
    async def _poll_demo(tags: list) -> dict:
        results: dict[str, dict] = {}
        for tag in tags:
            dt = tag["data_type"]
            if dt == "Float":
                val = round(random.gauss(50, 10), 2)
            elif dt == "Int32":
                val = random.randint(0, 500)
            elif dt == "Boolean":
                val = random.random() > 0.3
            elif dt == "FloatArray":
                val = [round(random.gauss(50, 5), 2) for _ in range(5)]
            else:
                val = random.choice(["RUNNING", "IDLE", "FAULT"])
            results[tag["name"]] = {"value": val, "error": None}
        await asyncio.sleep(0)  # yield to event loop
        return results

    # ── Type coercion ─────────────────────────────────────────────────────────

    @staticmethod
    def _coerce(value: Any, data_type: str) -> Any:
        if value is None:
            return None
        try:
            if data_type == "Float":
                return float(value)
            if data_type == "Int32":
                return int(value)
            if data_type == "Boolean":
                if isinstance(value, str):
                    return value.strip().lower() in ("1", "true", "yes", "on")
                return bool(value)
            if data_type == "FloatArray":
                if isinstance(value, (list, tuple)):
                    return [float(v) for v in value]
                return [float(value)]
            return str(value)       # String fallback
        except (TypeError, ValueError):
            return None
