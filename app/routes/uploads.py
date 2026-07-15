from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.models_sql import MediaAsset

router = APIRouter(tags=["uploads"])


@router.get("/uploads/{asset_ref:path}")
def get_upload(asset_ref: str, db: Session = Depends(get_db)):
    normalized_ref = asset_ref.strip().split("/")[-1]
    # Try querying by asset_id
    asset = db.query(MediaAsset).filter(MediaAsset.asset_id == normalized_ref).first()

    # Fallback 1: Query by storage_key
    if not asset:
        asset = db.query(MediaAsset).filter(MediaAsset.storage_key == normalized_ref).first()

    # Fallback 2: Query by filename
    if not asset:
        asset = db.query(MediaAsset).filter(MediaAsset.filename == normalized_ref).first()

    if not asset:
        raise HTTPException(status_code=404, detail="Upload not found")

    headers = {
        "Cache-Control": "public, max-age=31536000",
        "Content-Disposition": f'inline; filename="{asset.filename}"',
    }
    return Response(content=asset.content, media_type=asset.content_type or "application/octet-stream", headers=headers)
