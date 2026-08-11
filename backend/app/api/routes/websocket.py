"""WebSocket endpoint delivering live platform events to the frontend.

Client connects to /api/ws?token=<supabase-jwt>. After authentication, all
broadcast events plus events targeted at the user's id are pushed as JSON.
"""

import logging

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from app.core.auth import authenticate_token
from app.services.realtime.connection_manager import connection_manager

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws")
async def platform_events_websocket(websocket: WebSocket) -> None:
    token = websocket.query_params.get("token", "")
    try:
        user = authenticate_token(token)
    except HTTPException:
        await websocket.close(code=4401, reason="Unauthorized")
        return

    await websocket.accept()
    await connection_manager.connect(user.id, websocket)
    try:
        # We never expect meaningful inbound messages; this loop exists to
        # detect disconnects (including ping/pong keepalives from the client).
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await connection_manager.disconnect(user.id, websocket)
        if websocket.client_state == WebSocketState.CONNECTED:
            await websocket.close()
