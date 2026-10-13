import { describe, expect, it } from 'vitest'

import {
  agreeUnit,
  firstAmount,
  formatAmount,
  hasAmount,
  parseNumber,
  parseServings,
  scaleIngredient,
  scaleServings,
  scaleText,
} from './quantity'

describe('parseNumber', () => {
  it.each([
    ['2', 2, 'integer'],
    ['200', 200, 'integer'],
    ['1,5', 1.5, 'decimal'],
    ['1.5', 1.5, 'decimal'],
    ['0,25', 0.25, 'decimal'],
    ['1.000', 1000, 'integer'],
    ['12.500', 12500, 'integer'],
    ['1/2', 0.5, 'fraction'],
    ['3 / 4', 0.75, 'fraction'],
    ['1 1/2', 1.5, 'fraction'],
    ['1 e 1/2', 1.5, 'fraction'],
    ['2 e 3/4', 2.75, 'fraction'],
    ['½', 0.5, 'fraction'],
    ['1½', 1.5, 'fraction'],
    ['1 ½', 1.5, 'fraction'],
    ['2 e ¼', 2.25, 'fraction'],
  ])('%s → %d (%s)', (raw, value, style) => {
    const parsed = parseNumber(raw)
    expect(parsed?.value).toBeCloseTo(value)
    expect(parsed?.style).toBe(style)
  })

  it.each(['', 'a gosto', '1/0', '2 1/0', 'meia', '1,', ',5'])('"%s" não é número', (raw) => {
    expect(parseNumber(raw)).toBeNull()
  })
})

describe('formatAmount', () => {
  it.each([
    [0, '0'],
    [1, '1'],
    [2, '2'],
    [0.5, '1/2'],
    [0.25, '1/4'],
    [0.75, '3/4'],
    [1 / 3, '1/3'],
    [2 / 3, '2/3'],
    [0.125, '1/8'],
    [0.375, '3/8'],
    [1.5, '1 1/2'],
    [2.25, '2 1/4'],
    [3.6666, '3 2/3'],
    [1.98, '2'],
    [0.99, '1'],
    [1.2, '1,2'],
    [0.02, '0,02'],
    [10.4, '10 1/2'],
    [10.2, '10'],
    [12.5, '12 1/2'],
    [133.333, '133'],
    [1500, '1.500'],
  ])('%d → "%s"', (value, expected) => {
    expect(formatAmount(value)).toBe(expected)
  })

  it('no estilo decimal usa vírgula e até duas casas', () => {
    expect(formatAmount(2.25, 'decimal')).toBe('2,25')
    expect(formatAmount(3, 'decimal')).toBe('3')
    expect(formatAmount(1 / 3, 'decimal')).toBe('0,33')
    expect(formatAmount(0.75, 'decimal')).toBe('0,75')
  })

  it('valores inválidos viram texto vazio', () => {
    expect(formatAmount(Number.NaN)).toBe('')
    expect(formatAmount(-1)).toBe('')
  })
})

describe('scaleText', () => {
  it.each([
    // inteiros
    ['2', 2, '4'],
    ['3', 0.5, '1 1/2'],
    ['4', 0.5, '2'],
    ['1', 3, '3'],
    ['200', 1.5, '300'],
    ['250', 1 / 3, '83'],
    // decimais com vírgula (ficam decimais)
    ['1,5', 2, '3'],
    ['1,5', 1.5, '2,25'],
    ['0,5', 3, '1,5'],
    ['1.5', 2, '3'],
    // frações
    ['1/2', 2, '1'],
    ['1/2', 3, '1 1/2'],
    ['3/4', 2, '1 1/2'],
    ['1/3', 2, '2/3'],
    ['2/3', 1.5, '1'],
    ['1/4', 0.5, '1/8'],
    ['1 1/2', 2, '3'],
    ['1 e 1/2', 2, '3'],
    ['1 e 1/2', 0.5, '3/4'],
    ['½', 2, '1'],
    ['1½', 2, '3'],
    // faixas
    ['2-3', 2, '4-6'],
    ['2 - 3', 2, '4 - 6'],
    ['2–3', 2, '4–6'],
    ['2 a 3', 2, '4 a 6'],
    ['1/2 a 1', 2, '1 a 2'],
    ['3 ou 4', 0.5, '1 1/2 ou 2'],
    // número com texto em volta
    ['200g', 2, '400g'],
    ['1 lata (395 g)', 2, '2 lata (790 g)'],
    ['cerca de 2', 2, 'cerca de 4'],
    ['1.000', 2, '2.000'],
  ])('"%s" × %d → "%s"', (text, factor, expected) => {
    expect(scaleText(text, factor).text).toBe(expected)
  })

  it.each(['a gosto', 'q.b.', 'uma pitada', 'meia xícara', ''])('"%s" fica intacto', (text) => {
    expect(scaleText(text, 2)).toEqual({ text, before: null, after: null })
  })

  it('com fator 1 devolve o texto original, sem reformatar', () => {
    expect(scaleText('1 e 1/2', 1).text).toBe('1 e 1/2')
    expect(scaleText('0,50', 1).text).toBe('0,50')
  })

  it('não confunde números colados em letras', () => {
    expect(scaleText('x2', 2).text).toBe('x2')
    expect(scaleText('ovos tipo A2', 3).text).toBe('ovos tipo A2')
  })

  it('devolve o primeiro valor antes e depois (o maior da faixa)', () => {
    expect(scaleText('2-3', 2)).toEqual({ text: '4-6', before: 3, after: 6 })
    expect(scaleText('1/2', 4)).toEqual({ text: '2', before: 0.5, after: 2 })
  })

  it('com firstOnly só a primeira quantidade muda', () => {
    expect(scaleText('1 forma de 20 cm', 2, { firstOnly: true }).text).toBe('2 forma de 20 cm')
    expect(scaleText('1 forma de 20 cm', 2).text).toBe('2 forma de 40 cm')
  })

  it('uma fração com denominador zero vale só como texto', () => {
    expect(scaleText('1/0', 2).text).toBe('1/0')
  })
})

