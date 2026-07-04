from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import auth_required, pwd_context
from app.database import get_db
from app.models import UserProfileUpdate
from app.models_sql import Bid, Product, User
from app.serializers import serialize_bid, serialize_product, serialize_user
from app.services.users import sync_role_profile

router = APIRouter(prefix="/users", tags=["users"])


@router.put("/profile")
def update_profile(
    body: UserProfileUpdate,
    user: User = Depends(auth_required),
    db: Session = Depends(get_db),
):
    current_user = db.query(User).filter(User.user_id == user.user_id).first()
    if not current_user:
        raise HTTPException(status_code=404, detail="User not found")

    if body.name is not None:
        current_user.name = body.name

    if body.email is not None:
        email = body.email.lower()
        existing = db.query(User).filter(User.email == email, User.user_id != current_user.user_id).first()
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered")
        current_user.email = email

    mobile_number = body.mobile_number if body.mobile_number is not None else body.phone_number
    if mobile_number is not None:
        current_user.mobile_number = mobile_number.strip() or None

    if body.password:
        current_user.password_hash = pwd_context.hash(body.password)

    sync_role_profile(db, current_user)
    db.commit()
    db.refresh(current_user)
    return serialize_user(current_user)


@router.get("/me/bids")
def my_bids(user: User = Depends(auth_required), db: Session = Depends(get_db)):
    bids = (
        db.query(Bid)
        .filter(Bid.bidder_id == user.user_id)
        .order_by(Bid.created_at.desc())
        .limit(200)
        .all()
    )
    return [serialize_bid(bid) for bid in bids]


@router.get("/me/wins")
def my_wins(user: User = Depends(auth_required), db: Session = Depends(get_db)):
    items = db.query(Product).filter(Product.winner_id == user.user_id).limit(200).all()
    return [serialize_product(item) for item in items]
