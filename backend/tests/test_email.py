import logging
import re
import smtplib
import uuid
from email.message import EmailMessage
from typing import Any

import pytest
from pydantic import SecretStr

from app.config import Settings
from app.models import User
from app.services import email, security


def _user(name: str = "Ana <script>") -> User:
    return User(id=uuid.uuid4(), email="ana@example.com", name=name, password_hash="$argon2id$hash")


def _token(message: email.Email, path: str) -> str:
    match = re.search(rf"^http://localhost:5173{path}\?token=([\w.-]+)$", message.text, re.M)
    assert match is not None, message.text
    return match[1]


def test_verification_email_links_to_the_frontend() -> None:
    user = _user()

    message = email.verification_email(user)

    assert message.to == "ana@example.com"
    assert message.subject == "Confirme seu e-mail no Receita"
    assert message.text.startswith("Olá, Ana <script>!")
    assert "48 horas" in message.text
    token = _token(message, "/verificar-email")
    assert security.decode_email_verification_token(token) == (user.id, user.email)
    assert f'href="http://localhost:5173/verificar-email?token={token}"' in message.html
    assert "<script>" not in message.html and "Ana &lt;script&gt;" in message.html


def test_password_reset_email(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "frontend_url", "https://receita.example/")
    user = _user("Ana")

    message = email.password_reset_email(user)

    match = re.search(r"https://receita\.example/redefinir-senha\?token=([\w.-]+)", message.text)
    assert match is not None
    user_id, fingerprint = security.decode_password_reset_token(match[1])
    assert user_id == user.id
    assert security.fingerprint_matches(fingerprint, user.password_hash)
    assert "60 minutos" in message.text


async def test_console_backend_logs_the_link(caplog: pytest.LogCaptureFixture) -> None:
    message = email.verification_email(_user("Ana"))

    with caplog.at_level(logging.INFO, logger="app.services.email"):
        await email.send(message)

    assert _token(message, "/verificar-email") in caplog.text
    assert "ana@example.com" in caplog.text


class FakeSMTP:
    instances: list["FakeSMTP"] = []

    def __init__(self, host: str, port: int, timeout: float, **kwargs: Any) -> None:
        self.host, self.port, self.timeout = host, port, timeout
        self.calls: list[str] = []
        self.sent: list[EmailMessage] = []
        FakeSMTP.instances.append(self)

    def __enter__(self) -> "FakeSMTP":
        return self

    def __exit__(self, *args: object) -> None:
        self.calls.append("quit")

    def starttls(self, **kwargs: Any) -> None:
        self.calls.append("starttls")

    def login(self, username: str, password: str) -> None:
        self.calls.append(f"login:{username}:{password}")

    def send_message(self, message: EmailMessage) -> None:
        self.calls.append("send")
        self.sent.append(message)


async def test_smtp_backend(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    FakeSMTP.instances.clear()
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    for name, value in {
        "email_backend": "smtp",
        "smtp_host": "smtp.example.com",
        "smtp_port": 587,
        "smtp_username": "receita",
        "smtp_password": SecretStr("segredo"),
        "email_from": "Receita <oi@receita.example>",
    }.items():
        monkeypatch.setattr(settings, name, value)

    await email.send(email.verification_email(_user("Ana")))

    [smtp] = FakeSMTP.instances
    assert (smtp.host, smtp.port) == ("smtp.example.com", 587)
    assert smtp.calls == ["starttls", "login:receita:segredo", "send", "quit"]
    [sent] = smtp.sent
    assert sent["To"] == "ana@example.com"
    assert sent["From"] == "Receita <oi@receita.example>"
    assert sent["Subject"] == "Confirme seu e-mail no Receita"
    assert sent["Message-ID"].endswith("@receita.example>")
    assert sent.get_body(("plain",)) is not None and sent.get_body(("html",)) is not None


async def test_delivery_failures_are_only_logged(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    async def broken(message: email.Email) -> None:
        raise ConnectionRefusedError("smtp fora do ar")

    monkeypatch.setattr(email, "send", broken)

    await email.deliver(email.verification_email(_user("Ana")))

    assert "falha ao enviar e-mail" in caplog.text
