import uuid
from datetime import datetime
from typing import Annotated, Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.schemas.recipe_llm import Difficulty
from app.schemas.text import NoNul

ShortText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200), NoNul
]
OptionalShortText = (
    Annotated[str, StringConstraints(strip_whitespace=True, max_length=200), NoNul] | None
)

MAX_TAGS = 20
MAX_TAG_CHARS = 40


class IngredientIn(BaseModel):
    name: ShortText
    quantity: OptionalShortText = None
    unit: OptionalShortText = None
    note: OptionalShortText = None
    group: OptionalShortText = None

    @field_validator("quantity", "unit", "note", "group")
    @classmethod
    def _empty_as_none(cls, value: str | None) -> str | None:
        return value or None


class StepIn(BaseModel):
    """Passo enviado pelo cliente; a ordem é a da lista (`order` recebido é ignorado)."""

    text: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000), NoNul
    ]
    video_timestamp_s: int | None = Field(default=None, ge=0)


class IngredientOut(BaseModel):
    name: str
    quantity: str | None = None
    unit: str | None = None
    note: str | None = None
    group: str | None = None


class StepOut(BaseModel):
    order: int
    text: str
    video_timestamp_s: int | None


class VideoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    youtube_id: str
    title: str
    channel: str | None
    thumbnail_url: str | None
    duration_s: int


class RecipeTag(BaseModel):
    name: str
    count: int


class RecipeTags(BaseModel):
    tags: list[RecipeTag]


class RecipeSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    summary: str
    prep_time_min: int | None
    cook_time_min: int | None
    difficulty: Difficulty | None
    tags: list[str]
    is_favorite: bool
    rating: int | None
    created_at: datetime
    updated_at: datetime
    video: VideoOut


class RecipeOut(RecipeSummary):
    servings: str | None
    ingredients: list[IngredientOut]
    steps: list[StepOut]
    tips: list[str]
    user_notes: str | None


class RecipePage(BaseModel):
    items: list[RecipeSummary]
    next_cursor: str | None = Field(
        description="Passe em `cursor` para buscar a próxima página; null na última."
    )


_NOT_NULLABLE = ("title", "summary", "ingredients", "steps", "tips", "tags", "is_favorite")


def normalize_tags(tags: list[str]) -> list[str]:
    cleaned = (tag.strip().lstrip("#").strip().lower() for tag in tags)
    return list(dict.fromkeys(tag for tag in cleaned if tag))


class RecipeUpdate(BaseModel):
    """Campos editáveis; só os enviados são alterados. `null` limpa os campos opcionais."""

    model_config = ConfigDict(extra="forbid")

    title: ShortText | None = None
    summary: (
        Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000), NoNul] | None
    ) = None
    servings: (
        Annotated[str, StringConstraints(strip_whitespace=True, max_length=100), NoNul] | None
    ) = None
    prep_time_min: int | None = Field(default=None, ge=0, le=48 * 60)
    cook_time_min: int | None = Field(default=None, ge=0, le=48 * 60)
    difficulty: Difficulty | None = None
    ingredients: list[IngredientIn] | None = Field(default=None, max_length=100)
    steps: list[StepIn] | None = Field(default=None, max_length=100)
    tips: (
        list[
            Annotated[
                str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500), NoNul
            ]
        ]
        | None
    ) = Field(default=None, max_length=30)
    tags: (
        list[
            Annotated[
                str, StringConstraints(strip_whitespace=True, max_length=MAX_TAG_CHARS), NoNul
            ]
        ]
        | None
    ) = Field(default=None, max_length=MAX_TAGS)
    is_favorite: bool | None = None
    user_notes: Annotated[str, StringConstraints(max_length=5000), NoNul] | None = None
    rating: int | None = Field(default=None, ge=1, le=5)

    @field_validator("tags")
    @classmethod
    def _normalize_tags(cls, tags: list[str] | None) -> list[str] | None:
        return None if tags is None else normalize_tags(tags)

    @model_validator(mode="after")
    def _required_fields_not_null(self) -> "RecipeUpdate":
        for name in _NOT_NULLABLE:
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"o campo '{name}' não pode ser nulo")
        return self

    def changes(self) -> dict[str, Any]:
        """Valores prontos para gravar em `Recipe`, só dos campos enviados."""
        data = self.model_dump(include=self.model_fields_set)
        if "steps" in data:
            data["steps"] = [
                {"order": index, **step} for index, step in enumerate(data["steps"], start=1)
            ]
        if "servings" in data:
            data["servings"] = data["servings"] or None
        if "user_notes" in data:
            data["user_notes"] = (data["user_notes"] or "").strip() or None
        return data
