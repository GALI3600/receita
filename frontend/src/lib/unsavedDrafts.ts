// Alterações ainda não salvas (rascunho do editor e notas), guardadas na aba (sessionStorage)
// enquanto há o que salvar. Se a sessão expira no meio da edição, a página troca para o login e o
// editor some; depois de entrar de novo, a receita reabre com o que a pessoa tinha digitado.

import { CHECKED_PREFIX } from './checkedIngredients'
import {
  DIFFICULTIES,
  newKey,
  type IngredientDraft,
  type RecipeDraft,
  type StepDraft,
} from './recipeDraft'
import { readJson, removeByPrefix, writeStorage } from './storage'

const DRAFT_PREFIX = 'receita:rascunho:'
const NOTES_PREFIX = 'receita:nota:'

interface Stored {
  userId: string
  value: unknown
}

function isStored(value: unknown): value is Stored {
  return (
    typeof value === 'object' &&
    value !== null &&
    typeof (value as Stored).userId === 'string' &&
    'value' in value
  )
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function hasStrings(value: unknown, fields: string[]): value is Record<string, string> {
  return isRecord(value) && fields.every((field) => typeof value[field] === 'string')
}

const INGREDIENT_FIELDS = ['name', 'quantity', 'unit', 'note', 'group']

function isRecipeDraft(value: unknown): value is RecipeDraft {
  if (!hasStrings(value, ['title', 'summary', 'servings', 'prepTime', 'cookTime'])) return false
  const draft = value as unknown as Record<string, unknown>
  const difficulty = draft.difficulty
  return (
    (difficulty === '' || (DIFFICULTIES as unknown[]).includes(difficulty)) &&
    Array.isArray(draft.ingredients) &&
    draft.ingredients.every((item) => hasStrings(item, INGREDIENT_FIELDS)) &&
    Array.isArray(draft.steps) &&
    draft.steps.every((step) => hasStrings(step, ['text', 'time'])) &&
    Array.isArray(draft.tips) &&
    draft.tips.every((tip) => hasStrings(tip, ['text'])) &&
    Array.isArray(draft.tags) &&
    draft.tags.every((tag) => typeof tag === 'string')
  )
}

function load(key: string, userId: string | undefined): unknown {
  if (!userId) return null
  const stored = readJson(key, isStored, 'session')
  return stored && stored.userId === userId ? stored.value : null
}

function save(key: string, userId: string, value: unknown) {
  writeStorage(key, JSON.stringify({ userId, value }), 'session')
}

// --- Rascunho do editor ---------------------------------------------------------------------

export function saveRecipeDraft(userId: string, recipeId: string, draft: RecipeDraft) {
  save(DRAFT_PREFIX + recipeId, userId, draft)
}

/**
 * Rascunho guardado desta receita (só o da mesma conta), ou null. As linhas ganham chaves novas:
 * as guardadas vieram de outra carga da página e podem repetir as que o editor vai criar.
 */
export function loadRecipeDraft(userId: string | undefined, recipeId: string): RecipeDraft | null {
  const value = load(DRAFT_PREFIX + recipeId, userId)
  if (!isRecipeDraft(value)) return null
  return {
    ...value,
    ingredients: value.ingredients.map((item): IngredientDraft => ({
      key: newKey('ing'),
      name: item.name,
      quantity: item.quantity,
      unit: item.unit,
      note: item.note,
      group: item.group,
    })),
    steps: value.steps.map((step): StepDraft => ({
      key: newKey('passo'),
      text: step.text,
      time: step.time,
    })),
    tips: value.tips.map((tip) => ({ key: newKey('dica'), text: tip.text })),
    tags: [...value.tags],
  }
}

export function clearRecipeDraft(recipeId: string) {
  writeStorage(DRAFT_PREFIX + recipeId, null, 'session')
}

// --- Notas -----------------------------------------------------------------------------------

export function saveNotesDraft(userId: string, recipeId: string, text: string) {
  save(NOTES_PREFIX + recipeId, userId, text)
}

export function loadNotesDraft(userId: string | undefined, recipeId: string): string | null {
  const value = load(NOTES_PREFIX + recipeId, userId)
  return typeof value === 'string' ? value : null
}

export function clearNotesDraft(recipeId: string) {
  writeStorage(NOTES_PREFIX + recipeId, null, 'session')
}

/**
 * Esquece o que a conta deixou neste navegador (rascunhos e marcações de ingredientes), ao sair
 * da conta ou excluí-la: num computador compartilhado, nada das receitas fica para trás.
 */
export function forgetLocalUserData() {
  removeByPrefix(CHECKED_PREFIX, 'local')
  removeByPrefix(DRAFT_PREFIX, 'session')
  removeByPrefix(NOTES_PREFIX, 'session')
}