describe('agreeUnit', () => {
  it.each([
    ['xícara', 1, 2, 'xícaras'],
    ['xícara (chá)', 0.5, 2, 'xícaras (chá)'],
    ['xícaras', 2, 1, 'xícara'],
    ['xícaras (chá)', 2, 1.5, 'xícara (chá)'],
    ['colher de sopa', 1, 3, 'colheres de sopa'],
    ['colheres de sopa', 3, 1, 'colher de sopa'],
    ['pitada', 1, 2, 'pitadas'],
    ['dentes', 4, 1, 'dente'],
    ['porção', 1, 4, 'porções'],
    ['porções', 4, 1, 'porção'],
    ['unidades', 6, 1, 'unidade'],
  ])('%s (%d → %d) → %s', (unit, before, after, expected) => {
    expect(agreeUnit(unit, before, after)).toBe(expected)
  })

  it('não mexe quando o número continua singular ou plural', () => {
    expect(agreeUnit('xícara', 1, 1.5)).toBe('xícara')
    expect(agreeUnit('xícaras', 2, 4)).toBe('xícaras')
  })

  it('não mexe em abreviações nem palavras curtas', () => {
    expect(agreeUnit('g', 1, 2)).toBe('g')
    expect(agreeUnit('ml', 1, 2)).toBe('ml')
    expect(agreeUnit('kg', 2, 1)).toBe('kg')
    expect(agreeUnit('copo', 1, 2)).toBe('copos')
  })

  it('sem número antes ou depois, fica igual', () => {
    expect(agreeUnit('xícara', null, 2)).toBe('xícara')
  })
})

describe('scaleIngredient', () => {
  const base = { name: 'farinha', note: null, group: null }

  it('escala a quantidade e concorda a unidade', () => {
    expect(scaleIngredient({ ...base, quantity: '1', unit: 'xícara' }, 2)).toEqual({
      ...base,
      quantity: '2',
      unit: 'xícaras',
    })
    expect(scaleIngredient({ ...base, quantity: '3', unit: 'colheres de sopa' }, 1 / 3)).toEqual({
      ...base,
      quantity: '1',
      unit: 'colher de sopa',
    })
  })

  it('mantém "a gosto" e quantidades sem número', () => {
    const toTaste = { ...base, quantity: null, unit: null }
    expect(scaleIngredient(toTaste, 2)).toBe(toTaste)
    const words = { ...base, quantity: 'uma pitada', unit: null }
    expect(scaleIngredient(words, 2)).toBe(words)
  })

  it('com fator 1 devolve o mesmo objeto', () => {
    const item = { ...base, quantity: '1 e 1/2', unit: 'xícara' }
    expect(scaleIngredient(item, 1)).toBe(item)
  })
})

describe('rendimento', () => {
  it.each([
    ['6 unidades', 6],
    ['4 porções', 4],
    ['4 a 6 porções', 4],
    ['Rende 12 fatias', 12],
    ['1 bolo', 1],
    ['1,5 litro', 1.5],
  ])('parseServings("%s") = %d', (text, expected) => {
    expect(parseServings(text)).toBe(expected)
  })

  it.each([null, undefined, '', 'uma travessa', 'serve bem a família', '0 porções'])(
    'parseServings(%s) = null',
    (text) => {
      expect(parseServings(text)).toBeNull()
    },
  )

  it.each([
    ['6 unidades', 12, '12 unidades'],
    ['6 unidades', 1, '1 unidade'],
    ['6 unidades', 6, '6 unidades'],
    ['4 porções', 1, '1 porção'],
    ['1 bolo', 2, '2 bolos'],
    ['1 forma de 20 cm', 2, '2 formas de 20 cm'],
    ['4 a 6 porções', 8, '8 a 12 porções'],
    ['Rende 12 fatias', 6, 'Rende 6 fatias'],
    ['8', 4, '4'],
  ])('scaleServings("%s", %d) = "%s"', (text, count, expected) => {
    expect(scaleServings(text, count)).toBe(expected)
  })

  it('sem número o rendimento fica igual', () => {
    expect(scaleServings('uma travessa', 3)).toBe('uma travessa')
  })

  it('hasAmount e firstAmount', () => {
    expect(hasAmount('2 a 3')).toBe(true)
    expect(hasAmount('a gosto')).toBe(false)
    expect(hasAmount(null)).toBe(false)
    expect(firstAmount('1/2 xícara')).toBe(0.5)
  })
})
