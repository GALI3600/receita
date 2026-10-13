import { useId, useState } from 'react'

import {
  emptyIngredient,
  emptyStep,
  emptyTip,
  LIMITS,
  addTags,
  type DraftErrors,
  type IngredientDraft,
  type StepDraft,
  type TipDraft,
} from '../../../lib/recipeDraft'
import { RowActions, TextArea, TextInput } from './fields'
import { fieldId, focusField, moveItem } from './formUtils'

type Announce = (message: string) => void

/** Depois de mover: o foco fica no mesmo botão, ou no outro se este ficou desativado. */
function focusAfterMove(prefix: string, newIndex: number, count: number, delta: -1 | 1) {
  let button = delta === -1 ? 'subir' : 'descer'
  if (newIndex === 0) button = 'descer'
  else if (newIndex === count - 1) button = 'subir'
  if (count === 1) return
  focusField(`${prefix}-${button}`)
}

function AddButton({
  id,
  onClick,
  children,
  disabled,
}: {
  id: string
  onClick: () => void
  children: string
  disabled?: boolean
}) {
  return (
    <button
      id={id}
      type="button"
      className="btn-secondary mt-3 border-dashed"
      onClick={onClick}
      disabled={disabled}
    >
      <span aria-hidden="true" className="text-lg leading-none">
        +
      </span>
      {children}
    </button>
  )
}

function ListError({ fieldKey, error }: { fieldKey: string; error?: string }) {
  if (!error) return null
  return (
    <p id={fieldId(fieldKey)} tabIndex={-1} className="mt-2 text-sm font-semibold text-danger">
      {error}
    </p>
  )
}

// --- Ingredientes --------------------------------------------------------------------------------

export function IngredientsEditor({
  items,
  errors,
  onChange,
  announce,
}: {
  items: IngredientDraft[]
  errors: DraftErrors
  onChange: (items: IngredientDraft[]) => void
  announce: Announce
}) {
  const groupsListId = useId()
  const groups = [...new Set(items.map((item) => item.group.trim()).filter(Boolean))]

  function update(key: string, patch: Partial<IngredientDraft>) {
    onChange(items.map((item) => (item.key === key ? { ...item, ...patch } : item)))
  }

  function add() {
    const item = emptyIngredient(items.at(-1)?.group ?? '')
    onChange([...items, item])
    focusField(fieldId(`ingredients.${item.key}.quantity`))
  }

  function remove(index: number) {
    const item = items[index]
    const next = items.filter((_, i) => i !== index)
    onChange(next)
    announce(`Ingrediente ${item.name.trim() || index + 1} removido.`)
    const neighbor = next[index] ?? next[index - 1]
    focusField(neighbor ? `ingrediente-${neighbor.key}-remover` : 'editar-adicionar-ingrediente')
  }

  function move(index: number, delta: -1 | 1) {
    const next = moveItem(items, index, delta)
    onChange(next)
    const item = items[index]
    announce(`${item.name.trim() || 'Ingrediente'} movido para a posição ${index + delta + 1}.`)
    focusAfterMove(`ingrediente-${item.key}`, index + delta, next.length, delta)
  }

  return (
    <div>
      {items.length === 0 && (
        <p className="text-ink-soft">Nenhum ingrediente. Adicione o primeiro abaixo.</p>
      )}
      <ol className="space-y-3">
        {items.map((item, index) => {
          const label = `ingrediente ${index + 1}`
          const k = (field: string) => `ingredients.${item.key}.${field}`
          return (
            <li key={item.key}>
              <fieldset className="relative rounded-lg border border-line bg-paper/60 px-3 pt-1 pb-3">
                <legend className="float-left flex min-h-11 w-full items-center pr-36 font-serif font-semibold text-terracotta">
                  Ingrediente {index + 1}
                </legend>
                <div className="absolute top-0.5 right-0.5">
                  <RowActions
                    idPrefix={`ingrediente-${item.key}`}
                    itemLabel={item.name.trim() ? `${label} (${item.name.trim()})` : label}
                    index={index}
                    count={items.length}
                    onMove={(delta) => move(index, delta)}
                    onRemove={() => remove(index)}
                  />
                </div>
                <div className="clear-both grid grid-cols-2 gap-x-3 gap-y-2 sm:grid-cols-[6rem_9rem_minmax(0,1fr)]">
                  <TextInput
                    compact
                    fieldKey={k('quantity')}
                    label="Quantidade"
                    value={item.quantity}
                    error={errors[k('quantity')]}
                    onChange={(e) => update(item.key, { quantity: e.target.value })}
                    autoComplete="off"
                  />
                  <TextInput
                    compact
                    fieldKey={k('unit')}
                    label="Unidade"
                    value={item.unit}
                    error={errors[k('unit')]}
                    onChange={(e) => update(item.key, { unit: e.target.value })}
                    autoComplete="off"
                  />
                  <TextInput
                    compact
                    className="col-span-2 sm:col-span-1"
                    fieldKey={k('name')}
                    label="Ingrediente"
                    value={item.name}
                    error={errors[k('name')]}
                    onChange={(e) => update(item.key, { name: e.target.value })}
                    autoComplete="off"
                  />
                  <TextInput
                    compact
                    className="col-span-2"
                    fieldKey={k('note')}
                    label="Observação"
                    value={item.note}
                    error={errors[k('note')]}
                    onChange={(e) => update(item.key, { note: e.target.value })}
                    autoComplete="off"
                  />
                  <TextInput
                    compact
                    className="col-span-2 sm:col-span-1"
                    fieldKey={k('group')}
                    label="Grupo"
                    value={item.group}
                    error={errors[k('group')]}
                    onChange={(e) => update(item.key, { group: e.target.value })}
                    list={groupsListId}
                    autoComplete="off"
                  />
                </div>
              </fieldset>
            </li>
          )
        })}
      </ol>
      <datalist id={groupsListId}>
        {groups.map((group) => (
          <option key={group} value={group} />
        ))}
      </datalist>
      <ListError fieldKey="ingredients" error={errors.ingredients} />
      <AddButton
        id="editar-adicionar-ingrediente"
        onClick={add}
        disabled={items.length >= LIMITS.ingredients}
      >
        Adicionar ingrediente
      </AddButton>
    </div>
  )
}

