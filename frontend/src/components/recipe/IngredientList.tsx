import { useId, useRef } from 'react'

import type { Ingredient } from '../../api/types'
import { ingredientKey, useCheckedIngredients } from '../../lib/checkedIngredients'
import { groupIngredients, ingredientAmount, ingredientNote } from '../../lib/format'
import { scaleIngredient } from '../../lib/quantity'

interface IngredientListProps {
  recipeId: string
  ingredients: Ingredient[]
  /** Multiplicador das quantidades (escala de porções); 1 mostra o original. */
  factor?: number
}

/**
 * Ingredientes agrupados (massa, recheio...) com caixas para ir marcando o que já separou. As
 * marcações ficam guardadas no navegador, por receita.
 */
export function IngredientList({ recipeId, ingredients, factor = 1 }: IngredientListProps) {
  const baseId = useId()
  const { checked, toggle, clear } = useCheckedIngredients(recipeId, ingredients)
  const groups = groupIngredients(ingredients)
  const listRef = useRef<HTMLDivElement>(null)

  function clearAll() {
    clear()
    // O botão some: o foco vai para o primeiro ingrediente.
    listRef.current?.querySelector('input')?.focus()
  }

  if (ingredients.length === 0) {
    return <p className="text-ink-soft">O vídeo não lista os ingredientes.</p>
  }

  return (
    <div>
      <div ref={listRef} className="space-y-5 print:columns-2 print:gap-8 print:space-y-0">
        {groups.map(({ group, items }, groupIndex) => {
          // Pelo índice, não pelo nome: um nome com espaço ("para enrolar") viraria dois ids.
          const headingId = `${baseId}-grupo-${groupIndex}`
          return (
            <section
              key={group ?? ''}
              aria-labelledby={group ? headingId : undefined}
              className="print:pb-3"
            >
              {group && (
                <h3
                  id={headingId}
                  className="mb-1 font-serif text-lg font-semibold text-terracotta first-letter:uppercase"
                >
                  {group}
                </h3>
              )}
              <ul className="divide-y divide-dotted divide-line">
                {items.map(({ ingredient, index }) => {
                  const key = ingredientKey(ingredient, index)
                  const inputId = `${baseId}-item-${index}`
                  const shown = scaleIngredient(ingredient, factor)
                  const amount = ingredientAmount(shown)
                  const note = ingredientNote(shown, { scaled: factor !== 1 })
                  const isChecked = checked.has(key)
                  return (
                    <li key={index} className="print:break-inside-avoid">
                      <label
                        htmlFor={inputId}
                        className="flex min-h-11 cursor-pointer items-start gap-3 rounded-md px-1 py-2.5 transition-colors hover:bg-paper-deep print:min-h-0 print:py-1"
                      >
                        <input
                          id={inputId}
                          type="checkbox"
                          checked={isChecked}
                          onChange={() => toggle(key)}
                          className="ingredient-check mt-1 size-5 shrink-0 cursor-pointer accent-terracotta"
                        />
                        <span
                          className={`transition-colors ${isChecked ? 'text-ink-soft line-through decoration-terracotta/60' : ''}`}
                        >
                          {amount && (
                            <>
                              <span className="amount font-semibold">{amount}</span>{' '}
                            </>
                          )}
                          <span>{ingredient.name}</span>
                          {/* Sem quantidade, o motivo ("a gosto", "para fritar") vem na nota. */}
                          {note && <span className="text-ink-soft">, {note}</span>}
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
      <div className="mt-3 flex min-h-11 flex-wrap items-center gap-x-4 gap-y-1 text-sm text-ink-soft print:hidden">
        <p aria-live="polite">
          {checked.size === 0
            ? 'Marque o que já separou.'
            : `${checked.size} de ${ingredients.length} separados.`}
        </p>
        {checked.size > 0 && (
          <button
            type="button"
            className="link inline-flex min-h-11 items-center"
            onClick={clearAll}
          >
            Limpar marcações
          </button>
        )}
      </div>
    </div>
  )
}
