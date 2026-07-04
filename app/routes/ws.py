import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.database import SessionLocal
from app.models_sql import Product
from app.realtime import manager
from app.services.products import auction_time_left

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
                    "product_id": product.product_id,
                    "status": product.status,
                    "current_bid": float(product.current_bid) if product.current_bid is not None else None,
                    "highest_bidder_name": product.highest_bidder_name,
                    "time_left": auction_time_left(product),
                    "bid_count": product.bid_count or 0,
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
