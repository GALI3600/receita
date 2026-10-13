from enum import StrEnum
from typing import ClassVar


class ErrorCode(StrEnum):
    INVALID_URL = "invalid_url"
    VIDEO_UNAVAILABLE = "video_unavailable"
    YOUTUBE_BLOCKED = "youtube_blocked"
    NOT_EMBEDDABLE = "not_embeddable"
    LIVE_VIDEO = "live_video"
    TOO_LONG = "too_long"
    NO_TRANSCRIPT = "no_transcript"
    NOT_A_RECIPE = "not_a_recipe"
    LLM_MISSING_KEY = "llm_missing_key"
    LLM_REFUSED = "llm_refused"
    LLM_UNAVAILABLE = "llm_unavailable"
    LLM_INVALID_OUTPUT = "llm_invalid_output"
    LLM_ERROR = "llm_error"


class PipelineError(Exception):
    """Erro do domínio com código estável (gravado em Import.error_code) e mensagem para o usuário.

    `detail` guarda a causa técnica para logs; nunca é exibido ao usuário.
    """

    code: ClassVar[ErrorCode]
    default_message: ClassVar[str]

    def __init__(self, message: str | None = None, *, detail: str | None = None) -> None:
        self.message = message or self.default_message
        self.detail = detail
        super().__init__(self.message)

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}" + (f" ({self.detail})" if self.detail else "")


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
