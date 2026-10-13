from enum import StrEnum
from typing import Any, ClassVar


class ErrorCode(StrEnum):
    INVALID_URL = "invalid_url"
    VIDEO_UNAVAILABLE = "video_unavailable"
    YOUTUBE_BLOCKED = "youtube_blocked"
    NOT_EMBEDDABLE = "not_embeddable"
    LIVE_VIDEO = "live_video"
    TOO_LONG = "too_long"
    NO_TRANSCRIPT = "no_transcript"
    TRANSCRIPTION_FAILED = "transcription_failed"
    NOT_A_RECIPE = "not_a_recipe"
    LLM_MISSING_KEY = "llm_missing_key"
    LLM_REFUSED = "llm_refused"
    LLM_UNAVAILABLE = "llm_unavailable"
    LLM_INVALID_OUTPUT = "llm_invalid_output"
    LLM_ERROR = "llm_error"
    LLM_BUDGET_EXCEEDED = "llm_budget_exceeded"
    IMPORT_TIMEOUT = "import_timeout"
    INTERNAL_ERROR = "internal_error"
    QUEUE_UNAVAILABLE = "queue_unavailable"
    UNAUTHORIZED = "unauthorized"
    NOT_FOUND = "not_found"
    VALIDATION_ERROR = "validation_error"
    INVALID_CURSOR = "invalid_cursor"
    NO_ORIGINAL_RECIPE = "no_original_recipe"
    CSRF_FAILED = "csrf_failed"
    RATE_LIMITED = "rate_limited"
    QUOTA_EXCEEDED = "quota_exceeded"
    EMAIL_NOT_VERIFIED = "email_not_verified"
    INVALID_CREDENTIALS = "invalid_credentials"
    INVALID_PASSWORD = "invalid_password"
    INVALID_TOKEN = "invalid_token"
    CAPTCHA_FAILED = "captcha_failed"
    CAPTCHA_UNAVAILABLE = "captcha_unavailable"


class AppError(Exception):
    """Erro do domínio com código estável e mensagem para o usuário.

    `detail` guarda a causa técnica e só aparece em `repr()` (logs); `str()` traz apenas o código
    e a mensagem. Na API vira `{"error": {"code", "message"}}` com `status_code` e `headers`.
    """

    code: ClassVar[ErrorCode]
    default_message: ClassVar[str]
    status_code: ClassVar[int] = 400

    def __init__(self, message: str | None = None, *, detail: str | None = None) -> None:
        self.message = message or self.default_message
        self.detail = detail
        self.headers: dict[str, str] = {}
        super().__init__(self.message)

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"

    def __repr__(self) -> str:
        detail = f", detail={self.detail!r}" if self.detail else ""
        return f"{type(self).__name__}(code={self.code!r}, message={self.message!r}{detail})"


class PipelineError(AppError):
    """Falha do processamento de um vídeo, gravada em `Import.error_code`/`error_message`.

    `llm_usage` vem preenchido quando a falha aconteceu depois de uma chamada paga ao Claude (o
    uso precisa ser contabilizado mesmo sem receita). `transient` marca as falhas que podem
    passar sozinhas: só essas são tentadas de novo pelo worker.
    """

    status_code = 422
    transient: ClassVar[bool] = False

    def __init__(
        self,
        message: str | None = None,
        *,
        detail: str | None = None,
        llm_model: str | None = None,
        llm_usage: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, detail=detail)
        self.llm_model = llm_model
        self.llm_usage = llm_usage


class InvalidUrlError(PipelineError):
    code = ErrorCode.INVALID_URL
    default_message = "Esse link não parece ser de um vídeo do YouTube. Confira e tente de novo."


class VideoUnavailableError(PipelineError):
    code = ErrorCode.VIDEO_UNAVAILABLE
    default_message = (
        "Não conseguimos acessar esse vídeo. Ele pode ser privado ou ter sido removido."
    )


class YoutubeBlockedError(PipelineError):
    code = ErrorCode.YOUTUBE_BLOCKED
    transient = True
    default_message = (
        "O YouTube bloqueou temporariamente o acesso ao vídeo. Tente de novo em alguns minutos."
    )


class NotEmbeddableError(PipelineError):
    code = ErrorCode.NOT_EMBEDDABLE
    default_message = (
        "O dono desse vídeo não permite que ele seja exibido fora do YouTube, "
        "então não dá para guardá-lo no livro."
    )


class LiveVideoError(PipelineError):
    code = ErrorCode.LIVE_VIDEO
    default_message = (
        "Transmissões ao vivo só podem ser importadas depois que terminam. Tente mais tarde."
    )


class VideoTooLongError(PipelineError):
    code = ErrorCode.TOO_LONG
    default_message = "Esse vídeo é longo demais para ser importado."


class NoTranscriptError(PipelineError):
    code = ErrorCode.NO_TRANSCRIPT
    default_message = (
        "Não encontramos a receita nesse vídeo: ele não tem fala que dê para transcrever "
        "e a descrição também não traz a receita."
    )


class TranscriptionFailedError(PipelineError):
    code = ErrorCode.TRANSCRIPTION_FAILED
    transient = True
    default_message = (
        "Não conseguimos transcrever o áudio desse vídeo. Tente de novo em alguns minutos."
    )


