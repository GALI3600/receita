// localStorage que nunca derruba a página: em janela anônima, com o armazenamento bloqueado ou
// cheio, ler devolve null e gravar só não acontece.

export function readStorage(key: string): string | null {
  try {
    return window.localStorage.getItem(key)
  } catch {
    return null
  }
}

export function writeStorage(key: string, value: string | null): void {
  try {
    if (value === null) window.localStorage.removeItem(key)
    else window.localStorage.setItem(key, value)
  } catch {
    // Sem armazenamento: a marcação vale só enquanto a página estiver aberta.
  }
}

export function readJson<T>(key: string, isValid: (value: unknown) => value is T): T | null {
  const raw = readStorage(key)
  if (raw === null) return null
  try {
    const value: unknown = JSON.parse(raw)
    return isValid(value) ? value : null
  } catch {
    return null
  }
}
