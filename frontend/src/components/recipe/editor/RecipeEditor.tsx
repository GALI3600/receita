import { useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react'

import { isApiError } from '../../../api/client'
import { useUpdateRecipe } from '../../../api/queries'
import type { Recipe } from '../../../api/types'
import { describeError } from '../../../lib/errors'
import {
  LIMITS,
  isDraftDirty,
  serverErrorsToDraft,
  toDraft,
  validateDraft,
  type DraftErrors,
  type RecipeDraft,
} from '../../../lib/recipeDraft'
import { charCount } from '../../../lib/text'
import { clearRecipeDraft, saveRecipeDraft } from '../../../lib/unsavedDrafts'
import { useSession } from '../../../session/context'
import { ConfirmDialog } from '../../ConfirmDialog'
import { UnsavedChangesGuard } from '../../UnsavedChangesGuard'
import { Alert } from '../../ui'
import { TextArea, TextInput } from './fields'
import { fieldId, focusField } from './formUtils'
import { IngredientsEditor, StepsEditor, TipsEditor } from './ListEditors'

/** Texto do resumo de erros para cada chave (a ordem segue a do formulário). */
function errorLabel(key: string, draft: RecipeDraft): string {
  const simple: Record<string, string> = {
    title: 'Título',
    summary: 'Resumo',
    servings: 'Rendimento',
    prepTime: 'Tempo de preparo',
    cookTime: 'Tempo de forno/fogo',
    difficulty: 'Dificuldade',
    ingredients: 'Ingredientes',
    steps: 'Modo de preparo',
    tips: 'Dicas',
    tags: 'Tags',
    form: 'Receita',
  }
  if (simple[key]) return simple[key]
  const [list, rowKey, field] = key.split('.')
  if (list === 'ingredients') {
    const index = draft.ingredients.findIndex((item) => item.key === rowKey)
    const names: Record<string, string> = {
      name: 'nome',
      quantity: 'quantidade',
      unit: 'unidade',
      note: 'observação',
      group: 'grupo',
    }
    return `Ingrediente ${index + 1}, ${names[field] ?? field}`
  }
  if (list === 'steps') {
    const index = draft.steps.findIndex((item) => item.key === rowKey)
    return `Passo ${index + 1}, ${field === 'time' ? 'tempo no vídeo' : 'texto'}`
  }
  if (list === 'tips') {
    return `Dica ${draft.tips.findIndex((item) => item.key === rowKey) + 1}`
  }
  if (list === 'tags') return `Tag “${draft.tags[Number(rowKey)] ?? ''}”`
  return 'Receita'
}

/** Campo que recebe o foco para corrigir o erro `key`. */
function errorTarget(key: string): string {
  if (key.startsWith('tags.')) return fieldId('tags-nova')
  if (key === 'form') return 'editar-resumo-erros'
  return fieldId(key)
}

function orderedErrorKeys(errors: DraftErrors): string[] {
  // A ordem dos campos na página: os de cima primeiro.
  const order = ['form', 'title', 'summary', 'servings', 'prepTime', 'cookTime', 'difficulty']
  const lists = ['ingredients', 'steps', 'tips', 'tags']
  const keys = Object.keys(errors)
  const rank = (key: string) => {
    const top = order.indexOf(key)
    if (top >= 0) return top
    const list = lists.indexOf(key.split('.')[0])
    return order.length + (list >= 0 ? list : lists.length)
  }
  return keys
    .map((key, index) => ({ key, index }))
    .sort((a, b) => rank(a.key) - rank(b.key) || a.index - b.index)
    .map(({ key }) => key)
}

function Section({ title, id, children }: { title: string; id: string; children: ReactNode }) {
  return (
    <section aria-labelledby={id} className="border-t border-line pt-6">
      <h2 id={id} className="mb-4 text-2xl font-semibold">
        {title}
      </h2>
      {children}
    </section>
  )
}

interface RecipeEditorProps {
  recipe: Recipe
  /** Alterações não salvas recuperadas (a sessão tinha expirado no meio da edição). */
  restored?: RecipeDraft | null
  /** Fecha o editor; `saved` diz se as alterações foram gravadas. */
  onClose: (saved: boolean) => void
}

/** Modo de edição da receita: todos os campos, com validação e aviso ao sair sem salvar. */
export function RecipeEditor({ recipe, restored = null, onClose }: RecipeEditorProps) {
  const userId = useSession().user?.id
  const [initial] = useState(() => toDraft(recipe))
  const [draft, setDraft] = useState(() => restored ?? initial)
  const [errors, setErrors] = useState<DraftErrors>({})
  const [announcement, setAnnouncement] = useState('')
  const [confirmingCancel, setConfirmingCancel] = useState(false)
  const update = useUpdateRecipe(recipe.id)
  const summaryRef = useRef<HTMLDivElement>(null)
  const actionsRef = useRef<HTMLDivElement>(null)
  const dirty = isDraftDirty(initial, draft)
  const errorKeys = orderedErrorKeys(errors)

  // O rascunho fica guardado na aba enquanto há o que salvar: se a sessão expirar (o 401 troca a
  // página pelo login e desmonta o editor), a receita reabre com ele depois de entrar de novo.
  useEffect(() => {
    if (!userId) return
    if (dirty && !update.isSuccess) saveRecipeDraft(userId, recipe.id, draft)
    else clearRecipeDraft(recipe.id)
  }, [draft, dirty, update.isSuccess, userId, recipe.id])

  // A altura da barra fixa de ações vira o scroll-padding-bottom da página (index.css): o campo
  // que recebe o foco pelo teclado nunca fica escondido atrás dela (no celular ela quebra linha).
  useEffect(() => {
    const bar = actionsRef.current
    const root = document.documentElement
    if (!bar) return
    const measure = () =>
      root.style.setProperty('--editor-actions-height', `${bar.getBoundingClientRect().height}px`)
    measure()
    if (typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(measure)
    observer.observe(bar)
    return () => {
      observer.disconnect()
      root.style.removeProperty('--editor-actions-height')
    }
  }, [])

  function close(saved: boolean) {
    clearRecipeDraft(recipe.id)
    onClose(saved)
  }

  function change(patch: Partial<RecipeDraft>) {
    setDraft((current) => ({ ...current, ...patch }))
  }

  function announce(message: string) {
    // Repetir a mesma frase também precisa ser anunciado.
    setAnnouncement('')
    requestAnimationFrame(() => setAnnouncement(message))
  }

  function showErrors(next: DraftErrors) {
    setErrors(next)
    requestAnimationFrame(() => summaryRef.current?.focus())
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault()
    if (update.isPending) return
    const { errors: found, payload } = validateDraft(draft, {
      videoDuration: recipe.video.duration_s || undefined,
    })
    if (!payload) {
      showErrors(found)
      return
    }
    setErrors({})
    update.mutate(payload.body, {
      onSuccess: () => close(true),
      onError: (error) => {
        if (isApiError(error) && error.status === 422 && error.details?.length) {
          showErrors(serverErrorsToDraft(error.details, payload))
        } else {
          showErrors({ form: describeError(error) })
        }
      },
    })
  }

  function onCancel() {
    if (dirty) setConfirmingCancel(true)
    else close(false)
  }

  return (
    <>
      {/* Diálogos e anúncios fora do <form>: o space-y dele mexeria na margem do <dialog>. */}
      <UnsavedChangesGuard
        when={dirty && !update.isSuccess}
        onLeave={() => clearRecipeDraft(recipe.id)}
      />
      <ConfirmDialog
        open={confirmingCancel}
        title="Descartar as alterações?"
        confirmLabel="Descartar"
        cancelLabel="Continuar editando"
        tone="danger"
        onConfirm={() => {
          setConfirmingCancel(false)
          close(false)
        }}
        onCancel={() => setConfirmingCancel(false)}
      >
        O que você mudou nesta receita ainda não foi salvo.
      </ConfirmDialog>
      <p className="sr-only" aria-live="polite">
        {announcement}
      </p>

      <form
        onSubmit={onSubmit}
        noValidate
        aria-labelledby="editar-titulo-pagina"
        className="space-y-8"
      >
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="eyebrow">Editando</p>
            <h1 id="editar-titulo-pagina" className="mt-1 text-3xl font-semibold sm:text-4xl">
              {recipe.title}
            </h1>
          </div>
        </div>

        {restored && (
          <Alert tone="warning" title="Recuperamos as alterações que você não tinha salvado.">
            Confira e clique em “Salvar alterações”, ou em “Cancelar” para descartá-las.
          </Alert>
        )}

        {errorKeys.length > 0 && (
          <div
            ref={summaryRef}
            id="editar-resumo-erros"
            tabIndex={-1}
            role="alert"
            className="rounded-lg border border-danger/40 bg-danger-tint px-4 py-3"
          >
            <p className="font-semibold">
              {errorKeys.length === 1
                ? 'Falta corrigir um campo antes de salvar:'
                : `Falta corrigir ${errorKeys.length} campos antes de salvar:`}
            </p>
            <ul className="mt-1 list-disc space-y-0.5 pl-5">
              {errorKeys.map((key) => (
                <li key={key}>
                  {key === 'form' ? (
                    errors[key]
                  ) : (
                    <a
                      href={`#${errorTarget(key)}`}
                      className="link font-normal"
                      onClick={(event) => {
                        event.preventDefault()
                        focusField(errorTarget(key))
                      }}
                    >
                      {errorLabel(key, draft)}: {errors[key]}
                    </a>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}

        <section aria-labelledby="editar-sobre" className="space-y-4">
          <h2 id="editar-sobre" className="sr-only">
            Sobre a receita
          </h2>
          <TextInput
            fieldKey="title"
            label="Título"
            value={draft.title}
            error={errors.title}
            onChange={(e) => change({ title: e.target.value })}
            autoComplete="off"
            className="max-w-3xl"
          />
          <TextArea
            fieldKey="summary"
            label="Resumo"
            value={draft.summary}
            error={errors.summary}
            onChange={(e) => change({ summary: e.target.value })}
            hint={`${charCount(draft.summary.trim())} de ${LIMITS.summary} caracteres.`}
            className="max-w-3xl"
          />
          <div className="grid max-w-3xl gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <TextInput
              fieldKey="servings"
              label="Rendimento"
              value={draft.servings}
              error={errors.servings}
              onChange={(e) => change({ servings: e.target.value })}
              placeholder="6 porções"
              hint="Com um número, dá para ajustar as porções."
              autoComplete="off"
            />
            <TextInput
              fieldKey="prepTime"
              label="Preparo (min)"
              value={draft.prepTime}
              error={errors.prepTime}
              onChange={(e) => change({ prepTime: e.target.value })}
              inputMode="numeric"
              autoComplete="off"
            />
            <TextInput
              fieldKey="cookTime"
              label="Forno/fogo (min)"
              value={draft.cookTime}
              error={errors.cookTime}
              onChange={(e) => change({ cookTime: e.target.value })}
              inputMode="numeric"
              autoComplete="off"
            />
          </div>
        </section>

        <Section title="Ingredientes" id="editar-ingredientes">
          <IngredientsEditor
            items={draft.ingredients}
            errors={errors}
            onChange={(ingredients) => change({ ingredients })}
            announce={announce}
          />
        </Section>

        <Section title="Modo de preparo" id="editar-passos">
          <StepsEditor
            items={draft.steps}
            errors={errors}
            onChange={(steps) => change({ steps })}
            announce={announce}
          />
        </Section>

        <Section title="Dicas" id="editar-dicas">
          <TipsEditor
            items={draft.tips}
            errors={errors}
            onChange={(tips) => change({ tips })}
            announce={announce}
          />
        </Section>

        {/* Ações sempre à vista no fim da tela enquanto se edita. */}
        <div
          ref={actionsRef}
          className="editor-actions sticky bottom-0 z-10 -mx-3 flex flex-wrap items-center justify-end gap-2 border-t border-line bg-card/95 px-3 py-3 backdrop-blur sm:-mx-8 sm:px-8 lg:-mx-12 lg:px-12"
        >
          <p className="mr-auto text-sm text-ink-soft" aria-live="polite">
            {update.isPending ? 'Salvando…' : dirty ? 'Alterações não salvas' : 'Nada alterado'}
          </p>
          <button
            type="button"
            className="btn-secondary"
            onClick={onCancel}
            disabled={update.isPending}
          >
            Cancelar
          </button>
          <button type="submit" className="btn-primary" disabled={update.isPending}>
            {update.isPending ? 'Salvando…' : 'Salvar alterações'}
          </button>
        </div>
      </form>
    </>
  )
}
