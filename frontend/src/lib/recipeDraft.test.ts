import { describe, expect, it } from 'vitest'

import { makeRecipe } from '../test/fixtures'
import {
  addTags,
  emptyIngredient,
  emptyStep,
  emptyTip,
  isDraftDirty,
  normalizeTag,
  parseTimestamp,
  serverErrorsToDraft,
  toDraft,
  translateFieldError,
  validateDraft,
  type RecipeDraft,
} from './recipeDraft'

function draft(overrides: Partial<RecipeDraft> = {}): RecipeDraft {
  return { ...toDraft(makeRecipe()), ...overrides }
}

describe('parseTimestamp', () => {
  it.each([
    ['', null],
    ['  ', null],
    ['0:00', 0],
    ['0:07', 7],
    ['1:53', 113],
    ['12:05', 725],
    ['1:02:05', 3725],
    [' 2:30 ', 150],
  ])('"%s" → %s', (text, expected) => {
    expect(parseTimestamp(text)).toBe(expected)
  })

  it.each(['90', '1:5', '1:60', 'abc', '1:30s', '-1:00', '1:00:60'])('"%s" é inválido', (text) => {
    expect(parseTimestamp(text)).toBeUndefined()
  })
})

describe('tags', () => {
  it('normaliza como o backend', () => {
    expect(normalizeTag('  #Sobremesa ')).toBe('sobremesa')
    expect(normalizeTag('##Air Fryer')).toBe('air fryer')
  })

  it('junta tags digitadas com vírgula, sem repetir', () => {
    expect(addTags(['bolo'], 'Doce, #bolo, , festa')).toEqual(['bolo', 'doce', 'festa'])
  })
})

describe('toDraft e isDraftDirty', () => {
  it('converte a receita em texto editável', () => {
    const value = toDraft(makeRecipe())
    expect(value.prepTime).toBe('20')
    expect(value.steps.map((step) => step.time)).toEqual(['0:00', '1:53', ''])
    expect(value.ingredients[3]).toMatchObject({ name: 'sal', quantity: '', unit: '' })
    expect(value.tips.map((tip) => tip.text)).toEqual(['Teste o fermento antes.'])
  })

  it('só fica "sujo" quando o conteúdo muda (as chaves das linhas não contam)', () => {
    const recipe = makeRecipe()
    const a = toDraft(recipe)
    const b = toDraft(recipe)
    expect(isDraftDirty(a, b)).toBe(false)
    expect(isDraftDirty(a, { ...b, title: 'Outro' })).toBe(true)
    expect(isDraftDirty(a, { ...b, steps: [...b.steps].reverse() })).toBe(true)
  })
})

describe('validateDraft', () => {
  it('monta o PATCH com todos os campos editáveis', () => {
    const { errors, payload } = validateDraft(draft({ difficulty: '', servings: ' ' }))
    expect(errors).toEqual({})
    expect(payload?.body).toMatchObject({
      title: 'Bolo de cenoura com calda',
      servings: null,
      prep_time_min: 20,
      cook_time_min: 40,
      difficulty: null,
      tips: ['Teste o fermento antes.'],
      tags: ['bolo', 'sobremesa'],
    })
    expect(payload?.body.ingredients?.[3]).toEqual({
      name: 'sal',
      quantity: null,
      unit: null,
      note: null,
      group: 'massa',
    })
    expect(payload?.body.steps).toEqual([
      { text: 'Preaqueça o forno a 180 °C.', video_timestamp_s: 0 },
      { text: 'Bata as cenouras com os ovos.', video_timestamp_s: 113 },
      { text: 'Sirva com a calda.', video_timestamp_s: null },
    ])
  })

  it('ignora linhas totalmente vazias', () => {
    const base = draft()
    const { payload } = validateDraft({
      ...base,
      ingredients: [...base.ingredients, emptyIngredient()],
      steps: [...base.steps, emptyStep()],
      tips: [...base.tips, emptyTip()],
    })
    expect(payload?.body.ingredients).toHaveLength(4)
    expect(payload?.body.steps).toHaveLength(3)
    expect(payload?.body.tips).toHaveLength(1)
    expect(payload?.ingredientKeys).toEqual(base.ingredients.map((item) => item.key))
  })

  it('aponta os erros por campo e por linha', () => {
    const base = draft()
    const ingredient = { ...emptyIngredient(), quantity: '2' }
    const step = { ...emptyStep(), time: '1:5' }
    const longTip = { ...emptyTip(), text: 'x'.repeat(501) }
    const { errors, payload } = validateDraft({
      ...base,
      title: '  ',
      summary: 'x'.repeat(1001),
      prepTime: 'dez',
      cookTime: '3000',
      ingredients: [ingredient],
      steps: [step],
      tips: [longTip],
      tags: ['x'.repeat(41)],
    })
    expect(payload).toBeNull()
    expect(errors).toEqual({
      title: 'Dê um nome à receita.',
      summary: 'Use no máximo 1000 caracteres.',
      prepTime: 'Use só números (minutos).',
      cookTime: 'No máximo 2880 minutos (48 horas).',
      [`ingredients.${ingredient.key}.name`]: 'Diga qual é o ingrediente.',
      [`steps.${step.key}.text`]: 'Escreva o que fazer neste passo.',
      [`steps.${step.key}.time`]: 'Use minutos:segundos, como 1:53.',
      [`tips.${longTip.key}`]: 'Use no máximo 500 caracteres.',
      'tags.0': 'Use no máximo 40 caracteres.',
    })
  })

  it('não aceita tempo depois do fim do vídeo', () => {
    const base = draft()
    const step = { ...base.steps[0], time: '9:00' }
    const { errors } = validateDraft({ ...base, steps: [step] }, { videoDuration: 533 })
    expect(errors[`steps.${step.key}.time`]).toBe('O vídeo tem 8:53; use um tempo até aí.')
  })

  it('limita a quantidade de itens', () => {
    const base = draft()
    const many = Array.from({ length: 101 }, () => ({ ...emptyIngredient(), name: 'sal' }))
    const tags = Array.from({ length: 21 }, (_, i) => `tag${i}`)
    const { errors } = validateDraft({ ...base, ingredients: many, tags })
    expect(errors.ingredients).toBe('No máximo 100 ingredientes.')
    expect(errors.tags).toBe('No máximo 20 tags.')
  })
})

