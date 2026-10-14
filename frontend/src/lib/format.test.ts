import { describe, expect, it } from 'vitest'

import type { Ingredient } from '../api/types'
import { ingredientAmount, ingredientNote } from './format'

function ingredient(overrides: Partial<Ingredient> = {}): Ingredient {
  return { name: 'farinha', quantity: null, unit: null, note: null, group: null, ...overrides }
}

describe('ingredientAmount', () => {
  it.each([
    [{ quantity: '2', unit: 'xícaras' }, '2 xícaras'],
    [{ quantity: '3' }, '3'],
    [{ quantity: ' 1/2 ', unit: ' xícara ' }, '1/2 xícara'],
    [{}, null],
    [{ quantity: ' ' }, null],
    // Sem quantidade a unidade não é medida: vai para a nota, não para o negrito.
    [{ unit: 'fatias' }, null],
    [{ quantity: '', unit: 'fatias', note: 'a gosto' }, null],
  ])('%o → %s', (fields, expected) => {
    expect(ingredientAmount(ingredient(fields))).toBe(expected)
  })
})

describe('ingredientNote', () => {
  it.each([
    [{}, null],
    [{ note: '  ' }, null],
    [{ note: 'a gosto' }, 'a gosto'],
    [{ note: 'para fritar' }, 'para fritar'],
    [{ quantity: '2', unit: 'xícaras', note: 'peneirada' }, 'peneirada'],
    // Receitas antigas, de antes da normalização no backend.
    [{ unit: 'fatias' }, 'fatias'],
    [{ unit: 'fatias', note: 'finas' }, 'fatias, finas'],
    [{ quantity: '1', unit: 'xícara', note: '(1⅓ xícara)' }, '1⅓ xícara'],
    [{ note: ', picada' }, 'picada'],
    // Parênteses só no meio ficam.
    [{ note: 'picada (opcional)' }, 'picada (opcional)'],
    [{ note: '(grande) (madura)' }, '(grande) (madura)'],
    // Igual ao grupo só repete o título da seção (8uYzXzUHvYY: "pão…, fatias, para servir").
    [{ note: 'para servir', group: 'para servir' }, null],
    [{ note: ' Para Servir ', group: 'para servir ' }, null],
    [{ unit: 'fatias', note: 'para servir', group: 'para servir' }, 'fatias'],
    [{ note: 'para servir', group: 'recheio' }, 'para servir'],
  ])('%o → %s', (fields, expected) => {
    expect(ingredientNote(ingredient(fields))).toBe(expected)
  })
})

describe('ingredientNote com porções mudadas', () => {
  it.each([
    // A equivalência vale para a quantidade original: sai quando a receita é escalada.
    [{ quantity: '400', unit: 'g', note: '≈ 1⅓ xícara' }, null],
    [{ quantity: '200', unit: 'g', note: 'em pedaços, ≈ 7 oz' }, 'em pedaços'],
    [{ quantity: '1', unit: 'xícara', note: '(≈ 240 ml)' }, null],
    // O modelo também separa as partes com ";" (ZU_wbPigVRI).
    [
      { quantity: '180', unit: 'g', note: '≈ ¾ xícara; + 10 a 20 g para ajustar o ponto' },
      '+ 10 a 20 g para ajustar o ponto',
    ],
    [{ quantity: '1', unit: 'pacote', note: 'pacote de 1,5 kg, ≈ 10 xícaras' }, 'pacote de 1,5 kg'],
    // Tamanho não é equivalência: fica.
    [{ quantity: '1', unit: 'copo', note: 'copo de 300 ml' }, 'copo de 300 ml'],
    [{ note: 'a gosto' }, 'a gosto'],
  ])('%o → %s', (fields, expected) => {
    expect(ingredientNote(ingredient(fields), { scaled: true })).toBe(expected)
  })

  it('mantém a equivalência na quantidade original', () => {
    expect(ingredientNote(ingredient({ quantity: '400', unit: 'g', note: '≈ 1⅓ xícara' }))).toBe(
      '≈ 1⅓ xícara',
    )
  })
})
