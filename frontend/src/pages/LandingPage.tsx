import { Link, useLocation } from 'react-router-dom'

import { Alert } from '../components/ui'

import { youtubeThumbnail } from '../lib/format'
import { useDocumentTitle } from '../lib/useDocumentTitle'

const HOW_IT_WORKS = [
  {
    title: 'Cole o link',
    text: 'Achou uma receita boa no YouTube? Copie o endereço do vídeo e cole no Receita.',
  },
  {
    title: 'A gente escreve',
    text: 'Transcrevemos o vídeo e montamos a receita: ingredientes, quantidades e passo a passo.',
  },
  {
    title: 'Cozinhe com o vídeo',
    text: 'Cada passo leva ao momento certo do vídeo. Tudo fica guardado no seu livro.',
  },
]

const EXAMPLE_INGREDIENTS = [
  ['2 xícaras', 'farinha de trigo'],
  ['3', 'cenouras médias'],
  ['4', 'ovos'],
  ['1 e 1/2 xícara', 'açúcar'],
  ['1 xícara', 'óleo'],
]

const EXAMPLE_STEPS = [
  ['0:00', 'Preaqueça o forno a 180 °C e unte a forma.'],
  ['1:53', 'Bata as cenouras, os ovos, o açúcar e o óleo no liquidificador.'],
  ['4:31', 'Misture o líquido aos secos, sem bater, e leve ao forno.'],
]

function ExampleRecipe() {
  return (
    <figure className="page-sheet relative mx-auto max-w-md rotate-[0.6deg] px-6 py-7 sm:px-8">
      <figcaption className="sr-only">Exemplo de receita no Receita</figcaption>
      <div className="relative -mx-2 mb-5 overflow-hidden rounded-sm shadow-cover">
        <img
          src={youtubeThumbnail('-pRC-FQXLEI')}
          alt="Cena do vídeo de bolo de cenoura"
          className="aspect-video w-full object-cover"
        />
        <span className="absolute inset-0 flex items-center justify-center" aria-hidden="true">
          <span className="flex size-14 items-center justify-center rounded-full bg-card/90 text-terracotta shadow">
            <svg viewBox="0 0 16 16" className="ml-1 size-6">
              <path d="M4 2.5v11l9-5.5z" fill="currentColor" />
            </svg>
          </span>
        </span>
      </div>
      <p className="eyebrow">bolo · sobremesa</p>
      <p className="mt-1 font-serif text-3xl leading-tight font-semibold">Bolo de cenoura</p>
      <p className="mt-1 font-serif text-ink-soft italic">Fofinho, de liquidificador, com calda.</p>
      <p className="mt-5 font-serif text-lg font-semibold">Ingredientes</p>
      <ul className="mt-1 space-y-0.5">
        {EXAMPLE_INGREDIENTS.map(([amount, name]) => (
          <li key={name} className="flex items-baseline gap-2">
            <span
              aria-hidden="true"
              className="size-3.5 shrink-0 translate-y-0.5 rounded-sm border border-ink/50"
            />
            <span>
              <strong>{amount}</strong> {name}
            </span>
          </li>
        ))}
      </ul>
      <p className="mt-5 font-serif text-lg font-semibold">Modo de preparo</p>
      <ol className="mt-1 space-y-2">
        {EXAMPLE_STEPS.map(([time, text], index) => (
          <li key={time} className="flex gap-3">
            <span className="font-serif text-2xl leading-none font-semibold text-terracotta">
              {index + 1}
            </span>
            <span>
              {text}{' '}
              <span className="ml-1 inline-flex rounded-full border border-terracotta/40 px-2 text-sm font-semibold text-terracotta">
                ▶ {time}
              </span>
            </span>
          </li>
        ))}
      </ol>
    </figure>
  )
}

export function LandingPage() {
  useDocumentTitle(null)
  const location = useLocation()
  const accountDeleted =
    (location.state as { accountDeleted?: boolean } | null)?.accountDeleted === true
  return (
    <div className="overflow-x-clip">
      {accountDeleted && (
        <div className="mx-auto max-w-6xl px-4 pt-6">
          <Alert tone="success" title="Sua conta foi excluída">
            Apagamos seu livro, suas notas e o histórico de importações. Obrigado por ter cozinhado
            com a gente.
          </Alert>
        </div>
      )}
      <section className="mx-auto grid max-w-6xl items-center gap-12 px-4 py-10 sm:py-16 lg:grid-cols-2">
        <div>
          <p className="eyebrow">Seu livro de receitas</p>
          <h1 className="mt-3 text-4xl leading-[1.08] font-semibold sm:text-6xl">
            Do vídeo para a receita escrita, num só lugar.
          </h1>
          <p className="mt-5 max-w-xl text-lg text-ink-soft sm:text-xl">
            Cole o link de um vídeo de receita do YouTube. O Receita escreve os ingredientes e o
            passo a passo e guarda tudo no seu livro, junto com o vídeo.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link to="/cadastro" className="btn-primary px-6 text-lg">
              Criar meu livro
            </Link>
            <Link to="/entrar" className="btn-secondary px-6 text-lg">
              Já tenho conta
            </Link>
          </div>
          <p className="mt-3 text-sm text-ink-soft">Grátis. Só precisa de um e-mail.</p>
        </div>
        <ExampleRecipe />
      </section>

      <section aria-labelledby="como-funciona" className="border-t border-line bg-paper-deep/60">
        <div className="mx-auto max-w-6xl px-4 py-12 sm:py-16">
          <h2 id="como-funciona" className="text-center text-3xl font-semibold">
            Como funciona
          </h2>
          <ol className="mt-8 grid gap-6 md:grid-cols-3">
            {HOW_IT_WORKS.map((item, index) => (
              <li key={item.title} className="page-sheet px-6 py-6">
                <span
                  className="font-serif text-4xl font-semibold text-terracotta"
                  aria-hidden="true"
                >
                  {index + 1}
                </span>
                <h3 className="mt-2 text-xl font-semibold">{item.title}</h3>
                <p className="mt-1 text-ink-soft">{item.text}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>
    </div>
  )
}
