from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import auth_required
from app.database import get_db
from app.models_sql import User
from app.services.payment_plans import list_public_plans

router = APIRouter(prefix="/plans", tags=["plans"])


@router.get("")
def list_plans(user: User = Depends(auth_required)):
    return list_public_plans()


@router.get("/my")
def list_my_plans(user: User = Depends(auth_required), db: Session = Depends(get_db)):
    from app.routes.payments import list_my_payment_plans  # noqa: PLC0415

    return list_my_payment_plans(user=user, db=db)
