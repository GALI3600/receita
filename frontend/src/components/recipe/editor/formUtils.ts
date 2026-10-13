// Utilidades do formulário de edição (ids, foco e reordenação das linhas).

/** id do campo do formulário de edição a partir da chave do erro ("ingredients.ing-3.name"). */
export function fieldId(key: string): string {
  return `editar-${key.replace(/[^\w-]/g, '-')}`
}

/** Foca um campo depois que a lista re-renderizou (linha nova, linha movida). */
export function focusField(id: string) {
  requestAnimationFrame(() => {
    const element = document.getElementById(id)
    element?.focus()
  })
}

/** Move o item `index` uma posição para cima (-1) ou para baixo (+1). */
export function moveItem<T>(list: T[], index: number, delta: -1 | 1): T[] {
  const target = index + delta
  if (target < 0 || target >= list.length) return list
  const next = [...list]
  ;[next[index], next[target]] = [next[target], next[index]]
  return next
}