describe('limites contados como o backend (code points)', () => {
  it('emoji conta um caractere, não dois', () => {
    const base = draft()
    const title = '🍫'.repeat(150)
    expect(title.length).toBe(300)
    const ok = validateDraft({ ...base, title, tags: ['🍰'.repeat(40)] })
    expect(ok.errors).toEqual({})
    expect(ok.payload?.body.title).toBe(title)

    const tooLong = validateDraft({ ...base, title: '🍫'.repeat(201), tags: ['🍰'.repeat(41)] })
    expect(tooLong.errors.title).toBe('Use no máximo 200 caracteres.')
    expect(tooLong.errors['tags.0']).toBe('Use no máximo 40 caracteres.')
  })
})

describe('erros do servidor', () => {
  it('traduz as mensagens do Pydantic', () => {
    expect(
      translateFieldError({
        field: 'body.title',
        type: 'string_too_long',
        message: 'String should have at most 200 characters',
      }),
    ).toBe('Use no máximo 200 caracteres.')
    expect(
      translateFieldError({
        field: 'body.prep_time_min',
        type: 'less_than_equal',
        message: 'Input should be less than or equal to 2880',
      }),
    ).toBe('Use um valor até 2880.')
    expect(
      translateFieldError({
        field: 'body',
        type: 'value_error',
        message: "Value error, o campo 'title' não pode ser nulo",
      }),
    ).toBe("o campo 'title' não pode ser nulo")
    expect(translateFieldError({ field: 'x', type: 'outro', message: '?' })).toBe('Valor inválido.')
  })

  it('leva cada erro para a linha certa do rascunho', () => {
    const payload = {
      body: {},
      ingredientKeys: ['ing-a', 'ing-b'],
      stepKeys: ['passo-a'],
      tipKeys: ['dica-a'],
    }
    const errors = serverErrorsToDraft(
      [
        { field: 'body.title', type: 'string_too_short', message: '' },
        { field: 'body.ingredients.1.unit', type: 'string_too_long', message: 'at most 200' },
        { field: 'body.steps.0.video_timestamp_s', type: 'greater_than_equal', message: '0' },
        { field: 'body.tips.0', type: 'string_too_long', message: 'at most 500' },
        { field: 'body.tags.2', type: 'string_too_long', message: 'at most 40' },
        { field: 'body.cook_time_min', type: 'int_parsing', message: '' },
        { field: 'body', type: 'value_error', message: 'Value error, outro problema' },
      ],
      payload,
    )
    expect(errors).toEqual({
      title: 'Preencha este campo.',
      'ingredients.ing-b.unit': 'Use no máximo 200 caracteres.',
      'steps.passo-a.time': 'Use um valor a partir de 0.',
      'tips.dica-a': 'Use no máximo 500 caracteres.',
      'tags.2': 'Use no máximo 40 caracteres.',
      cookTime: 'Use um número inteiro.',
      form: 'outro problema',
    })
  })
})
