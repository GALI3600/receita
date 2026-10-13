"""Cadastro, login e recuperação de senha.

As respostas de cadastro e de "esqueci a senha" são iguais exista ou não conta com o e-mail;
quem tem conta fica sabendo pelo próprio e-mail.
"""

import hashlib

from fastapi import APIRouter, BackgroundTasks, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, RedisDep, SessionDep, ip_rate_limit
from app.config import get_settings
from app.errors import AppError
from app.models import User
from app.schemas.auth import (
    EmailIn,
    LoginIn,
    MeOut,
    MessageOut,
    RegisterIn,
    ResetPasswordIn,
    TokenIn,
)
from app.schemas.errors import ErrorResponse
from app.services import auth, email, quotas, rate_limit, security, turnstile

router = APIRouter(prefix="/auth", tags=["auth"])

REGISTER_MESSAGE = (
    "Enviamos um e-mail para você confirmar o cadastro. Abra o link para começar a importar "
    "receitas."
)
FORGOT_PASSWORD_MESSAGE = (
    "Se existir uma conta com esse e-mail, enviamos um link para redefinir a senha."
)

_RATE_LIMITED = {429: {"model": ErrorResponse}}
_INVALID_TOKEN = {400: {"model": ErrorResponse}}


def set_session_cookie(response: Response, user: User) -> None:
    settings = get_settings()
    token = security.create_session_token(user.id, user.password_hash)
    response.set_cookie(
        security.SESSION_COOKIE,
        token,
        max_age=settings.session_ttl_days * 86400,
        path="/",
        secure=settings.cookie_secure,
        httponly=True,
        samesite="lax",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        security.SESSION_COOKIE,
        path="/",
        secure=get_settings().cookie_secure,
        httponly=True,
        samesite="lax",
    )


def _email_key(address: str) -> str:
    # Contadores por e-mail no Redis sem guardar o endereço em claro.
    return hashlib.sha256(address.encode()).hexdigest()[:32]


async def me_out(session: AsyncSession, user: User) -> MeOut:
    quota = await quotas.import_quota(session, user.id)
    await session.commit()
    return MeOut.from_user(user, quota)


@router.post(
    "/register",
    response_model=MessageOut,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[ip_rate_limit("register", lambda s: s.rate_limit_register)],
    responses={400: {"model": ErrorResponse}, 422: {"model": ErrorResponse}, **_RATE_LIMITED},
)
async def register(
    body: RegisterIn,
    request: Request,
    session: SessionDep,
    redis: RedisDep,
    background: BackgroundTasks,
) -> MessageOut:
    """Cria a conta e envia o link de confirmação; a resposta não diz se o e-mail já tinha conta.

    Com `TURNSTILE_SECRET_KEY` configurado, exige o token do captcha em `cf-turnstile-response`.
    """
    await turnstile.verify(body.turnstile_token, rate_limit.client_ip(request))
    user, created = await auth.register(
        session, name=body.name, email=body.email, password=body.password
    )
    if created:
        background.add_task(email.deliver, email.verification_email(user))
    elif await rate_limit.allow(
        redis, "register-email", _email_key(user.email), get_settings().rate_limit_register
    ):
        background.add_task(email.deliver, email.account_exists_email(user))
    return MessageOut(message=REGISTER_MESSAGE)


@router.post(
    "/verify",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={**_INVALID_TOKEN},
)
async def verify_email(body: TokenIn, session: SessionDep) -> None:
    """Confirma o e-mail com o token do link. Repetir com o mesmo link não é erro."""
    await auth.verify_email(session, body.token)


@router.post(
    "/resend-verification",
    response_model=MessageOut,
    dependencies=[ip_rate_limit("resend-verification", lambda s: s.rate_limit_resend_verification)],
    responses={401: {"model": ErrorResponse}, **_RATE_LIMITED},
)
async def resend_verification(
    user: CurrentUser, session: SessionDep, background: BackgroundTasks
) -> MessageOut:
    await session.commit()
    if user.email_verified_at is not None:
        return MessageOut(message="Seu e-mail já está confirmado.")
    background.add_task(email.deliver, email.verification_email(user))
    return MessageOut(message=f"Enviamos um novo link de confirmação para {user.email}.")


@router.post(
    "/login",
    response_model=MeOut,
    dependencies=[ip_rate_limit("login", lambda s: s.rate_limit_login)],
    responses={401: {"model": ErrorResponse}, **_RATE_LIMITED},
)
async def login(body: LoginIn, session: SessionDep, response: Response) -> MeOut:
    """Abre a sessão (cookie httpOnly) e devolve o usuário, como em `GET /auth/me`."""
    user = await auth.authenticate(session, email=body.email, password=body.password)
    set_session_cookie(response, user)
    return await me_out(session, user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, redis: RedisDep, response: Response) -> None:
    """Encerra a sessão deste navegador. Sem sessão válida, só apaga o cookie."""
    token = request.cookies.get(security.SESSION_COOKIE)
    if token:
        try:
            await auth.revoke_session(redis, security.decode_session_token(token))
        except AppError:
            pass
    clear_session_cookie(response)


@router.post(
    "/forgot-password",
    response_model=MessageOut,
    dependencies=[ip_rate_limit("forgot-password", lambda s: s.rate_limit_forgot_password)],
    responses={**_RATE_LIMITED},
)
async def forgot_password(
    body: EmailIn, session: SessionDep, redis: RedisDep, background: BackgroundTasks
) -> MessageOut:
    """Envia o link de redefinição se houver conta; responde igual nos dois casos."""
    user = await auth.find_by_email(session, body.email)
    await session.commit()
    # Limite também por e-mail (sem avisar): ninguém lota a caixa de outra pessoa de vários IPs.
    if user is not None and await rate_limit.allow(
        redis,
        "forgot-password-email",
        _email_key(user.email),
        get_settings().rate_limit_forgot_password,
    ):
        background.add_task(email.deliver, email.password_reset_email(user))
    return MessageOut(message=FORGOT_PASSWORD_MESSAGE)


@router.post(
    "/reset-password",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={**_INVALID_TOKEN, 422: {"model": ErrorResponse}},
)
async def reset_password(body: ResetPasswordIn, session: SessionDep) -> None:
    """Troca a senha com o token do link (uso único) e encerra todas as sessões abertas."""
    await auth.reset_password(session, body.token, body.password)


@router.get("/me", response_model=MeOut, responses={401: {"model": ErrorResponse}})
async def me(user: CurrentUser, session: SessionDep) -> MeOut:
    """Usuário logado e a cota de receitas novas do dia."""
    return await me_out(session, user)
