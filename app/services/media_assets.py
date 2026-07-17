import uuid
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile as StarletteUploadFile

from app.models_sql import MediaAsset

def store_upload_in_db(
    db: Session,
    upload: UploadFile | StarletteUploadFile,
    owner_user_id: str | None = None,
    owner_role: str | None = None,
) -> str:
    storage_key = f"{uuid.uuid4().hex}{Path(upload.filename or '').suffix[:20]}"
    content = upload.file.read()
    asset = MediaAsset(
        asset_id=f"asset_{uuid.uuid4().hex[:24]}",
        storage_key=storage_key,
        owner_user_id=owner_user_id,
        owner_role=owner_role,
        filename=upload.filename or storage_key,
        content_type=(upload.content_type or "application/octet-stream").strip(),
        size_bytes=len(content or b""),
        content=content or b"",
    )
    db.add(asset)
    db.flush()
    return f"/uploads/{asset.asset_id}"
