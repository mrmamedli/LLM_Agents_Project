from email.message import EmailMessage
from typing import Any

import pytest
from pydantic import SecretStr

from app.config import Settings
from app.services.mailer import send_verification_email


async def test_send_verification_email_builds_message_and_uses_smtp_settings(
    monkeypatch: pytest.MonkeyPatch,
    test_settings: Settings,
) -> None:
    sent: list[tuple[EmailMessage, dict[str, Any]]] = []

    async def fake_send(message: EmailMessage, **kwargs: Any) -> None:
        sent.append((message, kwargs))

    monkeypatch.setattr("app.services.mailer.aiosmtplib.send", fake_send)
    settings = test_settings.model_copy(
        update={
            "smtp_host": "smtp.internal.example",
            "smtp_port": 465,
            "smtp_username": "mailer",
            "smtp_password": SecretStr("secret-password"),
            "smtp_from_email": "noreply@studyhub.example",
            "smtp_start_tls": False,
            "smtp_use_tls": True,
            "smtp_timeout_seconds": 5.0,
        }
    )

    await send_verification_email("student@example.com", "active-token", settings)

    assert len(sent) == 1
    message, smtp_options = sent[0]
    assert message["From"] == "noreply@studyhub.example"
    assert message["To"] == "student@example.com"
    assert message["Subject"] == "Confirm your StudyHub email"
    assert message.get_content().count("active-token") == 1
    assert smtp_options == {
        "hostname": "smtp.internal.example",
        "port": 465,
        "username": "mailer",
        "password": "secret-password",
        "start_tls": False,
        "use_tls": True,
        "timeout": 5.0,
    }


async def test_send_verification_email_is_noop_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
    test_settings: Settings,
) -> None:
    async def unexpected_send(*args: object, **kwargs: object) -> None:
        del args, kwargs
        pytest.fail("SMTP must not be called when emails are disabled")

    monkeypatch.setattr("app.services.mailer.aiosmtplib.send", unexpected_send)
    settings = test_settings.model_copy(update={"emails_enabled": False})

    await send_verification_email("student@example.com", "unused-token", settings)


def test_settings_rejects_conflicting_smtp_tls_modes() -> None:
    with pytest.raises(ValueError, match="cannot both be enabled"):
        Settings(smtp_start_tls=True, smtp_use_tls=True)


def test_settings_treats_empty_smtp_credentials_as_absent() -> None:
    settings = Settings(smtp_username="", smtp_password="")

    assert settings.smtp_username is None
    assert settings.smtp_password is None
