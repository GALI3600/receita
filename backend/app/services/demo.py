"""Receitas de demonstração para desenvolver a interface sem chamar o Claude.

`python -m app.cli seed-demo --email <email>` grava alguns vídeos reais do YouTube (públicos e
incorporáveis) com uma receita já gerada e coloca as receitas no livro do usuário. Só roda com
ENVIRONMENT=development: os vídeos ficam com o `PROMPT_VERSION` atual, então outros usuários que
importarem os mesmos links recebem estas receitas como se tivessem vindo do Claude.
"""

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import User, Video
from app.services import recipe_llm
from app.services.imports import copy_recipe

DEMO_LLM_MODEL = "demo"


class DemoSeedError(Exception):
    """O seed não pode rodar (ambiente errado ou usuário inexistente)."""


@dataclass(frozen=True, slots=True)
class DemoVideo:
    youtube_id: str
    title: str
    channel: str
    duration_s: int
    description: str
    recipe: dict[str, Any]

    @property
    def thumbnail_url(self) -> str:
        return f"https://i.ytimg.com/vi/{self.youtube_id}/hqdefault.jpg"


def _ingredient(
    name: str,
    quantity: str | None = None,
    unit: str | None = None,
    note: str | None = None,
    group: str | None = None,
) -> dict[str, Any]:
    return {"name": name, "quantity": quantity, "unit": unit, "note": note, "group": group}


def _steps(*steps: tuple[str, int | None]) -> list[dict[str, Any]]:
    return [
        {"order": order, "text": text, "video_timestamp_s": timestamp}
        for order, (text, timestamp) in enumerate(steps, start=1)
    ]


