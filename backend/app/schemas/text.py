"""Validação comum dos textos enviados pelo cliente."""

from typing import Annotated

from pydantic import AfterValidator


def _reject_nul(value: str) -> str:
    # O Postgres não aceita o caractere NUL em TEXT nem em JSONB: sem isso a gravação (ou a
    # busca) chega ao banco e vira erro 500.
    if "\x00" in value:
        raise ValueError("o texto não pode conter o caractere NUL")
    return value


NoNul = AfterValidator(_reject_nul)

NulFreeStr = Annotated[str, NoNul]
