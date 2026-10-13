import re
from functools import lru_cache
from typing import Annotated, Literal, NamedTuple, Self

from pydantic import BeforeValidator, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# Só para ENVIRONMENT=development sem SECRET_KEY: fora dele a chave é obrigatória.
DEV_SECRET_KEY = "dev-secret-key-inseguro-nao-use-em-producao"
MIN_SECRET_KEY_CHARS = 32

_WINDOWS_S = {"second": 1, "minute": 60, "hour": 3600, "day": 86400}
_RATE_LIMIT_RE = re.compile(r"^\s*(\d+)\s*/\s*(second|minute|hour|day)\s*$")


class RateLimit(NamedTuple):
    """Até `requests` pedidos por janela fixa de `window_s` segundos."""

    requests: int
    window_s: int


def _parse_rate_limit(value: object) -> object:
    """Aceita "10/minute" (também second, hour, day) no .env."""
    if not isinstance(value, str):
        return value
    match = _RATE_LIMIT_RE.match(value)
    if match is None or int(match[1]) < 1:
        raise ValueError('use o formato "<número>/<second|minute|hour|day>", ex.: "10/minute"')
    return RateLimit(int(match[1]), _WINDOWS_S[match[2]])


# NoDecode: o valor do .env é o texto "10/minute", não JSON (o padrão para tuplas).
RateLimitSetting = Annotated[RateLimit, NoDecode, BeforeValidator(_parse_rate_limit)]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Fechado por padrão: cookie sem Secure, SECRET_KEY de desenvolvimento e e-mails só no log
    # valem apenas com ENVIRONMENT=development explícito (docker-compose e .env.example).
    environment: str = "production"
    database_url: str = "postgresql+asyncpg://receita:receita@localhost:5432/receita"
    redis_url: str = "redis://localhost:6379/0"
    cors_origins: list[str] = ["http://localhost:5173"]
    anthropic_api_key: str = ""

    secret_key: SecretStr = SecretStr("")
    frontend_url: str = "http://localhost:5173"
    session_ttl_days: int = Field(default=30, ge=1)
    email_verification_ttl_hours: int = Field(default=48, ge=1)
    password_reset_ttl_minutes: int = Field(default=60, ge=5)

    # Sem valor: "console" em development (o link vai para o log), "smtp" fora dele.
    email_backend: Literal["console", "smtp"] | None = None
    email_from: str = "Receita <nao-responda@receita.local>"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: SecretStr = SecretStr("")
    # "starttls" (porta 587), "ssl" (porta 465) ou "none" (só para servidores locais de teste).
    smtp_security: Literal["starttls", "ssl", "none"] = "starttls"
    smtp_timeout_s: float = 10

    # Cloudflare Turnstile no cadastro; vazio desliga a checagem.
    turnstile_secret_key: SecretStr = SecretStr("")

    # Só com a API atrás de um proxy reverso que sobrescreve o X-Forwarded-For: o IP do
    # cliente passa a ser o último endereço do header (o que o proxy acrescentou).
    trust_proxy_headers: bool = False
    rate_limit_register: RateLimitSetting = RateLimit(5, 3600)
    rate_limit_login: RateLimitSetting = RateLimit(10, 60)
    rate_limit_forgot_password: RateLimitSetting = RateLimit(5, 3600)
    rate_limit_resend_verification: RateLimitSetting = RateLimit(5, 3600)
    rate_limit_imports: RateLimitSetting = RateLimit(30, 3600)

    # Receitas novas (que chamam o Claude) por usuário por dia UTC; cópias e falhas não contam.
    daily_import_limit: int = Field(default=10, ge=0)
    # Teto do gasto diário (UTC) com o Claude; ao atingir, vídeos novos ficam para o dia seguinte.
    daily_llm_budget_usd: float = Field(default=10.0, ge=0)

    max_video_duration_min: int = 60

    whisper_model: str = "small"
    whisper_device: Literal["cpu", "cuda", "auto"] = "cpu"
    whisper_compute_type: str = "int8"
    # Transcrições simultâneas no worker de whisper (cada uma ocupa CPU/RAM inteiras).
    whisper_max_jobs: int = Field(default=1, ge=1, le=4)

    import_job_timeout_s: int = 900
    whisper_job_timeout_s: int = 3600
    import_max_retries: int = 2
    import_retry_delay_s: int = 30
    # Imports parados há mais tempo que isso são dados como falhos pelo worker.
    import_stale_after_min: int = 360

    @property
    def is_development(self) -> bool:
        return self.environment == "development"

    @property
    def cookie_secure(self) -> bool:
        return not self.is_development

    @model_validator(mode="after")
    def _check_production(self) -> Self:
        if not self.secret_key.get_secret_value():
            if not self.is_development:
                raise ValueError("SECRET_KEY é obrigatório fora de ENVIRONMENT=development")
            self.secret_key = SecretStr(DEV_SECRET_KEY)
        elif len(self.secret_key.get_secret_value()) < MIN_SECRET_KEY_CHARS:
            raise ValueError(f"SECRET_KEY precisa ter pelo menos {MIN_SECRET_KEY_CHARS} caracteres")

        if self.email_backend is None:
            self.email_backend = "console" if self.is_development else "smtp"
        if self.email_backend == "smtp" and not self.smtp_host:
            raise ValueError("SMTP_HOST é obrigatório com EMAIL_BACKEND=smtp")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
