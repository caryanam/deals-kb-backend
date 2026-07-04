from decimal import Decimal

from app.utils import iso


def value(obj, key, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def money(amount):
    if isinstance(amount, Decimal):
        return float(amount)
    return amount


def serialize_user(user) -> dict:
    return {
        "user_id": value(user, "user_id"),
        "email": value(user, "email"),
        "name": value(user, "name", ""),
        "role": value(user, "role"),
        "auth_provider": value(user, "auth_provider", "email"),
        "mobile_number": value(user, "mobile_number"),
        "buyer_access_until": iso(value(user, "buyer_access_until")),
        "created_at": iso(value(user, "created_at")) or "",
    }


def serialize_product(product) -> dict:
    return {
        "product_id": value(product, "product_id"),
        "seller_id": value(product, "seller_id"),
        "seller_name": value(product, "seller_name", ""),
        "title": value(product, "title"),
        "product_type": value(product, "product_type"),
        "brand": value(product, "brand"),
        "model": value(product, "model"),
        "condition": value(product, "product_condition", value(product, "condition")),
        "description": value(product, "description"),
        "product_price": money(value(product, "product_price")),
        "expected_price": money(value(product, "expected_price")),
        "currency": "INR",
        "photos": value(product, "photos", []) or [],
        "video": value(product, "video"),
        "specifications": value(product, "specifications", {}) or {},
        "documents": value(product, "documents", {}) or {},
        "status": value(product, "status"),
        "reject_reason": value(product, "reject_reason"),
        "auction_start": iso(value(product, "auction_start")),
        "auction_end": iso(value(product, "auction_end")),
        "current_bid": money(value(product, "current_bid")),
        "highest_bidder_id": value(product, "highest_bidder_id"),
        "highest_bidder_name": value(product, "highest_bidder_name"),
        "bid_count": value(product, "bid_count", 0) or 0,
        "winner_id": value(product, "winner_id"),
        "winner_name": value(product, "winner_name"),
        "is_flagged": bool(value(product, "is_flagged", False)),
        "report_count": value(product, "report_count", 0) or 0,
        "is_cancelled": bool(value(product, "is_cancelled", False)),
        "cancel_reason": value(product, "cancel_reason"),
        "cancelled_at": iso(value(product, "cancelled_at")),
        "created_at": iso(value(product, "created_at")),
        "submitted_at": iso(value(product, "submitted_at", value(product, "created_at"))),
        "updated_at": iso(value(product, "updated_at")),
        "approved_at": iso(value(product, "approved_at")),
        "rejected_at": iso(value(product, "rejected_at")),
    }


def serialize_bid(bid) -> dict:
    return {
        "bid_id": value(bid, "bid_id"),
        "product_id": value(bid, "product_id"),
        "bidder_id": value(bid, "bidder_id"),
        "bidder_name": value(bid, "bidder_name"),
        "amount": money(value(bid, "amount")),
        "currency": "INR",
        "created_at": iso(value(bid, "created_at")),
    }


def serialize_notification(notification) -> dict:
    return {
        "notif_id": value(notification, "notif_id"),
        "user_id": value(notification, "user_id"),
        "role": value(notification, "role"),
        "product_id": value(notification, "product_id"),
        "title": value(notification, "title"),
        "body": value(notification, "message"),
        "message": value(notification, "message"),
        "type": value(notification, "type"),
        "read": bool(value(notification, "is_read", False)),
        "is_read": bool(value(notification, "is_read", False)),
        "is_cleared": bool(value(notification, "is_cleared", False)),
        "created_at": iso(value(notification, "created_at")),
        "read_at": iso(value(notification, "read_at")),
        "cleared_at": iso(value(notification, "cleared_at")),
    }


def serialize_chat_message(message) -> dict:
    return {
        "message_id": value(message, "message_id"),
        "conversation_id": value(message, "conversation_id"),
        "sender_id": value(message, "sender_id"),
        "receiver_id": value(message, "receiver_id"),
        "message": value(message, "message"),
        "is_read": bool(value(message, "is_read", False)),
        "created_at": iso(value(message, "created_at")),
    }


def serialize_chat_conversation(conversation, product=None, buyer=None, seller=None, last_message=None) -> dict:
    payload = {
        "conversation_id": value(conversation, "conversation_id"),
        "request_id": value(conversation, "request_id"),
        "product_id": value(conversation, "product_id"),
        "buyer_id": value(conversation, "buyer_id"),
        "seller_id": value(conversation, "seller_id"),
        "created_at": iso(value(conversation, "created_at")),
        "updated_at": iso(value(conversation, "updated_at")),
        "last_message": serialize_chat_message(last_message) if last_message else None,
    }
    if product:
        payload["product"] = {
            "product_id": value(product, "product_id"),
            "title": value(product, "title"),
            "status": value(product, "status"),
            "winner_id": value(product, "winner_id"),
        }
    if buyer:
        payload["buyer"] = {
            "user_id": value(buyer, "user_id"),
            "name": value(buyer, "name", ""),
        }
    if seller:
        payload["seller"] = {
            "user_id": value(seller, "user_id"),
            "name": value(seller, "name", ""),
        }
    return payload


def serialize_chat_request(chat_request, conversation=None) -> dict:
    payload = {
        "request_id": value(chat_request, "request_id"),
        "product_id": value(chat_request, "product_id"),
        "listing_name": value(chat_request, "listing_name"),
        "buyer_id": value(chat_request, "buyer_id"),
        "buyer_name": value(chat_request, "buyer_name"),
        "seller_id": value(chat_request, "seller_id"),
        "seller_name": value(chat_request, "seller_name"),
        "winning_bid_amount": money(value(chat_request, "winning_bid_amount")),
        "status": value(chat_request, "status"),
        "buyer_message": value(chat_request, "buyer_message"),
        "seller_response_message": value(chat_request, "seller_response_message"),
        "created_at": iso(value(chat_request, "created_at")),
        "updated_at": iso(value(chat_request, "updated_at")),
        "responded_at": iso(value(chat_request, "responded_at")),
    }
    if conversation:
        payload["conversation_id"] = value(conversation, "conversation_id")
        payload["conversation"] = serialize_chat_conversation(conversation)
    return payload


def serialize_community_request(community_request, is_joined_by_me=False, is_created_by_me=False, admin=False) -> dict:
    payload = {
        "request_id": value(community_request, "request_id"),
        "product_type": value(community_request, "product_type"),
        "brand": value(community_request, "brand"),
        "model": value(community_request, "model"),
        "budget_min": money(value(community_request, "budget_min")),
        "budget_max": money(value(community_request, "budget_max")),
        "condition_preference": value(community_request, "condition_preference"),
        "description": value(community_request, "description"),
        "interested_count": value(community_request, "interested_count", 0) or 0,
        "status": value(community_request, "status"),
        "created_by_name": value(community_request, "created_by_name"),
        "is_joined_by_me": bool(is_joined_by_me),
        "is_created_by_me": bool(is_created_by_me),
        "created_at": iso(value(community_request, "created_at")),
        "updated_at": iso(value(community_request, "updated_at")),
    }
    if admin:
        payload["created_by_user_id"] = value(community_request, "created_by_user_id")
    return payload


def serialize_report(report) -> dict:
    return {
        "report_id": value(report, "report_id"),
        "product_id": value(report, "product_id"),
        "reporter_id": value(report, "reporter_id"),
        "reporter_name": value(report, "reporter_name"),
        "reporter_role": value(report, "reporter_role"),
        "reported_user_id": value(report, "reported_user_id"),
        "report_type": value(report, "report_type"),
        "reason": value(report, "reason"),
        "evidence": value(report, "evidence", []) or [],
        "status": value(report, "status"),
        "admin_note": value(report, "admin_note"),
        "action_taken": value(report, "action_taken"),
        "created_at": iso(value(report, "created_at")),
        "updated_at": iso(value(report, "updated_at")),
    }


def serialize_payment(payment) -> dict:
    return {
        "payment_id": value(payment, "payment_id"),
        "user_id": value(payment, "user_id"),
        "user_role": value(payment, "user_role"),
        "plan_id": value(payment, "plan_id"),
        "plan_name": value(payment, "plan_name"),
        "amount": value(payment, "amount"),
        "currency": value(payment, "currency"),
        "razorpay_order_id": value(payment, "razorpay_order_id"),
        "razorpay_payment_id": value(payment, "razorpay_payment_id"),
        "status": value(payment, "status"),
        "receipt": value(payment, "receipt"),
        "notes": value(payment, "notes", {}) or {},
        "created_at": iso(value(payment, "created_at")),
        "paid_at": iso(value(payment, "paid_at")),
        "updated_at": iso(value(payment, "updated_at")),
    }


def serialize_admin_user(user, product_count=0) -> dict:
    return {
        "user_id": value(user, "user_id"),
        "name": value(user, "name", ""),
        "email": value(user, "email"),
        "mobile_number": value(user, "mobile_number"),
        "role": value(user, "role"),
        "created_at": iso(value(user, "created_at")) or "",
        "product_count": product_count,
    }
