"""
OPC UA SQL Bridge — FastAPI entry point
Run with:  uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config import DEMO_MODE
from engine import PollingEngine
from opc import OPCServer
from registry import (
    Tag, init_db, seed_demo_tags,
    get_all_tags, get_tag_by_id,
    add_tag, update_tag, set_enabled, delete_tag,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger(__name__)

# ── Singletons ────────────────────────────────────────────────────────────────
engine = PollingEngine()
opc    = OPCServer()


# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    if DEMO_MODE:
        await seed_demo_tags()

    engine.set_opc_server(opc)

    # Start OPC UA server first, then polling engine
    opc_task    = asyncio.create_task(opc.start())
    engine_task = asyncio.create_task(engine.start())

    yield

    engine.stop()
    await opc.stop()
    opc_task.cancel()
    engine_task.cancel()


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="OPC UA SQL Bridge", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── REST API ──────────────────────────────────────────────────────────────────

@app.get("/api/status")
async def status():
    tags    = await get_all_tags()
    enabled = [t for t in tags if t["enabled"]]
    cache   = engine.cache.snapshot()
    good    = sum(1 for v in cache.values() if v.get("quality") == "Good")
    return {
        "demo_mode":    DEMO_MODE,
        "opc_endpoint": opc.endpoint,
        "opc_nodes":    opc.node_count,
        "total_tags":   len(tags),
        "enabled_tags": len(enabled),
        "good_quality": good,
    }


@app.get("/api/tags")
async def list_tags():
    """Return all tags enriched with their latest cached value."""
    tags  = await get_all_tags()
    cache = engine.cache.snapshot()
    for tag in tags:
        entry = cache.get(tag["name"]) or {}
        tag["current_value"] = entry.get("value")
        tag["quality"]       = entry.get("quality", "Pending")
        tag["timestamp"]     = entry.get("timestamp")
        tag["error"]         = entry.get("error")
    return tags


@app.post("/api/tags", status_code=201)
async def create_tag(tag: Tag):
    try:
        result = await add_tag(tag)
    except Exception as e:
        raise HTTPException(400, detail=str(e))
    await opc.add_node(result)
    await engine.reload()
    return result


@app.put("/api/tags/{tag_id}")
async def edit_tag(tag_id: int, tag: Tag):
    if not await get_tag_by_id(tag_id):
        raise HTTPException(404, "Tag not found")
    await update_tag(tag_id, tag)
    await engine.reload()
    return {"ok": True}


@app.patch("/api/tags/{tag_id}/enabled")
async def toggle_tag(tag_id: int, enabled: bool):
    if not await get_tag_by_id(tag_id):
        raise HTTPException(404, "Tag not found")
    await set_enabled(tag_id, enabled)
    await engine.reload()
    return {"ok": True}


@app.delete("/api/tags/{tag_id}")
async def remove_tag(tag_id: int):
    tag = await get_tag_by_id(tag_id)
    if not tag:
        raise HTTPException(404, "Tag not found")
    await opc.remove_node(tag["name"])
    await delete_tag(tag_id)
    await engine.reload()
    return {"ok": True}


@app.get("/api/cache")
async def cache_snapshot():
    return engine.cache.snapshot()


# ── Static frontend (must be last) ────────────────────────────────────────────
app.mount("/", StaticFiles(directory="static", html=True), name="static")
