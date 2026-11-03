import asyncio
from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self.active: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self.active.add(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self.active.discard(websocket)

    async def broadcast(self, message: dict) -> None:
        async with self._lock:
            clients = list(self.active)
        failed = []
        for client in clients:
            try:
                await client.send_json(message)
            except Exception:
                failed.append(client)
        if failed:
            async with self._lock:
                for client in failed:
                    self.active.discard(client)


manager = ConnectionManager()