// --- Passos --------------------------------------------------------------------------------------

export function StepsEditor({
  items,
  errors,
  onChange,
  announce,
}: {
  items: StepDraft[]
  errors: DraftErrors
  onChange: (items: StepDraft[]) => void
  announce: Announce
}) {
  function update(key: string, patch: Partial<StepDraft>) {
    onChange(items.map((item) => (item.key === key ? { ...item, ...patch } : item)))
  }

  function add() {
    const item = emptyStep()
    onChange([...items, item])
    focusField(fieldId(`steps.${item.key}.text`))
  }

  function remove(index: number) {
    const next = items.filter((_, i) => i !== index)
    onChange(next)
    announce(`Passo ${index + 1} removido.`)
    const neighbor = next[index] ?? next[index - 1]
    focusField(neighbor ? `passo-${neighbor.key}-remover` : 'editar-adicionar-passo')
  }

  function move(index: number, delta: -1 | 1) {
    const next = moveItem(items, index, delta)
    onChange(next)
    announce(`Passo ${index + 1} movido para a posição ${index + delta + 1}.`)
    focusAfterMove(`passo-${items[index].key}`, index + delta, next.length, delta)
  }

  return (
    <div>
      {items.length === 0 && (
        <p className="text-ink-soft">Nenhum passo. Adicione o primeiro abaixo.</p>
      )}
      <ol className="space-y-3">
        {items.map((item, index) => {
          const k = (field: string) => `steps.${item.key}.${field}`
          return (
            <li key={item.key}>
              <fieldset className="relative rounded-lg border border-line bg-paper/60 px-3 pt-1 pb-3">
                <legend className="float-left flex min-h-11 w-full items-center pr-36 font-serif font-semibold text-terracotta">
                  Passo {index + 1}
                </legend>
                <div className="absolute top-0.5 right-0.5">
                  <RowActions
                    idPrefix={`passo-${item.key}`}
                    itemLabel={`passo ${index + 1}`}
                    index={index}
                    count={items.length}
                    onMove={(delta) => move(index, delta)}
                    onRemove={() => remove(index)}
                  />
                </div>
                <div className="clear-both grid gap-x-3 gap-y-2 sm:grid-cols-[minmax(0,1fr)_8rem]">
                  <TextArea
                    compact
                    fieldKey={k('text')}
                    label="O que fazer"
                    value={item.text}
                    error={errors[k('text')]}
                    onChange={(e) => update(item.key, { text: e.target.value })}
                    rows={2}
                  />
                  <TextInput
                    compact
                    fieldKey={k('time')}
                    label="Tempo no vídeo"
                    hint="mm:ss"
                    value={item.time}
                    error={errors[k('time')]}
                    onChange={(e) => update(item.key, { time: e.target.value })}
                    inputMode="numeric"
                    autoComplete="off"
                  />
                </div>
              </fieldset>
            </li>
          )
        })}
      </ol>
      <ListError fieldKey="steps" error={errors.steps} />
      <AddButton id="editar-adicionar-passo" onClick={add} disabled={items.length >= LIMITS.steps}>
        Adicionar passo
      </AddButton>
    </div>
  )
}