DEMO_VIDEOS: tuple[DemoVideo, ...] = (
    DemoVideo(
        youtube_id="-pRC-FQXLEI",
        title="Bolo de cenoura | Rita Lobo | Cozinha Prática",
        channel="Receitas",
        duration_s=533,
        description=(
            "Rita Lobo ensina um bolo de cenoura com chocolate que é tudo de bom! Confira todas "
            "as dicas para o seu bolo ficar fofinho e no ponto certo."
        ),
        recipe={
            "is_recipe": True,
            "title": "Bolo de cenoura com calda de chocolate",
            "summary": (
                "Bolo de liquidificador fofinho, com cenoura batida na massa e uma calda de "
                "chocolate que fica crocante por cima."
            ),
            "servings": None,
            "prep_time_min": 20,
            "cook_time_min": 45,
            "difficulty": "fácil",
            "ingredients": [
                _ingredient("farinha de trigo", "2", "xícaras", "peneirada", "massa"),
                _ingredient("fermento químico em pó", "1", "colher de sopa", None, "massa"),
                _ingredient("sal", "1", "pitada", None, "massa"),
                _ingredient("cenoura", "3", None, "descascada e picada", "massa"),
                _ingredient("ovo", "4", None, None, "massa"),
                _ingredient("açúcar", "1 e 1/2", "xícara", None, "massa"),
                _ingredient("óleo", "1", "xícara", "de canola ou de milho", "massa"),
                _ingredient("manteiga e farinha", None, None, "para untar a forma", "massa"),
                _ingredient("açúcar", "1/3", "xícara", None, "calda"),
                _ingredient(
                    "chocolate em pó", "1/2", "xícara", "não use cacau nem achocolatado", "calda"
                ),
                _ingredient("manteiga", "1", "colher de sopa", None, "calda"),
                _ingredient("água", "1/3", "xícara", None, "calda"),
            ],
            "steps": _steps(
                ("Preaqueça o forno a 180 °C.", 0),
                (
                    "Unte a forma com uma camada fina e uniforme de manteiga, espalhando com "
                    "papel-toalha, polvilhe farinha e chacoalhe para cobrir tudo.",
                    14,
                ),
                ("Numa tigela, peneire a farinha e junte o fermento e o sal.", 46),
                ("Coloque as cenouras picadas no liquidificador.", 113),
                (
                    "Quebre os ovos um a um numa tigelinha antes de passar para o liquidificador.",
                    163,
                ),
                (
                    "Junte o açúcar e o óleo e bata por 5 minutos, raspando as laterais do copo.",
                    183,
                ),
                (
                    "Despeje o líquido sobre os ingredientes secos e misture só até incorporar, "
                    "sem bater.",
                    271,
                ),
                ("Transfira para a forma e leve ao forno até crescer e dourar.", 347),
                ("Deixe amornar, desenforme e apare o topo do bolo, se quiser.", 377),
                (
                    "Para a calda, leve ao fogo médio o açúcar, o chocolate em pó, a manteiga e a "
                    "água, mexendo com um batedor por uns 5 minutos.",
                    412,
                ),
                (
                    "Quando a calda começar a desgrudar do fundo da panela, espalhe ainda quente "
                    "sobre o bolo morno.",
                    498,
                ),
            ),
            "tips": [
                "Teste o fermento numa água morna: se fizer bolinhas, está bom para usar.",
                "Depois de juntar a farinha, só misture; bater demais deixa o bolo solado.",
                "O vídeo não diz o tempo de forno: confira com um palito a partir de 35 minutos.",
            ],
            "tags": ["bolo", "sobremesa", "liquidificador", "chocolate"],
        },
    ),
    DemoVideo(
        youtube_id="p_UZdXhjeVQ",
        title="Pão de queijo fácil feito no liquidificador | Rita Lobo | Cozinha Prática",
        channel="Receitas",
        duration_s=247,
        description=(
            "Pão de queijo de liquidificador do Cozinha Prática é uma opção para aproveitar "
            "aquelas sobrinhas de queijo que você pode ter na geladeira."
        ),
        recipe={
            "is_recipe": True,
            "title": "Pão de queijo de liquidificador",
            "summary": (
                "Versão a jato do pão de queijo: massa fluida batida no liquidificador e assada "
                "em forminhas, com casquinha leve e miolo puxa."
            ),
            "servings": "6 unidades",
            "prep_time_min": 10,
            "cook_time_min": 25,
            "difficulty": "fácil",
            "ingredients": [
                _ingredient("polvilho azedo", "3/4", "xícara (chá)"),
                _ingredient("queijo meia-cura", "1", "xícara (chá)", "ralado grosso"),
                _ingredient("ovo", "1"),
                _ingredient("leite", "1/2", "xícara (chá)"),
                _ingredient("óleo", "2", "colheres de sopa", "e mais um pouco para untar"),
                _ingredient("sal", "1/2", "colher de chá"),
            ],
            "steps": _steps(
                (
                    "Preaqueça o forno a 200 °C e unte 6 forminhas de cupcake ou de empada com "
                    "óleo, no fundo e nas laterais.",
                    17,
                ),
                ("Separe 2 colheres de sopa do queijo ralado para polvilhar no fim.", 64),
                (
                    "No liquidificador, junte o polvilho, o ovo, o óleo, o restante do queijo, o "
                    "leite e o sal.",
                    97,
                ),
                ("Bata rapidamente, só até a massa ficar lisa e fluida.", 159),
                (
                    "Distribua a massa nas forminhas até 3/4 da altura e cubra com o queijo "
                    "reservado.",
                    177,
                ),
                ("Asse por 25 minutos, até dourar.", 210),
            ),
            "tips": [
                "Nesta versão não é preciso escaldar o polvilho.",
                "O polvilho azedo deixa o pão de queijo mais elástico e puxa.",
                "Aproveite as sobras de queijo da geladeira no lugar do meia-cura.",
            ],
            "tags": ["pão de queijo", "lanche", "liquidificador", "sem glúten"],
        },
    ),
    DemoVideo(
        youtube_id="oJ7FNrLslpY",
        title="A receita de brigadeiro da Rita Lobo",
        channel="Panelinha",
        duration_s=287,
        description=(
            "Tem RECEITA e também AULÃO sobre a classificação NOVA, que divide os alimentos por "
            "grau e propósito de processamento."
        ),
        recipe={
            "is_recipe": True,
            "title": "Brigadeiro de panela",
            "summary": (
                "O brigadeiro clássico feito com ingredientes de verdade: leite condensado, "
                "chocolate em pó, leite e manteiga, cremoso e brilhante."
            ),
            "servings": None,
            "prep_time_min": 5,
            "cook_time_min": 15,
            "difficulty": "fácil",
            "ingredients": [
                _ingredient("leite condensado", "1", "lata", "395 g"),
                _ingredient("leite", "2/3", "xícara (chá)"),
                _ingredient("manteiga", "1", "colher de sopa"),
                _ingredient("chocolate em pó", "3", "colheres de sopa"),
                _ingredient("nibs de cacau", "3/4", "xícara (chá)", "opcional", "para enrolar"),
                _ingredient("manteiga ou água", None, None, "para untar as mãos", "para enrolar"),
            ],
            "steps": _steps(
                (
                    "Numa panela média, dissolva o chocolate em pó no leite em fogo baixo, sem "
                    "deixar bolinhas.",
                    59,
                ),
                ("Junte o leite condensado e misture bem.", 73),
                ("Acrescente a manteiga, que dá brilho e cremosidade.", 197),
                (
                    "Depois que ferver, cozinhe por uns 15 minutos sem parar de mexer, em fogo "
                    "baixo, até o ponto.",
                    209,
                ),
                ("Transfira para um prato e espere esfriar.", 228),
                (
                    "Unte as mãos com manteiga ou água, enrole as bolinhas e passe nos nibs de "
                    "cacau.",
                    232,
                ),
            ),
            "tips": [
                "Não aumente o fogo para acelerar: o brigadeiro pode cristalizar.",
                "Use uma panela média; muito pequena demora, muito grande aquece rápido demais.",
                "No lugar do granulado, use nibs de cacau ou raspas de chocolate de verdade.",
            ],
            "tags": ["brigadeiro", "doce", "festa", "chocolate"],
        },
    ),
)


