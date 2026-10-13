import { useId, useState } from 'react'

import type { Ingredient } from '../../api/types'
import { groupIngredients, ingredientAmount } from '../../lib/format'

/** Ingredientes agrupados (massa, recheio...) com caixas para ir marcando o que já separou. */
export function IngredientList({ ingredients }: { ingredients: Ingredient[] }) {
  const baseId = useId()
  const [checked, setChecked] = useState<ReadonlySet<number>>(new Set())
  const groups = groupIngredients(ingredients)

  if (ingredients.length === 0) {
    return <p className="text-ink-soft">O vídeo não lista os ingredientes.</p>
  }

  function toggle(index: number) {
    setChecked((current) => {
      const next = new Set(current)
      if (next.has(index)) next.delete(index)
      else next.add(index)
      return next
    })
  }

  return (
    <div className="space-y-5">
      {groups.map(({ group, items }, groupIndex) => {
        // Pelo índice, não pelo nome: um nome com espaço ("para enrolar") viraria dois ids.
        const headingId = `${baseId}-grupo-${groupIndex}`
        return (
          <section key={group ?? ''} aria-labelledby={group ? headingId : undefined}>
            {group && (
              <h3
                id={headingId}
                className="mb-2 font-serif text-lg font-semibold text-terracotta first-letter:uppercase"
              >
                {group}
              </h3>
            )}
            <ul className="space-y-1">
              {items.map(({ ingredient, index }) => {
                const inputId = `${baseId}-item-${index}`
                const amount = ingredientAmount(ingredient)
                const isChecked = checked.has(index)
                return (
                  <li key={index}>
                    <label
                      htmlFor={inputId}
                      className="flex min-h-11 cursor-pointer items-start gap-3 rounded-md px-1 py-2.5 hover:bg-paper-deep"
                    >
                      <input
                        id={inputId}
                        type="checkbox"
                        checked={isChecked}
                        onChange={() => toggle(index)}
                        className="mt-1 size-5 shrink-0 cursor-pointer accent-terracotta"
                      />
                      <span className={isChecked ? 'text-ink-soft line-through' : ''}>
                        {amount && <span className="font-semibold">{amount} </span>}
                        <span>{ingredient.name}</span>
                        {ingredient.note && (
                          <span className="text-ink-soft">, {ingredient.note}</span>
                        )}
                        {!amount && <span className="text-ink-soft"> (a gosto)</span>}
                      </span>
                    </label>
                  </li>
                )
              })}
            </ul>
          </section>
        )
      })}
    </div>
  )
}
