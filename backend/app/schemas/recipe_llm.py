from typing import Literal

from pydantic import BaseModel, Field

Difficulty = Literal["fácil", "média", "difícil"]


class Ingredient(BaseModel):
    name: str = Field(description='Nome do ingrediente, em minúsculas. Ex.: "farinha de trigo".')
    quantity: str | None = Field(
        description='Quantidade como aparece no vídeo ("2", "1/2", "200"). null se não foi dita.'
    )
    unit: str | None = Field(description='Unidade ("xícara", "g", "colher de sopa") ou null.')
    note: str | None = Field(
        description='Observação de preparo ou estado ("peneirada", "em temperatura ambiente").'
    )
    group: str | None = Field(
        description='Parte da receita a que pertence ("massa", "recheio", "cobertura") ou null.'
    )


class Step(BaseModel):
    order: int = Field(description="Posição do passo, começando em 1.")
    text: str = Field(description="Instrução do passo, no imperativo e em português.")
    video_timestamp_s: int | None = Field(
        description="Segundo do vídeo em que o passo começa a ser mostrado, ou null."
    )


class RecipeLLM(BaseModel):
    is_recipe: bool = Field(description="false se o vídeo não ensina uma receita.")
    title: str = Field(description="Nome da receita.")
    summary: str = Field(description="Resumo de uma ou duas frases sobre o prato.")
    servings: str | None = Field(description='Rendimento ("8 fatias", "4 porções") ou null.')
    prep_time_min: int | None = Field(description="Tempo de preparo ativo, em minutos, ou null.")
    cook_time_min: int | None = Field(description="Tempo de forno/fogo, em minutos, ou null.")
    difficulty: Difficulty | None
    ingredients: list[Ingredient]
    steps: list[Step]
    tips: list[str] = Field(description="Dicas do vídeo e dúvidas sobre quantidades não ditas.")
    tags: list[str] = Field(description='Tags curtas em minúsculas ("sobremesa", "vegano").')
