"""E-mails da conta: confirmação de cadastro e redefinição de senha.

Dois backends (`EMAIL_BACKEND`): "console" só registra a mensagem no log, com o link (padrão em
development), e "smtp" envia de verdade. O envio roda fora do caminho crítico da requisição
(BackgroundTasks, depois da resposta): uma falha do servidor de e-mail vira log, nunca um erro
para o usuário nem uma diferença de tempo de resposta que revele se o e-mail tem conta.
"""

import asyncio
import html
import logging
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import make_msgid
from urllib.parse import urlencode

from app.config import get_settings
from app.models import User
from app.services import security

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Email:
    to: str
    subject: str
    text: str
    html: str


def frontend_link(path: str, **params: str) -> str:
    base = get_settings().frontend_url.rstrip("/")
    query = f"?{urlencode(params)}" if params else ""
    return f"{base}{path}{query}"


def _render(to: str, subject: str, name: str, paragraphs: list[str], link: str, cta: str) -> Email:
    greeting = f"Olá, {name}!"
    text = "\n\n".join([greeting, paragraphs[0], link, *paragraphs[1:], "— Receita"])
    body = "".join(f"<p>{html.escape(p)}</p>" for p in paragraphs[1:])
    markup = (
        '<div style="font-family: Georgia, serif; color: #3b2f2f; max-width: 480px">'
        f"<p>{html.escape(greeting)}</p>"
        f"<p>{html.escape(paragraphs[0])}</p>"
        f'<p><a href="{html.escape(link)}" style="display: inline-block; padding: 10px 18px; '
        'background: #9a3412; color: #fff; text-decoration: none; border-radius: 6px">'
        f"{html.escape(cta)}</a></p>"
        f'<p style="font-size: 13px">Ou copie o endereço: {html.escape(link)}</p>'
        f"{body}<p>— Receita</p></div>"
    )
    return Email(to=to, subject=subject, text=text, html=markup)


def verification_email(user: User) -> Email:
    token = security.create_email_verification_token(user.id, user.email)
    hours = get_settings().email_verification_ttl_hours
    return _render(
        user.email,
        "Confirme seu e-mail no Receita",
        user.name,
        [
            "Falta pouco para você começar o seu livro de receitas. Confirme seu e-mail:",
            f"O link vale por {hours} horas.",
            "Se você não criou uma conta no Receita, ignore esta mensagem.",
        ],
        frontend_link("/verificar-email", token=token),
        "Confirmar e-mail",
    )


def password_reset_email(user: User) -> Email:
    token = security.create_password_reset_token(user.id, user.password_hash)
    minutes = get_settings().password_reset_ttl_minutes
    return _render(
        user.email,
        "Redefinição de senha do Receita",
        user.name,
        [
            "Recebemos um pedido para redefinir a senha da sua conta. Escolha uma senha nova:",
            f"O link vale por {minutes} minutos e só pode ser usado uma vez.",
            "Se não foi você, ignore esta mensagem: sua senha continua a mesma.",
        ],
        frontend_link("/redefinir-senha", token=token),
        "Redefinir senha",
    )


def account_exists_email(user: User) -> Email:
    """Para um cadastro com um e-mail que já tem conta (a API responde igual nos dois casos)."""
    return _render(
        user.email,
        "Você já tem uma conta no Receita",
        user.name,
        [
            "Alguém tentou criar uma conta no Receita com este e-mail, mas ele já está "
            "cadastrado. Se foi você, é só entrar:",
            "Esqueceu a senha? Use a opção “Esqueci minha senha” na tela de entrada.",
            "Se não foi você, ignore esta mensagem: nada mudou na sua conta.",
        ],
        frontend_link("/entrar"),
        "Entrar",
    )


def _build_message(email: Email) -> EmailMessage:
    settings = get_settings()
    message = EmailMessage()
    message["From"] = settings.email_from
    message["To"] = email.to
    message["Subject"] = email.subject
    message["Message-ID"] = make_msgid(domain=settings.email_from.rpartition("@")[2].strip(">"))
    message.set_content(email.text)
    message.add_alternative(email.html, subtype="html")
    return message


def _send_smtp(email: Email) -> None:
    settings = get_settings()
    message = _build_message(email)
    timeout = settings.smtp_timeout_s
    smtp: smtplib.SMTP
    if settings.smtp_security == "ssl":
        context = ssl.create_default_context()
        smtp = smtplib.SMTP_SSL(
            settings.smtp_host, settings.smtp_port, timeout=timeout, context=context
        )
    else:
        smtp = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=timeout)
    with smtp:
        if settings.smtp_security == "starttls":
            smtp.starttls(context=ssl.create_default_context())
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password.get_secret_value())
        smtp.send_message(message)


async def send(email: Email) -> None:
    if get_settings().email_backend == "console":
        logger.info("e-mail (backend console) para %s: %s\n%s", email.to, email.subject, email.text)
        return
    await asyncio.to_thread(_send_smtp, email)


async def deliver(email: Email) -> None:
    """Envia em segundo plano: falhas ficam no log, nunca sobem."""
    try:
        await send(email)
    except Exception:
        logger.exception("falha ao enviar e-mail %r para %s", email.subject, email.to)
