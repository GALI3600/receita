import { useCallback, useEffect, useMemo, useState } from 'react'

import type { Ingredient } from '../api/types'
import { readJson, writeStorage } from './storage'

const PREFIX = 'receita:marcados:'

export function checkedStorageKey(recipeId: string): string {
  return `${PREFIX}${recipeId}`
}

/**
 * Identifica um ingrediente pela posição e pelo nome: se a receita for editada (ou restaurada),
 * marcações que não batem mais com a lista são ignoradas em vez de marcar o item errado.
 */
export function ingredientKey(ingredient: Pick<Ingredient, 'name'>, index: number): string {
  return `${index}:${ingredient.name}`
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === 'string')
}

export function loadChecked(recipeId: string): Set<string> {
  return new Set(readJson(checkedStorageKey(recipeId), isStringArray) ?? [])
}

export function saveChecked(recipeId: string, keys: Iterable<string>): void {
  const list = [...keys]
  writeStorage(checkedStorageKey(recipeId), list.length ? JSON.stringify(list) : null)
}

/** Ingredientes marcados de uma receita, guardados no navegador (sobrevivem a recarregar). */
export function useCheckedIngredients(recipeId: string, ingredients: Ingredient[]) {
  const [stored, setStored] = useState(() => ({ recipeId, keys: loadChecked(recipeId) }))
  // Outra receita na mesma página (navegação entre receitas): relê o que estava guardado.
  const current = stored.recipeId === recipeId ? stored : { recipeId, keys: loadChecked(recipeId) }
  if (current !== stored) setStored(current)

  // Marcações feitas em outra aba aparecem aqui também.
  useEffect(() => {
    function onStorage(event: StorageEvent) {
      if (event.key === checkedStorageKey(recipeId)) {
        setStored({ recipeId, keys: loadChecked(recipeId) })
      }
    }
    window.addEventListener('storage', onStorage)
    return () => window.removeEventListener('storage', onStorage)
  }, [recipeId])

  const valid = useMemo(() => new Set(ingredients.map(ingredientKey)), [ingredients])
  const checked = useMemo(
    () => new Set([...current.keys].filter((key) => valid.has(key))),
    [current.keys, valid],
  )

  const update = useCallback(
    (next: Set<string>) => {
      saveChecked(recipeId, next)
      setStored({ recipeId, keys: next })
    },
    [recipeId],
  )

  const toggle = useCallback(
    (key: string) => {
      const next = new Set(checked)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      update(next)
    },
    [checked, update],
  )

  const clear = useCallback(() => update(new Set()), [update])

  return { checked, toggle, clear }
}
