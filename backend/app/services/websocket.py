"""WebSocket connection manager for real-time notification broadcast."""

from __future__ import annotations

import logging
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages active WebSocket connections to broadcast updates to connected clients."""

    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        """Accept connection and register client."""
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info("WebSocket connection established. Total connections: %d", len(self.active_connections))

    def disconnect(self, websocket: WebSocket) -> None:
        """Remove client from active list."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info("WebSocket connection closed. Total connections: %d", len(self.active_connections))

    async def broadcast(self, message: dict) -> None:
        """Send JSON message to all connected clients."""
        logger.debug("Broadcasting WebSocket message: %s", message)
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                logger.warning("Failed to send message to connection. Storing for cleanup.")
                disconnected.append(connection)

        # Cleanup any failed connections
        for conn in disconnected:
            self.disconnect(conn)


# Global connection manager instance
manager = ConnectionManager()