async def _upsert_video(session: AsyncSession, demo: DemoVideo) -> Video:
    video = await session.scalar(select(Video).where(Video.youtube_id == demo.youtube_id))
    if video is None:
        video = Video(youtube_id=demo.youtube_id, embeddable=True)
        session.add(video)
    video.title = demo.title
    video.channel = demo.channel
    video.duration_s = demo.duration_s
    video.thumbnail_url = demo.thumbnail_url
    video.description = demo.description
    video.embeddable = True
    video.generated_recipe = demo.recipe
    video.llm_model = DEMO_LLM_MODEL
    video.llm_usage = None
    video.prompt_version = recipe_llm.PROMPT_VERSION
    await session.flush()
    return video


async def seed_demo(session: AsyncSession, email: str) -> list[uuid.UUID]:
    """Grava os vídeos de demonstração e põe as receitas no livro do usuário.

    Pode rodar de novo: atualiza os vídeos e não duplica receitas que o usuário já tem.
    Devolve os ids das receitas do usuário, na ordem de `DEMO_VIDEOS`.
    """
    if not get_settings().is_development:
        raise DemoSeedError("seed-demo só roda com ENVIRONMENT=development")
    user = await session.scalar(select(User).where(User.email == email.strip().lower()))
    if user is None:
        raise DemoSeedError(f"nenhuma conta com o e-mail {email!r}")

    recipe_ids = []
    for demo in DEMO_VIDEOS:
        video = await _upsert_video(session, demo)
        recipe_ids.append(await copy_recipe(session, user.id, video))
    await session.commit()
    return recipe_ids
