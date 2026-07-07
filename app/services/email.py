import smtplib
import ssl
from email.message import EmailMessage

from app.config import (
    SMTP_FROM_EMAIL,
    SMTP_FROM_NAME,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_TIMEOUT_SECONDS,
    SMTP_USERNAME,
    SMTP_USE_SSL,
)


def send_email(to_email: str, subject: str, text_body: str) -> None:
    if not SMTP_HOST or not SMTP_USERNAME or not SMTP_PASSWORD or not SMTP_FROM_EMAIL:
        raise RuntimeError("SMTP is not configured")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = f"{SMTP_FROM_NAME} <{SMTP_FROM_EMAIL}>"
    message["To"] = to_email
    message.set_content(text_body)

    if SMTP_USE_SSL:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context, timeout=SMTP_TIMEOUT_SECONDS) as smtp:
            smtp.login(SMTP_USERNAME, SMTP_PASSWORD)
            smtp.send_message(message)
        return

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=SMTP_TIMEOUT_SECONDS) as smtp:
        smtp.starttls(context=ssl.create_default_context())
        smtp.login(SMTP_USERNAME, SMTP_PASSWORD)
        smtp.send_message(message)


def send_otp_email(to_email: str, otp: str, purpose: str) -> None:
    purpose_text = "registration" if purpose == "registration" else "password reset"
    subject = f"DealsKB {purpose_text.title()} OTP"
    body = (
        f"Your DealsKB {purpose_text} OTP is {otp}.\n\n"
        "This code is valid for 5 minutes. Do not share it with anyone.\n\n"
        "Regards,\nDealsKB Support"
    )
    send_email(to_email, subject, body)


def send_newsletter_subscription_email(to_email: str) -> None:
    subject = "Welcome to DealsKB Auction Alerts"
    body = (
        "Hello,\n\n"
        "Thank you for subscribing to DealsKB weekly auction alerts.\n\n"
        "Sample alert format:\n"
        "- New live auctions near you\n"
        "- Cars, Bikes, Mobiles and Laptops going live this week\n"
        "- Secure bidding pass reminders\n"
        "- Featured verified listings\n\n"
        "We will notify you when new auction deals are available.\n\n"
        "Regards,\n"
        "DealsKB Support"
    )
    send_email(to_email, subject, body)
