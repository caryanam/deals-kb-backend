from sqlalchemy.orm import Session

from app.models_sql import Buyer, Dealer, Seller, User


def sync_role_profile(db: Session, user: User):
    if user.role == "Buyer":
        profile = db.query(Buyer).filter(Buyer.user_id == user.user_id).first()
        if not profile:
            profile = Buyer(user_id=user.user_id)
            db.add(profile)
    elif user.role == "Seller":
        profile = db.query(Seller).filter(Seller.user_id == user.user_id).first()
        if not profile:
            profile = Seller(user_id=user.user_id)
            db.add(profile)
    elif user.role == "Dealer":
        profile = db.query(Dealer).filter(Dealer.user_id == user.user_id).first()
        if not profile:
            profile = Dealer(user_id=user.user_id)
            db.add(profile)
    else:
        return

    profile.email = user.email
    profile.name = user.name
    profile.mobile_number = user.mobile_number
