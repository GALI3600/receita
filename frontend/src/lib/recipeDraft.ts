// Modelo do formulário de edição da receita: rascunho (texto livre em cada campo), validação com
// os mesmos limites do backend (app/schemas/recipes.py, RecipeUpdate) e tradução dos erros 422.

import type { Difficulty, FieldError, Recipe, RecipeUpdate } from '../api/types'
import { formatTimestamp } from './format'
import { charCount } from './text'

export const LIMITS = {
  title: 200,
  summary: 1000,
  servings: 100,
  minutes: 48 * 60,
  ingredients: 100,
  ingredientField: 200,
  steps: 100,
  stepText: 2000,
  tips: 30,
  tipText: 500,
  tags: 20,
  tagText: 40,
} as const

export const DIFFICULTIES: Difficulty[] = ['fácil', 'média', 'difícil']

export interface IngredientDraft {
  key: string
  name: string
  quantity: string
  unit: string
  note: string
  group: string
}

export interface StepDraft {
  key: string
  text: string
  /** Tempo no vídeo como a pessoa digita: "1:53", "1:02:05" ou vazio. */
  time: string
}

export interface TipDraft {
  key: string
  text: string
}

export interface RecipeDraft {
  title: string
  summary: string
  servings: string
  prepTime: string
  cookTime: string
  difficulty: Difficulty | ''
  ingredients: IngredientDraft[]
  steps: StepDraft[]
  tips: TipDraft[]
  tags: string[]
}

let keyCounter = 0
/** Chave estável de uma linha do formulário (a ordem muda ao reordenar). */
export function newKey(prefix: string): string {
  keyCounter += 1
  return `${prefix}-${keyCounter}`
}

export function emptyIngredient(group = ''): IngredientDraft {
  return { key: newKey('ing'), name: '', quantity: '', unit: '', note: '', group }
}

export function emptyStep(): StepDraft {
  return { key: newKey('passo'), text: '', time: '' }
}

export function emptyTip(): TipDraft {
  return { key: newKey('dica'), text: '' }
}

export function toDraft(recipe: Recipe): RecipeDraft {
  return {
    title: recipe.title,
    summary: recipe.summary,
    servings: recipe.servings ?? '',
    prepTime: recipe.prep_time_min === null ? '' : String(recipe.prep_time_min),
    cookTime: recipe.cook_time_min === null ? '' : String(recipe.cook_time_min),
    difficulty: recipe.difficulty ?? '',
    ingredients: recipe.ingredients.map((ingredient) => ({
      key: newKey('ing'),
      name: ingredient.name,
      quantity: ingredient.quantity ?? '',
      unit: ingredient.unit ?? '',
      note: ingredient.note ?? '',
      group: ingredient.group ?? '',
    })),
    steps: recipe.steps.map((step) => ({
      key: newKey('passo'),
      text: step.text,
      time: step.video_timestamp_s === null ? '' : formatTimestamp(step.video_timestamp_s),
    })),
    tips: recipe.tips.map((text) => ({ key: newKey('dica'), text })),
    tags: [...recipe.tags],
  }
}

/** O rascunho sem as chaves das linhas: dois rascunhos iguais aqui não têm o que salvar. */
function comparable(draft: RecipeDraft) {
  return {
    ...draft,
    ingredients: draft.ingredients.map(({ key: _key, ...rest }) => rest),
    steps: draft.steps.map(({ key: _key, ...rest }) => rest),
    tips: draft.tips.map((tip) => tip.text),
  }
}

export function isDraftDirty(initial: RecipeDraft, current: RecipeDraft): boolean {
  return JSON.stringify(comparable(initial)) !== JSON.stringify(comparable(current))
}

// --- Tempo do vídeo -----------------------------------------------------------------------------

/**
 * "1:53" → 113, "1:02:05" → 3725, "0:07" → 7; vazio → null. Devolve undefined se o texto não
 * estiver no formato minutos:segundos.
 */
export function parseTimestamp(text: string): number | null | undefined {
  const value = text.trim()
  if (!value) return null
  let match = /^(\d{1,3}):([0-5]\d)$/.exec(value)
  if (match) return Number(match[1]) * 60 + Number(match[2])
  match = /^(\d{1,2}):([0-5]\d):([0-5]\d)$/.exec(value)
  if (match) return Number(match[1]) * 3600 + Number(match[2]) * 60 + Number(match[3])
  return undefined
}

// --- Tags ----------------------------------------------------------------------------------------

