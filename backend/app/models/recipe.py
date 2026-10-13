import uuid
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.base import Timestamps, UUIDPrimaryKey, str_enum
from app.models.enums import Difficulty
from app.models.video import Video


class Recipe(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "recipes"
    __table_args__ = (
        UniqueConstraint("user_id", "video_id"),
        CheckConstraint("rating BETWEEN 1 AND 5", name="rating_range"),
        Index("ix_recipes_user_id_created_at", "user_id", "created_at"),
        Index("ix_recipes_tags", "tags", postgresql_using="gin"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    video_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("videos.id"), index=True)

    title: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text, default="", server_default="")
    servings: Mapped[str | None] = mapped_column(String(100))
    prep_time_min: Mapped[int | None] = mapped_column(Integer)
    cook_time_min: Mapped[int | None] = mapped_column(Integer)
    difficulty: Mapped[Difficulty | None] = mapped_column(str_enum(Difficulty, "difficulty"))
    ingredients: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    steps: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    tips: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"))
    tags: Mapped[list[str]] = mapped_column(
        ARRAY(Text), default=list, server_default=text("'{}'::text[]")
    )

    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    user_notes: Mapped[str | None] = mapped_column(Text)
    rating: Mapped[int | None] = mapped_column(SmallInteger)

    video: Mapped[Video] = relationship(lazy="raise")
