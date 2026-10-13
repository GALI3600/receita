import uuid

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.base import Timestamps, UUIDPrimaryKey, str_enum
from app.models.enums import ImportStatus


class Import(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "imports"
    __table_args__ = (Index("ix_imports_user_id_created_at", "user_id", "created_at"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    url: Mapped[str] = mapped_column(Text)
    youtube_id: Mapped[str] = mapped_column(String(11), index=True)
    status: Mapped[ImportStatus] = mapped_column(
        str_enum(ImportStatus, "import_status"),
        default=ImportStatus.PENDING,
        server_default=ImportStatus.PENDING,
    )
    error_code: Mapped[str | None] = mapped_column(String(50))
    error_message: Mapped[str | None] = mapped_column(Text)
    recipe_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("recipes.id", ondelete="SET NULL")
    )
