from sqlalchemy.orm import Session

from app.models_sql import Buyer, Dealer, Seller, User


ROLE_ID_PREFIX = {
    "Buyer": "BYR",
    "Seller": "SLR",
    "Dealer": "DLR",
}


def next_role_user_id(db: Session, role: str) -> str:
    prefix = ROLE_ID_PREFIX.get(role)
    if not prefix:
        return f"user_{role.lower()}"

    existing_ids = [
        row[0]
        for row in db.query(User.user_id)
        .filter(User.role == role, User.user_id.like(f"{prefix}%"))
        .all()
    ]

    max_number = 0
    for value in existing_ids:
        suffix = str(value)[len(prefix):].strip()
        if suffix.isdigit():
            max_number = max(max_number, int(suffix))

    return f"{prefix}{max_number + 1}"


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
