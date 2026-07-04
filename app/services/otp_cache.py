from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class RegistrationOtpCacheEntry:
    email: Optional[str]
    mobile_number: Optional[str]
    name: str
    role: str
    password_hash: str | None
    otp: str
    expires_at: datetime


registration_otp_cache: dict[str, list[RegistrationOtpCacheEntry]] = {}


def registration_otp_key(email: str | None = None, mobile_number: str | None = None) -> str:
    return (email or mobile_number or "").lower()


def set_registration_otp(entry: RegistrationOtpCacheEntry):
    registration_otp_cache.setdefault(registration_otp_key(entry.email, entry.mobile_number), []).append(entry)


def get_registration_otp(
    mobile_number: str | None = None,
    otp: str | None = None,
    email: str | None = None,
    now: datetime | None = None,
) -> RegistrationOtpCacheEntry | None:
    key = registration_otp_key(email, mobile_number)
    entries = registration_otp_cache.get(key, [])
    if now is not None:
        entries = [entry for entry in entries if entry.expires_at >= now]
        registration_otp_cache[key] = entries

    for entry in reversed(entries):
        if otp is not None and entry.otp != otp:
            continue
        if email is not None and entry.email != email:
            continue
        return entry
    return None


def delete_registration_otp(mobile_number: str | None = None, email: str | None = None):
    registration_otp_cache.pop(registration_otp_key(email, mobile_number), None)