class TranscriptionGaveUpError(TranscriptionFailedError):
    """O whisper já falhou demais com este vídeo; ele não volta para a fila."""

    transient = False
    default_message = (
        "Não conseguimos transcrever o áudio desse vídeo. Tente outro vídeo com a mesma receita."
    )


class NotARecipeError(PipelineError):
    code = ErrorCode.NOT_A_RECIPE
    default_message = "Esse vídeo não parece ser uma receita."


class LLMMissingKeyError(PipelineError):
    code = ErrorCode.LLM_MISSING_KEY
    default_message = (
        "A geração de receitas não está configurada no servidor. Tente de novo mais tarde."
    )


class LLMRefusedError(PipelineError):
    code = ErrorCode.LLM_REFUSED
    default_message = "Não foi possível gerar a receita para esse vídeo."


class LLMUnavailableError(PipelineError):
    code = ErrorCode.LLM_UNAVAILABLE
    transient = True
    default_message = (
        "O serviço que escreve as receitas está indisponível no momento. "
        "Tente de novo em alguns minutos."
    )


class LLMInvalidOutputError(PipelineError):
    code = ErrorCode.LLM_INVALID_OUTPUT
    default_message = "Não conseguimos montar a receita desse vídeo. Tente de novo mais tarde."


class LLMError(PipelineError):
    code = ErrorCode.LLM_ERROR
    default_message = "Algo deu errado ao escrever a receita. Tente de novo mais tarde."


class LLMBudgetExceededError(PipelineError):
    """O gasto do dia com o Claude chegou ao teto: o worker adia o import (status `deferred`)."""

    code = ErrorCode.LLM_BUDGET_EXCEEDED
    default_message = (
        "Muita gente está importando receitas hoje. A sua vai ser escrita amanhã, "
        "e o vídeo fica guardado até lá."
    )


class ImportTimeoutError(PipelineError):
    code = ErrorCode.IMPORT_TIMEOUT
    default_message = "O processamento desse vídeo demorou demais. Tente de novo mais tarde."


class InternalError(PipelineError):
    code = ErrorCode.INTERNAL_ERROR
    status_code = 500
    default_message = "Algo deu errado do nosso lado. Tente de novo em alguns minutos."


class QueueUnavailableError(AppError):
    code = ErrorCode.QUEUE_UNAVAILABLE
    status_code = 503
    default_message = (
        "Não conseguimos colocar o vídeo na fila agora. Tente de novo em alguns minutos."
    )


class UnauthorizedError(AppError):
    code = ErrorCode.UNAUTHORIZED
    status_code = 401
    default_message = "Entre na sua conta para continuar."


class NotFoundError(AppError):
    code = ErrorCode.NOT_FOUND
    status_code = 404
    default_message = "Não encontramos o que você procurou."


class RecipeNotFoundError(NotFoundError):
    default_message = "Receita não encontrada."


class ImportNotFoundError(NotFoundError):
    default_message = "Importação não encontrada."


class InvalidCursorError(AppError):
    code = ErrorCode.INVALID_CURSOR
    status_code = 422
    default_message = "A página pedida não é válida. Recarregue a lista."


class NoOriginalRecipeError(AppError):
    code = ErrorCode.NO_ORIGINAL_RECIPE
    status_code = 409
    default_message = "A receita original desse vídeo não está disponível para restaurar."


class CsrfError(AppError):
    code = ErrorCode.CSRF_FAILED
    status_code = 403
    default_message = "Pedido bloqueado por segurança. Recarregue a página e tente de novo."


class TooManyRequestsError(AppError):
    """429 com `Retry-After` (segundos até poder tentar de novo)."""

    status_code = 429

    def __init__(
        self, retry_after_s: int, message: str | None = None, *, detail: str | None = None
    ) -> None:
        super().__init__(message, detail=detail)
        self.retry_after_s = max(1, retry_after_s)
        self.headers["Retry-After"] = str(self.retry_after_s)


class RateLimitedError(TooManyRequestsError):
    code = ErrorCode.RATE_LIMITED
    default_message = "Muitas tentativas em pouco tempo. Espere um pouco e tente de novo."


class QuotaExceededError(TooManyRequestsError):
    code = ErrorCode.QUOTA_EXCEEDED
    default_message = (
        "Você chegou ao limite de receitas novas por hoje. Amanhã tem mais; enquanto isso, "
        "vídeos que já estão no site continuam liberados."
    )


class EmailNotVerifiedError(AppError):
    code = ErrorCode.EMAIL_NOT_VERIFIED
    status_code = 403
    default_message = (
        "Confirme seu e-mail para importar receitas. O link está na sua caixa de entrada."
    )


class InvalidCredentialsError(AppError):
    code = ErrorCode.INVALID_CREDENTIALS
    status_code = 401
    default_message = "E-mail ou senha incorretos."


class InvalidPasswordError(AppError):
    code = ErrorCode.INVALID_PASSWORD
    status_code = 403
    default_message = "Senha incorreta."


class InvalidTokenError(AppError):
    code = ErrorCode.INVALID_TOKEN
    default_message = "Este link é inválido ou expirou. Peça um novo."


class CaptchaFailedError(AppError):
    code = ErrorCode.CAPTCHA_FAILED
    default_message = "Não conseguimos confirmar que você não é um robô. Tente de novo."


class CaptchaUnavailableError(AppError):
    code = ErrorCode.CAPTCHA_UNAVAILABLE
    status_code = 503
    default_message = "Não conseguimos checar o captcha agora. Tente de novo em alguns minutos."
