from app.errors import LLMRefusedError, VideoUnavailableError


def test_str_never_includes_technical_detail() -> None:
    exc = VideoUnavailableError(detail="ERROR: [youtube] xyz: /tmp/receita-audio-123")

    assert str(exc) == f"[video_unavailable] {exc.message}"
    assert "/tmp" not in str(exc)
    assert "/tmp/receita-audio-123" in repr(exc)


def test_llm_usage_travels_with_the_error() -> None:
    exc = LLMRefusedError(llm_model="claude-opus-5-5", llm_usage={"input_tokens": 10})

    assert exc.llm_usage == {"input_tokens": 10}
    assert exc.llm_model == "claude-opus-5-5"
    assert VideoUnavailableError().llm_usage is None