// --- Dicas ---------------------------------------------------------------------------------------

export function TipsEditor({
  items,
  errors,
  onChange,
  announce,
}: {
  items: TipDraft[]
  errors: DraftErrors
  onChange: (items: TipDraft[]) => void
  announce: Announce
}) {
  function add() {
    const item = emptyTip()
    onChange([...items, item])
    focusField(fieldId(`tips.${item.key}`))
  }

  function remove(index: number) {
    const next = items.filter((_, i) => i !== index)
    onChange(next)
    announce(`Dica ${index + 1} removida.`)
    const neighbor = next[index] ?? next[index - 1]
    focusField(neighbor ? `dica-${neighbor.key}-remover` : 'editar-adicionar-dica')
  }

  return (
    <div>
      {items.length === 0 && <p className="text-ink-soft">Nenhuma dica.</p>}
      <ul className="space-y-2">
        {items.map((item, index) => (
          <li key={item.key} className="flex items-start gap-2">
            <TextArea
              compact
              className="flex-1"
              fieldKey={`tips.${item.key}`}
              label={`Dica ${index + 1}`}
              value={item.text}
              error={errors[`tips.${item.key}`]}
              onChange={(e) =>
                onChange(
                  items.map((tip) =>
                    tip.key === item.key ? { ...tip, text: e.target.value } : tip,
                  ),
                )
              }
              rows={2}
            />
            <div className="pt-6">
              <RowActions
                idPrefix={`dica-${item.key}`}
                itemLabel={`dica ${index + 1}`}
                index={index}
                count={items.length}
                onRemove={() => remove(index)}
              />
            </div>
          </li>
        ))}
      </ul>
      <ListError fieldKey="tips" error={errors.tips} />
      <AddButton id="editar-adicionar-dica" onClick={add} disabled={items.length >= LIMITS.tips}>
        Adicionar dica
      </AddButton>
    </div>
  )
}

// --- Tags ----------------------------------------------------------------------------------------

export function TagsEditor({
  tags,
  errors,
  onChange,
  announce,
}: {
  tags: string[]
  errors: DraftErrors
  onChange: (tags: string[]) => void
  announce: Announce
}) {
  const [typed, setTyped] = useState('')

  function commit() {
    if (!typed.trim()) return
    const next = addTags(tags, typed)
    const added = next.filter((tag) => !tags.includes(tag))
    onChange(next)
    setTyped('')
    if (added.length) announce(`Tag ${added.join(', ')} adicionada.`)
  }

  function remove(tag: string) {
    onChange(tags.filter((t) => t !== tag))
    announce(`Tag ${tag} removida.`)
    focusField(fieldId('tags-nova'))
  }

  const tagErrors = tags
    .map((tag, index) => ({ tag, error: errors[`tags.${index}`] }))
    .filter((item) => item.error)

  return (
    <div>
      {tags.length > 0 && (
        <ul className="mb-3 flex flex-wrap gap-2" aria-label="Tags da receita">
          {tags.map((tag) => (
            <li key={tag}>
              <span className="tag-chip gap-1 py-0 pr-0 pl-3">
                #{tag}
                {/* 36px visíveis e 44px de área de toque (::after, 4px para cada lado). */}
                <button
                  type="button"
                  onClick={() => remove(tag)}
                  className="relative inline-flex size-9 items-center justify-center rounded-full after:absolute after:-inset-1 hover:bg-danger-tint hover:text-danger"
                  aria-label={`Remover a tag ${tag}`}
                >
                  <span aria-hidden="true">×</span>
                </button>
              </span>
            </li>
          ))}
        </ul>
      )}
      <div className="flex items-start gap-2">
        <TextInput
          compact
          className="flex-1"
          fieldKey="tags-nova"
          label="Nova tag"
          value={typed}
          onChange={(e) => {
            const value = e.target.value
            // Vírgula fecha a tag na hora.
            if (value.includes(',')) {
              onChange(addTags(tags, value))
              setTyped('')
            } else setTyped(value)
          }}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault()
              commit()
            }
          }}
          hint={`Enter ou vírgula adiciona a tag. Até ${LIMITS.tags} tags.`}
          autoComplete="off"
          placeholder="sobremesa"
        />
        <button
          type="button"
          className="btn-secondary mt-6"
          onClick={commit}
          disabled={!typed.trim() || tags.length >= LIMITS.tags}
        >
          Adicionar
        </button>
      </div>
      <ListError fieldKey="tags" error={errors.tags} />
      {tagErrors.map(({ tag, error }) => (
        <p key={tag} className="mt-1 text-sm font-semibold text-danger">
          #{tag}: {error}
        </p>
      ))}
    </div>
  )
}
