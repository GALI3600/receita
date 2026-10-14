from typing import Literal

from pydantic import BaseModel, Field

Difficulty = Literal["fácil", "média", "difícil"]


class Ingredient(BaseModel):
    name: str = Field(
        description="Nome do ingrediente, em minúsculas, sem quantidade nem tamanho. "
        'Ex.: "farinha de trigo".'
    )
    quantity: str | None = Field(
        description='Quantidade do vídeo ou da descrição ("2", "1/2", "200"). null se não foi dita.'
    )
    unit: str | None = Field(
        description='Só a unidade ("xícara", "g", "colher de sopa", "dentes") ou null.'
    )
    note: str | None = Field(
        description='Estado, corte, tamanho ou equivalência, sem parênteses ("peneirada", '
        '"grandes", "≈ 1 xícara"). Com quantity null, diz o que fazer ("a gosto", "para fritar", '
        '"quantidade não informada").'
    )
    group: str | None = Field(
        description='Parte da receita a que pertence ("massa", "recheio", "cobertura") ou null.'
    )


class Step(BaseModel):
    order: int = Field(description="Posição do passo, começando em 1.")
    text: str = Field(description="Instrução do passo, no imperativo e em português.")
    video_timestamp_s: int | None = Field(
        description="Segundo do vídeo em que o passo começa a ser feito, ou null."
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
    steps: list[Step] = Field(description="Pelo menos um passo quando is_recipe é true.")
    tips: list[str] = Field(
        description="Conselhos práticos do vídeo para quem cozinha; não fala das fontes."
    )
    tags: list[str] = Field(description='Tags curtas em minúsculas ("sobremesa", "vegano").')
