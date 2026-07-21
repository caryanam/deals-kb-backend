import hashlib
import secrets
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from urllib.parse import parse_qsl, urlencode

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from app.config import (
    CCAVENUE_ACCESS_CODE,
    CCAVENUE_CANCEL_URL,
    CCAVENUE_CURRENCY,
    CCAVENUE_ENVIRONMENT,
    CCAVENUE_LANGUAGE,
    CCAVENUE_MERCHANT_ID,
    CCAVENUE_PRODUCTION_URL,
    CCAVENUE_REDIRECT_URL,
    CCAVENUE_TEST_URL,
    CCAVENUE_WORKING_KEY,
)

CCAvenueConfigError = RuntimeError

_IV = bytes(range(16))
_BLOCK_SIZE = 16


def _key() -> bytes:
    if not CCAVENUE_WORKING_KEY:
        raise CCAvenueConfigError("CCAVENUE_WORKING_KEY is not configured")
    return hashlib.md5(CCAVENUE_WORKING_KEY.encode("utf-8")).digest()


def gateway_url() -> str:
    url = CCAVENUE_PRODUCTION_URL if CCAVENUE_ENVIRONMENT == "production" else CCAVENUE_TEST_URL
    if not url:
        raise CCAvenueConfigError("CCAvenue gateway URL is not configured for the selected environment")
    return url


def require_configured() -> None:
    missing = [
        name
        for name, value in {
            "CCAVENUE_MERCHANT_ID": CCAVENUE_MERCHANT_ID,
            "CCAVENUE_ACCESS_CODE": CCAVENUE_ACCESS_CODE,
            "CCAVENUE_WORKING_KEY": CCAVENUE_WORKING_KEY,
            "CCAVENUE_REDIRECT_URL": CCAVENUE_REDIRECT_URL,
            "CCAVENUE_CANCEL_URL": CCAVENUE_CANCEL_URL,
        }.items()
        if not value
    ]
    if missing:
        raise CCAvenueConfigError(f"Missing CCAvenue configuration: {', '.join(missing)}")
    gateway_url()


def _pad(data: bytes) -> bytes:
    pad_len = _BLOCK_SIZE - (len(data) % _BLOCK_SIZE)
    return data + bytes([pad_len]) * pad_len


def _unpad(data: bytes) -> bytes:
    if not data:
        raise ValueError("Empty CCAvenue decrypted payload")
    pad_len = data[-1]
    if pad_len < 1 or pad_len > _BLOCK_SIZE:
        raise ValueError("Invalid CCAvenue padding")
    return data[:-pad_len]


def encrypt_request(plain_text: str) -> str:
    cipher = Cipher(algorithms.AES(_key()), modes.CBC(_IV))
    encryptor = cipher.encryptor()
    encrypted = encryptor.update(_pad(plain_text.encode("utf-8"))) + encryptor.finalize()
    return encrypted.hex()


def decrypt_response(enc_response: str) -> str:
    cipher = Cipher(algorithms.AES(_key()), modes.CBC(_IV))
    decryptor = cipher.decryptor()
    decrypted = decryptor.update(bytes.fromhex((enc_response or "").strip())) + decryptor.finalize()
    return _unpad(decrypted).decode("utf-8", errors="replace")


def format_amount(amount: Decimal) -> str:
    return str(Decimal(amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def generate_order_id() -> str:
    return f"DKB-{secrets.token_urlsafe(18).replace('-', '').replace('_', '')[:24]}"


def build_payment_request(payment, user, item: dict[str, Any] | None = None) -> str:
    billing_name = (getattr(user, "name", "") or "DealsKB Customer").strip()[:60]
    billing_email = (getattr(user, "email", "") or "").strip()[:100]
    billing_tel = (getattr(user, "mobile_number", "") or "").strip()[:20]
    params = {
        "merchant_id": CCAVENUE_MERCHANT_ID,
        "order_id": payment.order_id,
        "currency": payment.currency or CCAVENUE_CURRENCY,
        "amount": format_amount(payment.amount),
        "redirect_url": CCAVENUE_REDIRECT_URL,
        "cancel_url": CCAVENUE_CANCEL_URL,
        "language": CCAVENUE_LANGUAGE,
        "billing_name": billing_name,
        "billing_email": billing_email,
        "billing_tel": billing_tel,
        "merchant_param1": payment.payment_id,
        "merchant_param2": payment.payment_type or "",
    }
    if item and item.get("name"):
        params["merchant_param3"] = str(item["name"])[:100]
    return urlencode(params)


def parse_decrypted_response(response: str) -> dict[str, str]:
    parsed = {}
    for key, value in parse_qsl(response or "", keep_blank_values=True):
        parsed[str(key).strip()] = str(value).strip()
    return parsed


def map_order_status(order_status: str | None) -> str:
    normalized = (order_status or "").strip().lower()
    if "success" in normalized:
        return "SUCCESS"
    if "fail" in normalized:
        return "FAILED"
    if "abort" in normalized:
        return "ABORTED"
    if "invalid" in normalized:
        return "INVALID"
    if "await" in normalized:
        return "AWAITED"
    return "INVALID"