/** Como o backend guarda as tags: sem "#", sem espaços nas pontas, em minúsculas. */
export function normalizeTag(tag: string): string {
  return tag.trim().replace(/^#+/, '').trim().toLowerCase()
}

/** Junta tags novas (digitadas com vírgula) às existentes, sem repetir. */
export function addTags(current: string[], typed: string): string[] {
  const next = [...current]
  for (const part of typed.split(',')) {
    const tag = normalizeTag(part)
    if (tag && !next.includes(tag)) next.push(tag)
  }
  return next
}

// --- Validação e envio ------------------------------------------------------------------------

/**
 * Erros por campo. Chaves: "title", "summary", "servings", "prepTime", "cookTime",
 * "difficulty", "ingredients", "steps", "tips", "tags", e por linha
 * "ingredients.<key>.<campo>", "steps.<key>.text", "steps.<key>.time", "tips.<key>",
 * "tags.<índice>"; "form" para o que não tem campo.
 */
export type DraftErrors = Record<string, string>

export interface DraftPayload {
  body: RecipeUpdate
  /** Linha do rascunho de cada item enviado (as linhas vazias não vão). */
  ingredientKeys: string[]
  stepKeys: string[]
  tipKeys: string[]
}

function tooLong(limit: number): string {
  return `Use no máximo ${limit} caracteres.`
}

function parseMinutes(text: string): number | null | undefined {
  const value = text.trim()
  if (!value) return null
  if (!/^\d+$/.test(value)) return undefined
  return Number(value)
}

function isBlankIngredient(item: IngredientDraft): boolean {
  return [item.name, item.quantity, item.unit, item.note, item.group].every((v) => !v.trim())
}

/**
 * Valida o rascunho com os limites do backend e monta o PATCH. Linhas totalmente vazias
 * (ingrediente, passo ou dica) são ignoradas em vez de virar erro.
 */
export function validateDraft(
  draft: RecipeDraft,
  { videoDuration }: { videoDuration?: number } = {},
): { errors: DraftErrors; payload: DraftPayload | null } {
  const errors: DraftErrors = {}

  const title = draft.title.trim()
  if (!title) errors.title = 'Dê um nome à receita.'
  else if (charCount(title) > LIMITS.title) errors.title = tooLong(LIMITS.title)

  const summary = draft.summary.trim()
  if (charCount(summary) > LIMITS.summary) errors.summary = tooLong(LIMITS.summary)

  const servings = draft.servings.trim()
  if (charCount(servings) > LIMITS.servings) errors.servings = tooLong(LIMITS.servings)

  const minutes: Record<'prepTime' | 'cookTime', number | null> = { prepTime: null, cookTime: null }
  for (const field of ['prepTime', 'cookTime'] as const) {
    const value = parseMinutes(draft[field])
    if (value === undefined) errors[field] = 'Use só números (minutos).'
    else if (value !== null && value > LIMITS.minutes)
      errors[field] = `No máximo ${LIMITS.minutes} minutos (48 horas).`
    else minutes[field] = value
  }

  const ingredients = draft.ingredients.filter((item) => !isBlankIngredient(item))
  if (ingredients.length > LIMITS.ingredients) {
    errors.ingredients = `No máximo ${LIMITS.ingredients} ingredientes.`
  }
  for (const item of ingredients) {
    if (!item.name.trim()) errors[`ingredients.${item.key}.name`] = 'Diga qual é o ingrediente.'
    for (const field of ['name', 'quantity', 'unit', 'note', 'group'] as const) {
      if (charCount(item[field].trim()) > LIMITS.ingredientField) {
        errors[`ingredients.${item.key}.${field}`] = tooLong(LIMITS.ingredientField)
      }
    }
  }

  const steps = draft.steps.filter((step) => step.text.trim() || step.time.trim())
  if (steps.length > LIMITS.steps) errors.steps = `No máximo ${LIMITS.steps} passos.`
  const stepTimes = new Map<string, number | null>()
  for (const step of steps) {
    const text = step.text.trim()
    if (!text) errors[`steps.${step.key}.text`] = 'Escreva o que fazer neste passo.'
    else if (charCount(text) > LIMITS.stepText)
      errors[`steps.${step.key}.text`] = tooLong(LIMITS.stepText)
    const seconds = parseTimestamp(step.time)
    if (seconds === undefined) {
      errors[`steps.${step.key}.time`] = 'Use minutos:segundos, como 1:53.'
    } else if (seconds !== null && videoDuration && seconds > videoDuration) {
      errors[`steps.${step.key}.time`] =
        `O vídeo tem ${formatTimestamp(videoDuration)}; use um tempo até aí.`
    } else {
      stepTimes.set(step.key, seconds)
    }
  }

  const tips = draft.tips.filter((tip) => tip.text.trim())
  if (tips.length > LIMITS.tips) errors.tips = `No máximo ${LIMITS.tips} dicas.`
  for (const tip of tips) {
    if (charCount(tip.text.trim()) > LIMITS.tipText)
      errors[`tips.${tip.key}`] = tooLong(LIMITS.tipText)
  }

  const tags = draft.tags.map(normalizeTag).filter(Boolean)
  if (tags.length > LIMITS.tags) errors.tags = `No máximo ${LIMITS.tags} tags.`
  tags.forEach((tag, index) => {
    if (charCount(tag) > LIMITS.tagText) errors[`tags.${index}`] = tooLong(LIMITS.tagText)
  })

  if (Object.keys(errors).length > 0) return { errors, payload: null }

  const optional = (value: string) => value.trim() || null
  return {
    errors,
    payload: {
      body: {
        title,
        summary,
        servings: servings || null,
        prep_time_min: minutes.prepTime,
        cook_time_min: minutes.cookTime,
        difficulty: draft.difficulty || null,
        ingredients: ingredients.map((item) => ({
          name: item.name.trim(),
          quantity: optional(item.quantity),
          unit: optional(item.unit),
          note: optional(item.note),
          group: optional(item.group),
        })),
        steps: steps.map((step) => ({
          text: step.text.trim(),
          video_timestamp_s: stepTimes.get(step.key) ?? null,
        })),
        tips: tips.map((tip) => tip.text.trim()),
        tags,
      },
      ingredientKeys: ingredients.map((item) => item.key),
      stepKeys: steps.map((step) => step.key),
      tipKeys: tips.map((tip) => tip.key),
    },
  }
}

// --- Erros do servidor (422) --------------------------------------------------------------------

/** Mensagem em português para um erro de validação do backend (as do Pydantic vêm em inglês). */
export function translateFieldError(detail: FieldError): string {
  const limit = /(\d+)/.exec(detail.message)?.[1]
  switch (detail.type) {
    case 'missing':
    case 'string_too_short':
      return 'Preencha este campo.'
    case 'string_too_long':
      return limit ? tooLong(Number(limit)) : 'Texto longo demais.'
    case 'too_long':
      return limit ? `No máximo ${limit} itens.` : 'Itens demais.'
    case 'greater_than_equal':
      return limit ? `Use um valor a partir de ${limit}.` : 'Valor pequeno demais.'
    case 'less_than_equal':
      return limit ? `Use um valor até ${limit}.` : 'Valor grande demais.'
    case 'int_parsing':
    case 'int_type':
    case 'int_from_float':
      return 'Use um número inteiro.'
    case 'literal_error':
    case 'enum':
      return 'Escolha uma das opções.'
    case 'value_error':
      return detail.message.replace(/^Value error,\s*/i, '')
    default:
      return 'Valor inválido.'
  }
}

const TOP_FIELDS: Record<string, string> = {
  title: 'title',
  summary: 'summary',
  servings: 'servings',
  prep_time_min: 'prepTime',
  cook_time_min: 'cookTime',
  difficulty: 'difficulty',
  ingredients: 'ingredients',
  steps: 'steps',
  tips: 'tips',
  tags: 'tags',
}

/** Leva os erros do 422 (campo "body.ingredients.3.name") para as linhas do rascunho. */
export function serverErrorsToDraft(details: FieldError[], payload: DraftPayload): DraftErrors {
  const errors: DraftErrors = {}
  for (const detail of details) {
    const parts = detail.field.split('.')
    if (parts[0] === 'body') parts.shift()
    const [field, rawIndex, sub] = parts
    const message = translateFieldError(detail)
    const index = Number(rawIndex)
    let key: string | null = null
    if (field === 'ingredients' && Number.isInteger(index) && payload.ingredientKeys[index]) {
      key = `ingredients.${payload.ingredientKeys[index]}.${sub ?? 'name'}`
    } else if (field === 'steps' && Number.isInteger(index) && payload.stepKeys[index]) {
      key = `steps.${payload.stepKeys[index]}.${sub === 'video_timestamp_s' ? 'time' : 'text'}`
    } else if (field === 'tips' && Number.isInteger(index) && payload.tipKeys[index]) {
      key = `tips.${payload.tipKeys[index]}`
    } else if (field === 'tags' && Number.isInteger(index)) {
      key = `tags.${index}`
    } else if (field && TOP_FIELDS[field]) {
      key = TOP_FIELDS[field]
    }
    const target = key ?? 'form'
    if (!errors[target]) errors[target] = message
  }
  return errors
}
