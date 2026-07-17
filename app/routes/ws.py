import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.database import SessionLocal
from app.models_sql import Product
from app.realtime import manager
from app.services.products import auction_snapshot

logger = logging.getLogger("dealskb")
router = APIRouter(tags=["websocket"])


@router.websocket("/ws/auction/{product_id}")
async def ws_auction(websocket: WebSocket, product_id: str):
    await manager.connect(product_id, websocket)
    try:
        db = SessionLocal()
        try:
            product = db.query(Product).filter(Product.product_id == product_id).first()
            if product:
                await websocket.send_json({
                    "type": "state",
                    **auction_snapshot(product),
                })
        finally:
            db.close()

        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(product_id, websocket)
    except Exception as exc:
        logger.warning("WebSocket error: %s", exc)
        manager.disconnect(product_id, websocket)
