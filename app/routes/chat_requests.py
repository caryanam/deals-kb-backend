import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import auth_required, is_seller_like
from app.database import get_db
from app.models import ChatRequestCreateIn, ChatRequestRespondIn
from app.models_sql import ChatConversation, ChatMessage, ChatRequest, Product, User
from app.serializers import serialize_chat_request
from app.services.notifications import create_notification
from app.utils import now_utc

router = APIRouter(prefix="/chat-requests", tags=["chat-requests"])


BUYER_MESSAGE = (
    'Hi, I have won the bid for your listing "{listing_name}". I’m interested in completing the purchase '
    "at the winning bid amount. Please confirm if you are willing to proceed."
)
SELLER_ACCEPT_MESSAGE = (
    'Thank you for your interest. I accept your request and am ready to proceed with the sale of '
    '"{listing_name}". Let’s continue the discussion here.'
)
SELLER_REJECT_MESSAGE = (
    'Hi, thank you for your interest in "{listing_name}". I appreciate your bid, but I’m currently expecting '
    "a better price and won’t be proceeding with the sale at this amount. You’re welcome to bid again if "
    "this item is listed in a future auction."
)


def _get_request_or_404(db: Session, request_id: str) -> ChatRequest:
    chat_request = db.query(ChatRequest).filter(ChatRequest.request_id == request_id).first()
    if not chat_request:
        raise HTTPException(status_code=404, detail="Chat request not found")
    return chat_request


def _conversation_for_request(db: Session, request_id: str) -> ChatConversation | None:
    return db.query(ChatConversation).filter(ChatConversation.request_id == request_id).first()


def _create_seed_message(
    db: Session,
    conversation: ChatConversation,
    sender_id: str,
    receiver_id: str,
    message: str,
):
    existing = (
        db.query(ChatMessage)
        .filter(
            ChatMessage.conversation_id == conversation.conversation_id,
            ChatMessage.sender_id == sender_id,
            ChatMessage.receiver_id == receiver_id,
            ChatMessage.message == message,
        )
        .first()
    )
    if existing:
        return

    db.add(
        ChatMessage(
            message_id=f"msg_{uuid.uuid4().hex[:12]}",
            conversation_id=conversation.conversation_id,
            sender_id=sender_id,
            receiver_id=receiver_id,
            message=message,
        )
    )


def _get_or_create_accepted_conversation(db: Session, chat_request: ChatRequest) -> ChatConversation:
    conversation = _conversation_for_request(db, chat_request.request_id)
    if conversation:
        return conversation

    conversation = ChatConversation(
        conversation_id=f"chat_{uuid.uuid4().hex[:12]}",
        request_id=chat_request.request_id,
        product_id=chat_request.product_id,
        buyer_id=chat_request.buyer_id,
        seller_id=chat_request.seller_id,
    )
    db.add(conversation)
    db.flush()
    return conversation


