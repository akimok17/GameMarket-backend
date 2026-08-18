from collections import defaultdict
from fastapi import WebSocket


class OrderConnectionManager:
    def __init__(self):
        self._connections: dict[int, dict[int, set[WebSocket]]] = defaultdict(lambda: defaultdict(set))

    async def connect(self, order_id: int, user_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections[order_id][user_id].add(websocket)

    def disconnect(self, order_id: int, user_id: int, websocket: WebSocket) -> None:
        users = self._connections.get(order_id)
        if not users:
            return
        sockets = users.get(user_id)
        if sockets:
            sockets.discard(websocket)
            if not sockets:
                users.pop(user_id, None)
        if not users:
            self._connections.pop(order_id, None)

    def is_online(self, order_id: int, user_id: int) -> bool:
        return bool(self._connections.get(order_id, {}).get(user_id))

    async def broadcast(self, order_id: int, payload: dict, *, exclude: WebSocket | None = None) -> None:
        dead: list[tuple[int, WebSocket]] = []
        for uid, sockets in list(self._connections.get(order_id, {}).items()):
            for socket in list(sockets):
                if socket is exclude:
                    continue
                try:
                    await socket.send_json(payload)
                except Exception:
                    dead.append((uid, socket))
        for uid, socket in dead:
            self.disconnect(order_id, uid, socket)

    async def send_user(self, order_id: int, user_id: int, payload: dict) -> None:
        for socket in list(self._connections.get(order_id, {}).get(user_id, set())):
            try:
                await socket.send_json(payload)
            except Exception:
                self.disconnect(order_id, user_id, socket)


order_connections = OrderConnectionManager()
