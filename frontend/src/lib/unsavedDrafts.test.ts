import { describe, expect, it } from 'vitest'

import { makeRecipe } from '../test/fixtures'
import { checkedStorageKey } from './checkedIngredients'
import { isDraftDirty, toDraft } from './recipeDraft'
import { charCount } from './text'
import {
  clearNotesDraft,
  clearRecipeDraft,
  forgetLocalUserData,
  loadNotesDraft,
  loadRecipeDraft,
  saveNotesDraft,
  saveRecipeDraft,
} from './unsavedDrafts'

describe('rascunho do editor guardado na aba', () => {
  it('volta igual, com chaves de linha novas, e só para a mesma conta', () => {
    const draft = { ...toDraft(makeRecipe()), title: 'Bolo da vó' }
    saveRecipeDraft('user-1', 'rec-1', draft)

    const loaded = loadRecipeDraft('user-1', 'rec-1')
    expect(loaded).not.toBeNull()
    expect(isDraftDirty(draft, loaded!)).toBe(false)
    expect(loaded!.title).toBe('Bolo da vó')
    const oldKeys = draft.ingredients.map((item) => item.key)
    expect(loaded!.ingredients.some((item) => oldKeys.includes(item.key))).toBe(false)

    expect(loadRecipeDraft('user-2', 'rec-1')).toBeNull()
    expect(loadRecipeDraft(undefined, 'rec-1')).toBeNull()
    expect(loadRecipeDraft('user-1', 'rec-2')).toBeNull()

    clearRecipeDraft('rec-1')
    expect(loadRecipeDraft('user-1', 'rec-1')).toBeNull()
  })

  it('ignora o que não tem a forma de um rascunho', () => {
    window.sessionStorage.setItem('receita:rascunho:rec-1', '{quebrado')
    expect(loadRecipeDraft('user-1', 'rec-1')).toBeNull()
    window.sessionStorage.setItem(
      'receita:rascunho:rec-1',
      JSON.stringify({ userId: 'user-1', value: { title: 1 } }),
    )
    expect(loadRecipeDraft('user-1', 'rec-1')).toBeNull()
  })
})

describe('notas guardadas na aba', () => {
  it('guarda, lê e apaga por receita e conta', () => {
    saveNotesDraft('user-1', 'rec-1', 'Menos açúcar')
    expect(loadNotesDraft('user-1', 'rec-1')).toBe('Menos açúcar')
    expect(loadNotesDraft('user-2', 'rec-1')).toBeNull()
    clearNotesDraft('rec-1')
    expect(loadNotesDraft('user-1', 'rec-1')).toBeNull()
  })
})

describe('forgetLocalUserData', () => {
  it('apaga marcações e rascunhos, e mais nada', () => {
    window.localStorage.setItem(checkedStorageKey('rec-1'), '["0:sal"]')
    window.localStorage.setItem(checkedStorageKey('rec-2'), '["1:ovo"]')
    window.localStorage.setItem('outra', 'fica')
    saveRecipeDraft('user-1', 'rec-1', toDraft(makeRecipe()))
    saveNotesDraft('user-1', 'rec-1', 'nota')

    forgetLocalUserData()
    expect(window.localStorage.getItem(checkedStorageKey('rec-1'))).toBeNull()
    expect(window.localStorage.getItem(checkedStorageKey('rec-2'))).toBeNull()
    expect(window.localStorage.getItem('outra')).toBe('fica')
    expect(window.sessionStorage.length).toBe(0)
  })
})

describe('charCount', () => {
  it('conta code points, como o backend', () => {
    expect(charCount('abc')).toBe(3)
    expect(charCount('🍰')).toBe(1)
    expect('🍰'.length).toBe(2)
    expect(charCount('pão 🍞')).toBe(5)
  })
})
