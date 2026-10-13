import { act, renderHook } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { Ingredient } from '../api/types'
import {
  checkedStorageKey,
  ingredientKey,
  loadChecked,
  useCheckedIngredients,
} from './checkedIngredients'
import { readJson, readStorage, writeStorage } from './storage'

const ingredients: Ingredient[] = [
  { name: 'farinha', quantity: '2', unit: 'xícaras', note: null, group: null },
  { name: 'ovos', quantity: '3', unit: null, note: null, group: null },
]

describe('storage', () => {
  it('lê e grava, e JSON inválido vira null', () => {
    writeStorage('k', '["a"]')
    expect(readStorage('k')).toBe('["a"]')
    expect(readJson('k', Array.isArray)).toEqual(['a'])
    writeStorage('k', '{quebrado')
    expect(readJson('k', Array.isArray)).toBeNull()
    writeStorage('k', null)
    expect(readStorage('k')).toBeNull()
  })
})

describe('useCheckedIngredients', () => {
  it('marca, guarda por receita e limpa', () => {
    const { result } = renderHook(() => useCheckedIngredients('r1', ingredients))
    act(() => result.current.toggle(ingredientKey(ingredients[1], 1)))
    expect([...result.current.checked]).toEqual(['1:ovos'])
    expect([...loadChecked('r1')]).toEqual(['1:ovos'])
    expect(loadChecked('r2').size).toBe(0)

    act(() => result.current.toggle('1:ovos'))
    expect(result.current.checked.size).toBe(0)
    act(() => result.current.toggle('0:farinha'))
    act(() => result.current.clear())
    expect(localStorage.getItem(checkedStorageKey('r1'))).toBeNull()
  })

  it('troca de receita relê as marcações dela', () => {
    localStorage.setItem(checkedStorageKey('r2'), JSON.stringify(['0:farinha']))
    const { result, rerender } = renderHook(({ id }) => useCheckedIngredients(id, ingredients), {
      initialProps: { id: 'r1' },
    })
    expect(result.current.checked.size).toBe(0)
    rerender({ id: 'r2' })
    expect([...result.current.checked]).toEqual(['0:farinha'])
  })

  it('acompanha mudanças feitas em outra aba', () => {
    const { result } = renderHook(() => useCheckedIngredients('r1', ingredients))
    act(() => {
      localStorage.setItem(checkedStorageKey('r1'), JSON.stringify(['1:ovos']))
      window.dispatchEvent(new StorageEvent('storage', { key: checkedStorageKey('r1') }))
    })
    expect([...result.current.checked]).toEqual(['1:ovos'])
  })

  it('ignora dados guardados com formato errado', () => {
    localStorage.setItem(checkedStorageKey('r1'), JSON.stringify({ a: 1 }))
    const { result } = renderHook(() => useCheckedIngredients('r1', ingredients))
    expect(result.current.checked.size).toBe(0)
  })
})
