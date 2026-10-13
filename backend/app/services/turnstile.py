"""Cloudflare Turnstile (CAPTCHA) no cadastro. Sem `TURNSTILE_SECRET_KEY`, a checagem é pulada."""

import logging

import httpx

from app.config import get_settings
from app.errors import CaptchaFailedError, CaptchaUnavailableError

logger = logging.getLogger(__name__)

SITEVERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
TIMEOUT_S = 10


def is_enabled() -> bool:
    return bool(get_settings().turnstile_secret_key.get_secret_value())


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=TIMEOUT_S)


async def verify(token: str | None, remote_ip: str | None) -> None:
    """Levanta `CaptchaFailedError` se o token não for aceito pela Cloudflare."""
    if not is_enabled():
        return
    if not token:
        raise CaptchaFailedError(detail="sem cf-turnstile-response")

    data = {"secret": get_settings().turnstile_secret_key.get_secret_value(), "response": token}
    if remote_ip:
        data["remoteip"] = remote_ip
    try:
        async with _client() as client:
            response = await client.post(SITEVERIFY_URL, data=data)
            response.raise_for_status()
            result = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("turnstile indisponível: %r", exc)
        raise CaptchaUnavailableError(detail=repr(exc)) from exc

    if not result.get("success"):
        raise CaptchaFailedError(detail=f"turnstile: {result.get('error-codes')}")
