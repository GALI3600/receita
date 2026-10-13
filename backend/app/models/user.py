from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.base import CreatedAt, UUIDPrimaryKey, str_enum
from app.models.enums import UserPlan


class User(UUIDPrimaryKey, CreatedAt, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(100))
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    plan: Mapped[UserPlan] = mapped_column(
        str_enum(UserPlan, "user_plan"), default=UserPlan.FREE, server_default=UserPlan.FREE
    )
