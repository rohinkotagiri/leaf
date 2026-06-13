"""WebSocket router for real-time frontend notifications."""

from __future__ import annotations

import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.services.websocket import manager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websockets"])


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """FastAPI WebSocket endpoint for clients to connect and receive real-time updates."""
    await manager.connect(websocket)
    try:
        while True:
            # Wait for any incoming message to keep connection alive
            data = await websocket.receive_text()
            # Simple heartbeat / ping-pong support
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        logger.exception("WebSocket connection error occurred")
        manager.disconnect(websocket)
