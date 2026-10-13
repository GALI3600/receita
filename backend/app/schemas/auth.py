import uuid
from datetime import datetime
from typing import Annotated

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
)

from app.models import User, UserPlan
from app.schemas.text import NoNul
from app.services.quotas import ImportQuota

MIN_PASSWORD_CHARS = 8
# O argon2 aceita qualquer tamanho, mas senhas enormes só servem para gastar CPU do servidor.
MAX_PASSWORD_CHARS = 128


def _strip(value: object) -> object:
    return value.strip() if isinstance(value, str) else value


# Normalizado (sem espaços nas pontas e todo em minúsculas): é a chave única da conta.
Email = Annotated[
    EmailStr, BeforeValidator(_strip), AfterValidator(str.lower), Field(max_length=320)
]
NewPassword = Annotated[
    str,
    StringConstraints(min_length=MIN_PASSWORD_CHARS, max_length=MAX_PASSWORD_CHARS),
    NoNul,
]
Password = Annotated[str, StringConstraints(min_length=1, max_length=MAX_PASSWORD_CHARS), NoNul]
Token = Annotated[str, StringConstraints(min_length=1, max_length=2048), NoNul]


class RegisterIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100), NoNul
    ]
    email: Email
    password: NewPassword
    turnstile_token: Token | None = Field(
        default=None,
        alias="cf-turnstile-response",
        description="Token do Cloudflare Turnstile; obrigatório quando o captcha está ativo.",
    )


class LoginIn(BaseModel):
    email: Email
    password: Password


class EmailIn(BaseModel):
    email: Email


class TokenIn(BaseModel):
    token: Token


class ResetPasswordIn(BaseModel):
    token: Token
    password: NewPassword


class PasswordIn(BaseModel):
    password: Password


class MessageOut(BaseModel):
    message: str


class QuotaOut(BaseModel):
    used: int = Field(
        description="Receitas novas de hoje, contando as que ainda estão em andamento"
    )
    limit: int
    remaining: int
    resets_at: datetime = Field(description="Quando a cota zera (meia-noite UTC)")

    @classmethod
    def from_quota(cls, quota: ImportQuota) -> "QuotaOut":
        return cls(
            used=quota.used,
            limit=quota.limit,
            remaining=quota.remaining,
            resets_at=quota.resets_at,
        )


class MeOut(BaseModel):
    id: uuid.UUID
    name: str
    email: str
    email_verified: bool
    plan: UserPlan
    created_at: datetime
    quota: QuotaOut

    @classmethod
    def from_user(cls, user: User, quota: ImportQuota) -> "MeOut":
        return cls(
            id=user.id,
            name=user.name,
            email=user.email,
            email_verified=user.email_verified_at is not None,
            plan=user.plan,
            created_at=user.created_at,
            quota=QuotaOut.from_quota(quota),
        )
