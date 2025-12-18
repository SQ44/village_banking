import logging
import smtplib
from email.message import EmailMessage
from typing import Iterable

from .config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


def send_email(subject: str, body: str, recipients: Iterable[str]) -> bool:
    recipients = [recipient for recipient in recipients if recipient]
    if not recipients:
        logger.warning("No email recipients supplied for subject '%s'", subject)
        return False
    if not settings.smtp_host or not settings.smtp_from_email:
        logger.warning("SMTP settings incomplete; unable to send '%s'", subject)
        return False

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.smtp_from_email
    message["To"] = ", ".join(recipients)
    message.set_content(body)

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as server:
            if settings.smtp_use_tls:
                server.starttls()
            if settings.smtp_username and settings.smtp_password:
                server.login(settings.smtp_username, settings.smtp_password)
            server.send_message(message)
        logger.info("Sent email '%s' to %s", subject, recipients)
        return True
    except Exception:
        logger.exception("Failed to send email '%s'", subject)
        return False
