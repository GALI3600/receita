import { useId, useState } from 'react'

function StarIcon({ filled }: { filled: boolean }) {
  return (
    <svg viewBox="0 0 24 24" className="size-8" aria-hidden="true">
      <path
        d="m12 3.6 2.6 5.3 5.8.8-4.2 4.1 1 5.8-5.2-2.7-5.2 2.7 1-5.8-4.2-4.1 5.8-.8z"
        fill={filled ? 'currentColor' : 'none'}
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
    </svg>
  )
}

const LABELS = ['Não gostei', 'Mais ou menos', 'Boa', 'Muito boa', 'Excelente']

/**
 * Avaliação de 1 a 5 estrelas como um grupo de rádios: setas do teclado escolhem, Tab sai do
 * grupo, e o leitor de tela anuncia "3 estrelas, Boa".
 */
export function RatingStars({
  value,
  onChange,
  disabled,
}: {
  value: number | null
  onChange: (value: number | null) => void
  disabled?: boolean
}) {
  const name = useId()
  const legendId = useId()
  const [hover, setHover] = useState<number | null>(null)
  const shown = hover ?? value ?? 0

  return (
    <fieldset aria-describedby={`${legendId}-texto`}>
      <legend id={legendId} className="font-semibold">
        Sua avaliação
      </legend>
      <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1">
        <div className="flex text-terracotta" onMouseLeave={() => setHover(null)}>
          {[1, 2, 3, 4, 5].map((n) => (
            <label
              key={n}
              className="relative inline-flex size-11 cursor-pointer items-center justify-center rounded-full transition-transform hover:scale-110 has-[:focus-visible]:outline-3 has-[:focus-visible]:outline-terracotta has-[:disabled]:cursor-not-allowed"
              onMouseEnter={() => setHover(n)}
              onMouseLeave={() => setHover(null)}
            >
              <input
                type="radio"
                name={name}
                value={n}
                checked={value === n}
                onChange={() => {
                  setHover(null)
                  onChange(n)
                }}
                disabled={disabled}
                className="sr-only"
              />
              <StarIcon filled={n <= shown} />
              <span className="sr-only">
                {n} {n === 1 ? 'estrela' : 'estrelas'}, {LABELS[n - 1]}
              </span>
            </label>
          ))}
        </div>
        <p id={`${legendId}-texto`} className="text-sm text-ink-soft">
          {hover ? LABELS[hover - 1] : value ? LABELS[value - 1] : 'Ainda sem avaliação'}
        </p>
        {value !== null && (
          <button
            type="button"
            className="link inline-flex min-h-11 items-center text-sm print:hidden"
            onClick={() => {
              setHover(null)
              onChange(null)
            }}
            disabled={disabled}
          >
            Limpar avaliação
          </button>
        )}
      </div>
    </fieldset>
  )
}