@router.post("")
def create_chat_request(
    body: ChatRequestCreateIn,
    user: User = Depends(auth_required),
    db: Session = Depends(get_db),
):
    if user.role != "Buyer":
        raise HTTPException(status_code=403, detail="Only buyers can send purchase requests")

    product = db.query(Product).filter(Product.product_id == body.product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    if product.status != "ended":
        raise HTTPException(status_code=400, detail="Purchase request is available only after auction ends")
    if product.winner_id != user.user_id:
        raise HTTPException(status_code=403, detail="Purchase request is available only to the winning buyer")

    active_request = (
        db.query(ChatRequest)
        .filter(
            ChatRequest.product_id == product.product_id,
            ChatRequest.buyer_id == user.user_id,
            ChatRequest.status.in_(["PENDING", "ACCEPTED"]),
        )
        .first()
    )
    if active_request:
        conversation = _conversation_for_request(db, active_request.request_id)
        return serialize_chat_request(active_request, conversation=conversation)

    seller = db.query(User).filter(User.user_id == product.seller_id).first()
    if not seller:
        raise HTTPException(status_code=404, detail="Seller not found")

    listing_name = product.title
    chat_request = ChatRequest(
        request_id=f"creq_{uuid.uuid4().hex[:12]}",
        product_id=product.product_id,
        listing_name=listing_name,
        buyer_id=user.user_id,
        buyer_name=user.name,
        seller_id=seller.user_id,
        seller_name=seller.name,
        winning_bid_amount=product.current_bid or product.expected_price or 0,
        status="PENDING",
        buyer_message=BUYER_MESSAGE.format(listing_name=listing_name),
    )
    db.add(chat_request)
    create_notification(
        db,
        user_id=seller.user_id,
        title="Purchase request received",
        message=f"{user.name} sent a purchase request for {listing_name}.",
        notif_type="chat_request_pending",
        product_id=product.product_id,
    )
    db.commit()
    db.refresh(chat_request)
    return serialize_chat_request(chat_request)


@router.get("/buyer")
def list_buyer_requests(
    user: User = Depends(auth_required),
    db: Session = Depends(get_db),
):
    if user.role != "Buyer":
        raise HTTPException(status_code=403, detail="Only buyers can view buyer chat requests")

    requests = (
        db.query(ChatRequest)
        .filter(ChatRequest.buyer_id == user.user_id)
        .order_by(ChatRequest.updated_at.desc(), ChatRequest.created_at.desc())
        .limit(200)
        .all()
    )
    return [serialize_chat_request(item, conversation=_conversation_for_request(db, item.request_id)) for item in requests]


@router.get("/seller")
def list_seller_requests(
    user: User = Depends(auth_required),
    db: Session = Depends(get_db),
):
    if not is_seller_like(user):
        raise HTTPException(status_code=403, detail="Only sellers can view seller chat requests")

    requests = (
        db.query(ChatRequest)
        .filter(ChatRequest.seller_id == user.user_id)
        .order_by(ChatRequest.updated_at.desc(), ChatRequest.created_at.desc())
        .limit(200)
        .all()
    )
    return [serialize_chat_request(item, conversation=_conversation_for_request(db, item.request_id)) for item in requests]


@router.patch("/{request_id}/respond")
def respond_to_chat_request(
    request_id: str,
    body: ChatRequestRespondIn,
    user: User = Depends(auth_required),
    db: Session = Depends(get_db),
):
    if not is_seller_like(user):
        raise HTTPException(status_code=403, detail="Only sellers can respond to purchase requests")

    chat_request = _get_request_or_404(db, request_id)
    if chat_request.seller_id != user.user_id:
        raise HTTPException(status_code=403, detail="Purchase request is available only to the listing seller")
    if chat_request.status != "PENDING":
        raise HTTPException(status_code=400, detail="This purchase request has already been responded to")

    action = (body.action or "").strip().lower()
    now = now_utc().replace(tzinfo=None)
    conversation = None

    if action == "accept":
        chat_request.status = "ACCEPTED"
        chat_request.seller_response_message = SELLER_ACCEPT_MESSAGE.format(listing_name=chat_request.listing_name)
        conversation = _get_or_create_accepted_conversation(db, chat_request)
        _create_seed_message(
            db,
            conversation,
            sender_id=chat_request.buyer_id,
            receiver_id=chat_request.seller_id,
            message=chat_request.buyer_message,
        )
        _create_seed_message(
            db,
            conversation,
            sender_id=chat_request.seller_id,
            receiver_id=chat_request.buyer_id,
            message=chat_request.seller_response_message,
        )
        conversation.updated_at = now
        create_notification(
            db,
            user_id=chat_request.buyer_id,
            title="Purchase request accepted",
            message=f"{chat_request.seller_name} accepted your request for {chat_request.listing_name}. Chat is now open.",
            notif_type="chat_request_accepted",
            product_id=chat_request.product_id,
        )
    elif action == "reject":
        chat_request.status = "REJECTED"
        chat_request.seller_response_message = SELLER_REJECT_MESSAGE.format(listing_name=chat_request.listing_name)
        create_notification(
            db,
            user_id=chat_request.buyer_id,
            title="Purchase request rejected",
            message=f"{chat_request.seller_name} rejected your request for {chat_request.listing_name}.",
            notif_type="chat_request_rejected",
            product_id=chat_request.product_id,
        )
    else:
        raise HTTPException(status_code=400, detail='Action must be "accept" or "reject"')

    chat_request.responded_at = now
    chat_request.updated_at = now
    db.commit()
    db.refresh(chat_request)
    if conversation:
        db.refresh(conversation)
    return serialize_chat_request(chat_request, conversation=conversation)
