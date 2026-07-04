import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import auth_required, is_seller_like
from app.database import get_db
from app.models import ChatMessageIn
from app.models_sql import ChatConversation, ChatMessage, ChatRequest, Product, User
from app.serializers import serialize_chat_conversation, serialize_chat_message
from app.utils import now_utc

router = APIRouter(prefix="/chats", tags=["chats"])


def _get_conversation_or_404(db: Session, conversation_id: str) -> ChatConversation:
    conversation = db.query(ChatConversation).filter(ChatConversation.conversation_id == conversation_id).first()
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


def _assert_chat_member(conversation: ChatConversation, user: User):
    if user.role == "Admin":
        return
    if user.user_id not in (conversation.buyer_id, conversation.seller_id):
        raise HTTPException(status_code=403, detail="You do not have access to this conversation")


def _assert_conversation_accepted(db: Session, conversation: ChatConversation):
    if not conversation.request_id:
        return
    chat_request = db.query(ChatRequest).filter(ChatRequest.request_id == conversation.request_id).first()
    if not chat_request or chat_request.status != "ACCEPTED":
        raise HTTPException(status_code=403, detail="Chat opens only after seller accepts the purchase request")


def _conversation_payload(db: Session, conversation: ChatConversation, current_user: User | None = None) -> dict:
    product = db.query(Product).filter(Product.product_id == conversation.product_id).first()
    buyer = db.query(User).filter(User.user_id == conversation.buyer_id).first()
    seller = db.query(User).filter(User.user_id == conversation.seller_id).first()
    last_message = (
        db.query(ChatMessage)
        .filter(ChatMessage.conversation_id == conversation.conversation_id)
        .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
        .first()
    )
    payload = serialize_chat_conversation(conversation, product=product, buyer=buyer, seller=seller, last_message=last_message)
    if current_user:
        payload["unread_count"] = (
            db.query(ChatMessage)
            .filter(
                ChatMessage.conversation_id == conversation.conversation_id,
                ChatMessage.receiver_id == current_user.user_id,
                ChatMessage.is_read.is_(False),
            )
            .count()
        )
    return payload


def _get_or_create_product_conversation(db: Session, product: Product, chat_request: ChatRequest) -> ChatConversation:
    conversation = (
        db.query(ChatConversation)
        .filter(
            ChatConversation.request_id == chat_request.request_id,
        )
        .first()
    )
    if conversation:
        return conversation

    conversation = ChatConversation(
        conversation_id=f"chat_{uuid.uuid4().hex[:12]}",
        request_id=chat_request.request_id,
        product_id=product.product_id,
        buyer_id=product.winner_id,
        seller_id=product.seller_id,
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


@router.get("")
def list_my_conversations(
    user: User = Depends(auth_required),
    db: Session = Depends(get_db),
):
    query = db.query(ChatConversation)
    if user.role == "Buyer":
        query = query.filter(ChatConversation.buyer_id == user.user_id)
    elif is_seller_like(user):
        query = query.filter(ChatConversation.seller_id == user.user_id)
    elif user.role != "Admin":
        return []

    conversations = query.order_by(ChatConversation.updated_at.desc(), ChatConversation.created_at.desc()).limit(200).all()
    return [_conversation_payload(db, conversation, current_user=user) for conversation in conversations]


@router.post("/products/{product_id}")
def open_product_chat(
    product_id: str,
    user: User = Depends(auth_required),
    db: Session = Depends(get_db),
):
    product = db.query(Product).filter(Product.product_id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    if product.status != "ended":
        raise HTTPException(status_code=400, detail="Chat is available only after auction ends")
    if not product.winner_id:
        raise HTTPException(status_code=400, detail="Chat is available only when the auction has a winning buyer")

    if user.role == "Buyer" and product.winner_id != user.user_id:
        raise HTTPException(status_code=403, detail="Chat with seller is available only to the winning buyer")
    if is_seller_like(user) and product.seller_id != user.user_id:
        raise HTTPException(status_code=403, detail="Winner chat is available only to the seller")
    if user.role not in ("Buyer", "Seller", "Dealer", "Admin"):
        raise HTTPException(status_code=403, detail="You do not have access to this chat")

    chat_request = (
        db.query(ChatRequest)
        .filter(
            ChatRequest.product_id == product.product_id,
            ChatRequest.buyer_id == product.winner_id,
            ChatRequest.seller_id == product.seller_id,
            ChatRequest.status == "ACCEPTED",
        )
        .first()
    )
    if not chat_request:
        raise HTTPException(status_code=403, detail="Chat opens only after seller accepts the purchase request")

    conversation = _get_or_create_product_conversation(db, product, chat_request)
    return _conversation_payload(db, conversation, current_user=user)


@router.get("/{request_id}")
def get_chat_by_request(
    request_id: str,
    user: User = Depends(auth_required),
    db: Session = Depends(get_db),
):
    chat_request = db.query(ChatRequest).filter(ChatRequest.request_id == request_id).first()
    if not chat_request:
        raise HTTPException(status_code=404, detail="Chat request not found")
    if chat_request.status != "ACCEPTED":
        raise HTTPException(status_code=403, detail="Chat opens only after seller accepts the purchase request")

    conversation = db.query(ChatConversation).filter(ChatConversation.request_id == request_id).first()
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    _assert_chat_member(conversation, user)
    return _conversation_payload(db, conversation, current_user=user)


@router.get("/{conversation_id}/messages")
def list_messages(
    conversation_id: str,
    user: User = Depends(auth_required),
    db: Session = Depends(get_db),
):
    conversation = _get_conversation_or_404(db, conversation_id)
    _assert_chat_member(conversation, user)
    _assert_conversation_accepted(db, conversation)
    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.conversation_id == conversation_id)
        .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
        .limit(500)
        .all()
    )
    return [serialize_chat_message(message) for message in messages]


@router.post("/{conversation_id}/messages")
def send_message(
    conversation_id: str,
    body: ChatMessageIn,
    user: User = Depends(auth_required),
    db: Session = Depends(get_db),
):
    conversation = _get_conversation_or_404(db, conversation_id)
    _assert_chat_member(conversation, user)
    _assert_conversation_accepted(db, conversation)

    text = body.message.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Message is required")
    if len(text) > 2000:
        raise HTTPException(status_code=400, detail="Message must be 2000 characters or less")

    if user.user_id == conversation.buyer_id:
        receiver_id = conversation.seller_id
    elif user.user_id == conversation.seller_id:
        receiver_id = conversation.buyer_id
    else:
        raise HTTPException(status_code=403, detail="Admins can view chats but cannot send messages")

    message = ChatMessage(
        message_id=f"msg_{uuid.uuid4().hex[:12]}",
        conversation_id=conversation.conversation_id,
        sender_id=user.user_id,
        receiver_id=receiver_id,
        message=text,
    )
    conversation.updated_at = now_utc().replace(tzinfo=None)
    db.add(message)
    db.commit()
    db.refresh(message)
    return serialize_chat_message(message)


@router.post("/{conversation_id}/read")
def mark_messages_read(
    conversation_id: str,
    user: User = Depends(auth_required),
    db: Session = Depends(get_db),
):
    conversation = _get_conversation_or_404(db, conversation_id)
    _assert_chat_member(conversation, user)
    _assert_conversation_accepted(db, conversation)
    updated = (
        db.query(ChatMessage)
        .filter(
            ChatMessage.conversation_id == conversation_id,
            ChatMessage.receiver_id == user.user_id,
            ChatMessage.is_read.is_(False),
        )
        .update({"is_read": True}, synchronize_session=False)
    )
    db.commit()
    return {"updated": updated}
