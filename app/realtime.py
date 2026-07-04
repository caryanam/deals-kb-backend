from typing import Dict, List

from fastapi import WebSocket


class AuctionRoom:
    def __init__(self):
        self.rooms: Dict[str, List[WebSocket]] = {}

    async def connect(self, product_id: str, websocket: WebSocket):
        await websocket.accept()
        self.rooms.setdefault(product_id, []).append(websocket)

    def disconnect(self, product_id: str, websocket: WebSocket):
        if product_id not in self.rooms:
            return
        try:
            self.rooms[product_id].remove(websocket)
        except ValueError:
            pass
        if not self.rooms[product_id]:
            del self.rooms[product_id]

    async def broadcast(self, product_id: str, message: dict):
        if product_id not in self.rooms:
            return

        dead = []
        for websocket in list(self.rooms[product_id]):
            try:
                await websocket.send_json(message)
            except Exception:
                dead.append(websocket)

        for websocket in dead:
            self.disconnect(product_id, websocket)


manager = AuctionRoom()
