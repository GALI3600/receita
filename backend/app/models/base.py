import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column


def str_enum(enum_cls: type[StrEnum], name: str) -> Enum:
    """Enum guardado como VARCHAR + CHECK: adicionar valores não exige ALTER TYPE."""
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=max(len(member.value) for member in enum_cls),
        values_callable=lambda cls: [member.value for member in cls],
    )


class UUIDPrimaryKey:
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


class CreatedAt:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Timestamps(CreatedAt):
    # Traz o `updated_at` do servidor (RETURNING) a cada UPDATE: sem isso o atributo expira e
    # lê-lo depois do commit exigiria um lazy load, que não existe na sessão async.
    __mapper_args__ = {"eager_defaults": True}

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
