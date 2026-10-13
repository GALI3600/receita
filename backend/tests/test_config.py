import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import DEV_SECRET_KEY, RateLimit, Settings

PRODUCTION = {"_env_file": None, "environment": "production", "smtp_host": "smtp.example.com"}
KEY = "k" * 32


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("ENVIRONMENT", "SECRET_KEY", "EMAIL_BACKEND", "SMTP_HOST"):
        monkeypatch.delenv(name, raising=False)


def test_production_is_the_default_and_requires_secret_key() -> None:
    with pytest.raises(ValidationError, match="SECRET_KEY é obrigatório"):
        Settings(_env_file=None)


def test_secret_key_must_be_long() -> None:
    with pytest.raises(ValidationError, match="pelo menos 32 caracteres"):
        Settings(**PRODUCTION, secret_key="curta")


def test_production_settings() -> None:
    settings = Settings(**PRODUCTION, secret_key=KEY)

    assert settings.cookie_secure
    assert settings.email_backend == "smtp"
    assert settings.secret_key.get_secret_value() == KEY


def test_smtp_needs_a_host() -> None:
    with pytest.raises(ValidationError, match="SMTP_HOST"):
        Settings(_env_file=None, environment="production", secret_key=KEY)


def test_development_defaults() -> None:
    settings = Settings(_env_file=None, environment="development")

    assert settings.secret_key.get_secret_value() == DEV_SECRET_KEY
    assert not settings.cookie_secure
    assert settings.email_backend == "console"
    assert settings.daily_import_limit == 10
    assert settings.rate_limit_login == RateLimit(10, 60)


@pytest.mark.parametrize(
    ("value", "expected"),
    [("3/second", RateLimit(3, 1)), (" 20 / hour ", RateLimit(20, 3600)), ("1/day", (1, 86400))],
)
def test_rate_limit_from_env(
    monkeypatch: pytest.MonkeyPatch, value: str, expected: RateLimit
) -> None:
    monkeypatch.setenv("RATE_LIMIT_IMPORTS", value)

    settings = Settings(_env_file=None, environment="development")

    assert settings.rate_limit_imports == expected


@pytest.mark.parametrize("value", ["10", "0/minute", "10/week", "dez/minute"])
def test_invalid_rate_limit(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("RATE_LIMIT_LOGIN", value)

    with pytest.raises(ValidationError, match="formato"):
        Settings(_env_file=None, environment="development")


def test_every_setting_is_documented_in_env_example() -> None:
    env_example = Path(__file__).parents[1] / ".env.example"
    documented = set(re.findall(r"^([A-Z0-9_]+)=", env_example.read_text(), re.M))

    assert {name.upper() for name in Settings.model_fields} - documented == set()
