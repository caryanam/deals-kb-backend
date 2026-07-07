import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.models import NewsletterSubscribeIn
from app.services.email import send_newsletter_subscription_email

router = APIRouter(prefix="/newsletter", tags=["newsletter"])
logger = logging.getLogger("dealskb")


def send_newsletter_email_background(email: str):
    try:
        send_newsletter_subscription_email(email)
        logger.info("Newsletter subscription email sent successfully to %s", email)
    except Exception:
        logger.exception("Failed to send newsletter subscription email to %s", email)


@router.post("/subscribe")
def subscribe_to_newsletter(body: NewsletterSubscribeIn, background_tasks: BackgroundTasks):
    email = body.email.lower()
    if not email:
        raise HTTPException(status_code=400, detail="Email is required")

    background_tasks.add_task(send_newsletter_email_background, email)
    return {"message": "Subscription request received. Confirmation email sent to your inbox!"}
