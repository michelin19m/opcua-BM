"""
OPC UA Server
─────────────
• Wraps asyncua.Server.
• Creates one Variable node per registered tag on startup.
• Supports adding / removing nodes at runtime (when tags are
  created or deleted via the REST API).
• update_node() is called by the polling engine on every poll cycle.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from asyncua import Server, ua
from config import OPC_ENDPOINT, OPC_NAMESPACE

log = logging.getLogger(__name__)

# Map our type strings to asyncua VariantType
_VTYPE: dict[str, ua.VariantType] = {
    "Float":      ua.VariantType.Float,
    "Int32":      ua.VariantType.Int32,
    "Boolean":    ua.VariantType.Boolean,
    "String":     ua.VariantType.String,
    "FloatArray": ua.VariantType.Float,   # element type; value will be a list
}

# Sensible zero-values for each type
_DEFAULT: dict[str, Any] = {
    "Float":      0.0,
    "Int32":      0,
    "Boolean":    False,
    "String":     "",
    "FloatArray": [],
}


class OPCServer:
    def __init__(self):
        self._server: Optional[Server] = None
        self._idx:    Optional[int]    = None
        self._nodes:  dict[str, Any]   = {}   # name → asyncua node
        self._ready   = asyncio.Event()

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        from registry import get_all_tags

        self._server = Server()
        await self._server.init()
        self._server.set_endpoint(OPC_ENDPOINT)
        self._server.set_server_name("SQL Bridge OPC UA Server")
        self._idx = await self._server.register_namespace(OPC_NAMESPACE)

        # Create nodes for every tag that already exists in the registry
        for tag in await get_all_tags():
            await self._add_node(tag)

        await self._server.start()
        self._ready.set()
        log.info("OPC UA server listening on %s", OPC_ENDPOINT)

    async def stop(self) -> None:
        if self._server:
            await self._server.stop()
            log.info("OPC UA server stopped")

    # ── Node management ───────────────────────────────────────────────────────

    async def add_node(self, tag: dict) -> None:
        """Called when a new tag is created via the REST API."""
        await self._ready.wait()
        await self._add_node(tag)

    async def remove_node(self, tag_name: str) -> None:
        """Called when a tag is deleted via the REST API."""
        node = self._nodes.pop(tag_name, None)
        if node and self._server:
            try:
                await self._server.delete_nodes([node], recursive=True)
            except Exception as e:
                log.warning("Could not delete OPC node %s: %s", tag_name, e)

    async def _add_node(self, tag: dict) -> None:
        if tag["name"] in self._nodes:
            return
        vtype   = _VTYPE.get(tag["data_type"], ua.VariantType.Float)
        default = _DEFAULT.get(tag["data_type"], 0.0)
        try:
            node = await self._server.nodes.objects.add_variable(
                self._idx, tag["name"], default, vtype
            )
            self._nodes[tag["name"]] = node
            log.debug("OPC node created: %s (%s)", tag["name"], tag["data_type"])
        except Exception as e:
            log.error("Failed to create OPC node %s: %s", tag["name"], e)

    # ── Value updates ─────────────────────────────────────────────────────────

    async def update_node(self, name: str, value: Any) -> None:
        if not self._ready.is_set() or value is None:
            return
        node = self._nodes.get(name)
        if not node:
            return
        try:
            dv = ua.DataValue(
                Value=ua.Variant(value),
                SourceTimestamp=datetime.now(timezone.utc),
            )
            await node.write_value(dv)
        except Exception as e:
            log.debug("update_node %s failed: %s", name, e)

    # ── Info ──────────────────────────────────────────────────────────────────

    @property
    def endpoint(self) -> str:
        return OPC_ENDPOINT.replace("0.0.0.0", "localhost")

    @property
    def node_count(self) -> int:
        return len(self._nodes)
