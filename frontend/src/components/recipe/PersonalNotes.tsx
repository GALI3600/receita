import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useId, useRef, useState } from 'react'

import { recipesApi } from '../../api/endpoints'
import { queryKeys, useUpdateRecipe } from '../../api/queries'
import type { Recipe } from '../../api/types'
import { describeError } from '../../lib/errors'
import { charCount } from '../../lib/text'
import { clearNotesDraft, loadNotesDraft, saveNotesDraft } from '../../lib/unsavedDrafts'
import { useSession } from '../../session/context'

const NOTES_MAX = 5000
const NOTES_SAVE_DELAY_MS = 1000

const timeFormat = new Intl.DateTimeFormat('pt-BR', { hour: '2-digit', minute: '2-digit' })

/** Igual ao que o backend grava: sem espaços nas pontas, vazio vira null. */
function normalize(text: string): string {
  return text.trim()
}

/**
 * Anotações pessoais da receita, salvas sozinhas um segundo depois de parar de digitar (e ao
 * sair do campo ou da página). O status ("Salvando…", "Salvo às 14:32") é anunciado. O que falta
 * salvar fica guardado na aba: se a sessão expirar antes, o texto volta depois do login.
 */
export function PersonalNotes({ recipe }: { recipe: Recipe }) {
  const id = useId()
  const client = useQueryClient()
  const userId = useSession().user?.id
  const update = useUpdateRecipe(recipe.id)
  const { mutate } = update
  const [restored] = useState(() => {
    const stored = loadNotesDraft(userId, recipe.id)
    return stored !== null && normalize(stored) !== normalize(recipe.user_notes ?? '')
      ? stored
      : null
  })
  const [text, setText] = useState(restored ?? recipe.user_notes ?? '')
  const [savedAt, setSavedAt] = useState<Date | null>(null)
  // O último texto salvo: no estado (para a tela) e num ref (para os callbacks e a limpeza).
  const [saved, setSaved] = useState(() => normalize(recipe.user_notes ?? ''))
  const savedRef = useRef(saved)
  const pendingRef = useRef<string | null>(null)
  // Último texto enviado (para o blur e o temporizador não mandarem o mesmo PATCH duas vezes).
  const sentRef = useRef<string | null>(null)
  const timerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const length = charCount(text)
  const tooLong = length > NOTES_MAX
  const dirty = normalize(text) !== saved

  useEffect(() => {
    if (!userId) return
    if (dirty) saveNotesDraft(userId, recipe.id, text)
    else clearNotesDraft(recipe.id)
  }, [text, dirty, userId, recipe.id])

  const save = useCallback(
    (value: string) => {
      const normalized = normalize(value)
      pendingRef.current = null
      if (normalized === savedRef.current || normalized === sentRef.current) return
      if (charCount(value) > NOTES_MAX) return
      sentRef.current = normalized
      mutate(
        { user_notes: normalized || null },
        {
          onSuccess: () => {
            savedRef.current = normalized
            setSaved(normalized)
            setSavedAt(new Date())
          },
          onSettled: () => {
            sentRef.current = null
          },
        },
      )
    },
    [mutate],
  )

  // Salva depois de uma pausa na digitação.
  useEffect(() => {
    if (!dirty || tooLong) return
    pendingRef.current = text
    const timer = setTimeout(() => save(text), NOTES_SAVE_DELAY_MS)
    timerRef.current = timer
    return () => clearTimeout(timer)
  }, [text, dirty, tooLong, save])

  // Saiu da página (ou do modo leitura) com algo por salvar: salva direto pela API, porque o
  // componente (e a mutation dele) já não existe quando a resposta chegar.
  useEffect(() => {
    const recipeId = recipe.id
    return () => {
      const pending = pendingRef.current
      if (pending === null) return
      const normalized = normalize(pending)
      if (normalized === savedRef.current || charCount(pending) > NOTES_MAX) return
      void recipesApi
        .update(recipeId, { user_notes: normalized || null })
        .then((saved) => {
          client.setQueryData<Recipe>(queryKeys.recipe(recipeId), (current) =>
            current ? { ...current, user_notes: saved.user_notes } : current,
          )
          // Salvo: a cópia da aba já não é necessária (a não ser que já tenha outro texto).
          const stored = loadNotesDraft(userId, recipeId)
          if (stored !== null && normalize(stored) === (saved.user_notes ?? '')) {
            clearNotesDraft(recipeId)
          }
        })
        // Falhou (a sessão expirou, sem rede): o texto continua guardado na aba.
        .catch(() => undefined)
    }
  }, [recipe.id, client, userId])

  // Fechar a aba com nota por salvar: o navegador pergunta antes.
  useEffect(() => {
    if (!dirty) return
    function onBeforeUnload(event: BeforeUnloadEvent) {
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', onBeforeUnload)
    return () => window.removeEventListener('beforeunload', onBeforeUnload)
  }, [dirty])

  let status: string
  if (tooLong) status = ''
  else if (update.isPending) status = 'Salvando…'
  else if (update.isError && dirty) status = ''
  else if (dirty && restored !== null && normalize(text) === normalize(restored))
    status = 'Recuperamos uma nota que você não tinha salvado.'
  else if (dirty) status = 'Alterações por salvar…'
  else if (savedAt) status = `Salvo às ${timeFormat.format(savedAt)}.`
  else status = 'As notas são só suas e ficam salvas sozinhas.'

  return (
    <div>
      <label htmlFor={id} className="mb-1 block font-semibold">
        Minhas notas
      </label>
      <textarea
        id={id}
        value={text}
        onChange={(event) => setText(event.target.value)}
        onBlur={() => {
          // Salva já; o temporizador da digitação não precisa mais disparar.
          clearTimeout(timerRef.current)
          if (dirty && !tooLong) save(text)
        }}
        rows={4}
        className="field-input notes-paper resize-y font-serif text-lg leading-8"
        placeholder="Ex.: usei metade do açúcar e ficou ótimo."
        aria-invalid={tooLong ? true : undefined}
        aria-describedby={`${id}-status ${id}-contagem`}
      />
      <div className="mt-1 flex flex-wrap items-start justify-between gap-x-4 text-sm">
        <p id={`${id}-status`} aria-live="polite" className="text-ink-soft">
          {status}
          {update.isError && dirty && !tooLong && (
            <span className="font-semibold text-danger">
              Não conseguimos salvar: {describeError(update.error)}{' '}
              <button
                type="button"
                className="link inline-flex min-h-11 items-center"
                onClick={() => save(text)}
              >
                Tentar de novo
              </button>
            </span>
          )}
          {tooLong && (
            <span className="font-semibold text-danger">
              As notas podem ter até {NOTES_MAX.toLocaleString('pt-BR')} caracteres.
            </span>
          )}
        </p>
        <p
          id={`${id}-contagem`}
          className={tooLong ? 'font-semibold text-danger' : 'text-ink-soft'}
        >
          {length.toLocaleString('pt-BR')}/{NOTES_MAX.toLocaleString('pt-BR')}
        </p>
      </div>
    </div>
  )
}
