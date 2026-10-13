// localStorage/sessionStorage que nunca derrubam a página: em janela anônima, com o armazenamento
// bloqueado ou cheio, ler devolve null e gravar só não acontece.

export type StorageArea = 'local' | 'session'

function area(which: StorageArea): Storage {
  return which === 'session' ? window.sessionStorage : window.localStorage
}

export function readStorage(key: string, which: StorageArea = 'local'): string | null {
  try {
    return area(which).getItem(key)
  } catch {
    return null
  }
}

export function writeStorage(key: string, value: string | null, which: StorageArea = 'local') {
  try {
    if (value === null) area(which).removeItem(key)
    else area(which).setItem(key, value)
  } catch {
    // Sem armazenamento: o dado vale só enquanto a página estiver aberta.
  }
}

export function readJson<T>(
  key: string,
  isValid: (value: unknown) => value is T,
  which: StorageArea = 'local',
): T | null {
  const raw = readStorage(key, which)
  if (raw === null) return null
  try {
    const value: unknown = JSON.parse(raw)
    return isValid(value) ? value : null
  } catch {
    return null
  }
}

/** Apaga todas as chaves que começam com `prefix`. */
export function removeByPrefix(prefix: string, which: StorageArea = 'local') {
  try {
    const storage = area(which)
    const keys: string[] = []
    for (let i = 0; i < storage.length; i++) {
      const key = storage.key(i)
      if (key?.startsWith(prefix)) keys.push(key)
    }
    for (const key of keys) storage.removeItem(key)
  } catch {
    // Sem armazenamento: não há o que apagar.
  }
}
