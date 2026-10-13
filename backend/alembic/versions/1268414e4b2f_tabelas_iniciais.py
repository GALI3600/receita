"""tabelas iniciais

Revision ID: 1268414e4b2f
Revises:
Create Date: 2026-10-13 11:18:05.852144

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1268414e4b2f"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _created_at() -> sa.Column:
    return sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        server_default=sa.text("now()"),
        nullable=False,
    )


def _updated_at() -> sa.Column:
    return sa.Column(
        "updated_at",
        sa.DateTime(timezone=True),
        server_default=sa.text("now()"),
        nullable=False,
    )


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("plan", sa.String(length=4), server_default="free", nullable=False),
        _created_at(),
        sa.CheckConstraint("plan IN ('free')", name=op.f("ck_users_user_plan")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )

    op.create_table(
        "videos",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("youtube_id", sa.String(length=11), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("channel", sa.String(length=255), nullable=True),
        sa.Column("duration_s", sa.Integer(), nullable=False),
        sa.Column("thumbnail_url", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("embeddable", sa.Boolean(), nullable=False),
        sa.Column("transcript", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("transcript_source", sa.String(length=7), nullable=True),
        sa.Column("generated_recipe", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("llm_model", sa.String(length=100), nullable=True),
        sa.Column("llm_usage", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("prompt_version", sa.String(length=50), nullable=True),
        _created_at(),
        sa.CheckConstraint(
            "transcript_source IN ('manual', 'auto', 'whisper')",
            name=op.f("ck_videos_transcript_source"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_videos")),
        sa.UniqueConstraint("youtube_id", name=op.f("uq_videos_youtube_id")),
    )

    op.create_table(
        "recipes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("video_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), server_default="", nullable=False),
        sa.Column("servings", sa.String(length=100), nullable=True),
        sa.Column("prep_time_min", sa.Integer(), nullable=True),
        sa.Column("cook_time_min", sa.Integer(), nullable=True),
        sa.Column("difficulty", sa.String(length=7), nullable=True),
        sa.Column(
            "ingredients",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "steps",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "tips",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "tags",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'::text[]"),
            nullable=False,
        ),
        sa.Column("is_favorite", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("user_notes", sa.Text(), nullable=True),
        sa.Column("rating", sa.SmallInteger(), nullable=True),
        _created_at(),
        _updated_at(),
        sa.CheckConstraint(
            "difficulty IN ('fácil', 'média', 'difícil')", name=op.f("ck_recipes_difficulty")
        ),
        sa.CheckConstraint("rating BETWEEN 1 AND 5", name=op.f("ck_recipes_rating_range")),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_recipes_user_id_users"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["video_id"], ["videos.id"], name=op.f("fk_recipes_video_id_videos")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_recipes")),
        sa.UniqueConstraint("user_id", "video_id", name=op.f("uq_recipes_user_id_video_id")),
    )
    op.create_index("ix_recipes_tags", "recipes", ["tags"], postgresql_using="gin")
    op.create_index("ix_recipes_user_id_created_at", "recipes", ["user_id", "created_at"])
    op.create_index(op.f("ix_recipes_video_id"), "recipes", ["video_id"])

    op.create_table(
        "imports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("youtube_id", sa.String(length=11), nullable=False),
        sa.Column("status", sa.String(length=12), server_default="pending", nullable=False),
        sa.Column("error_code", sa.String(length=50), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("recipe_id", sa.Uuid(), nullable=True),
        _created_at(),
        _updated_at(),
        sa.CheckConstraint(
            "status IN ('pending', 'fetching', 'transcribing', 'generating', 'done', 'failed')",
            name=op.f("ck_imports_import_status"),
        ),
        sa.ForeignKeyConstraint(
            ["recipe_id"],
            ["recipes.id"],
            name=op.f("fk_imports_recipe_id_recipes"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_imports_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_imports")),
    )
    op.create_index("ix_imports_user_id_created_at", "imports", ["user_id", "created_at"])
    op.create_index(op.f("ix_imports_youtube_id"), "imports", ["youtube_id"])


def downgrade() -> None:
    op.drop_table("imports")
    op.drop_table("recipes")
    op.drop_table("videos")
    op.drop_table("users")
