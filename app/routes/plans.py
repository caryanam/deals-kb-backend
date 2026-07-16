from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import auth_required
from app.database import get_db
from app.models_sql import User

router = APIRouter(prefix="/plans", tags=["plans"])


@router.get("")
def list_plans(user: User = Depends(auth_required)):
    return []


@router.get("/my")
def list_my_plans(user: User = Depends(auth_required), db: Session = Depends(get_db)):
    return []
