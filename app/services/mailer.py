from email.message import EmailMessage

import aiosmtplib

from app.config import Settings


def build_verification_message(recipient: str, token: str, sender: str) -> EmailMessage:
    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = "Confirm your StudyHub email"
    message.set_content(
        "Use the following token to verify your StudyHub email address:\n\n"
        f"{token}\n\n"
        "If you did not create this account, you can ignore this message."
    )
    return message


async def send_verification_email(recipient: str, token: str, settings: Settings) -> None:
    if not settings.emails_enabled:
        return
    password = (
        settings.smtp_password.get_secret_value() if settings.smtp_password is not None else None
    )
    await aiosmtplib.send(
        build_verification_message(recipient, token, str(settings.smtp_from_email)),
        hostname=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_username,
        password=password,
        start_tls=settings.smtp_start_tls,
        use_tls=settings.smtp_use_tls,
        timeout=settings.smtp_timeout_seconds,
    )
