"""Registry of connected WebSocket clients with per-user targeting.

Events with owner_user_id=None broadcast to everyone; events with a user id
are delivered only to that user's connections.
"""

import asyncio
import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, user_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections.setdefault(user_id, set()).add(websocket)
        logger.info("ws_client_connected", extra={"user_id": user_id})

    async def disconnect(self, user_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            connections = self._connections.get(user_id)
            if connections is not None:
                connections.discard(websocket)
                if not connections:
                    self._connections.pop(user_id, None)
        logger.info("ws_client_disconnected", extra={"user_id": user_id})

    async def dispatch(self, event: dict[str, Any]) -> None:
        owner_user_id = event.get("owner_user_id")
        async with self._lock:
            if owner_user_id:
                targets = list(self._connections.get(str(owner_user_id), ()))
            else:
                targets = [
                    websocket
                    for connections in self._connections.values()
                    for websocket in connections
                ]

        for websocket in targets:
            try:
                await websocket.send_json(event)
            except Exception:  # noqa: BLE001 - dead sockets are cleaned up on receive
                logger.debug("ws_send_failed_dropping_client")


connection_manager = ConnectionManager()
