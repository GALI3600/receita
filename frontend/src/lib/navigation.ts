export const DEFAULT_AFTER_LOGIN = '/livro'

const AUTH_PATHS = ['/entrar', '/cadastro']

/** Caminho interno: uma barra, sem "//" no começo, sem barra invertida nem controle. */
function isInternalPath(path: string): boolean {
  if (!path.startsWith('/') || path.startsWith('//')) return false
  // eslint-disable-next-line no-control-regex
  return !/[\\\u0000-\u001f\u007f]/.test(path)
}

/**
 * Valida o `next` de /entrar?next=... para evitar open redirect: só caminhos internos
 * (começam com uma barra, sem "//", sem barra invertida nem caracteres de controle).
 * Devolve o caminho normalizado ou `fallback`. As regras valem também para o resultado
 * normalizado: "/.//host" ou "/%2e//host" viram "//host" depois de resolver "." e "..".
 */
export function safeNext(
  next: string | null | undefined,
  fallback: string = DEFAULT_AFTER_LOGIN,
): string {
  if (!next || next.length > 2000) return fallback
  if (!isInternalPath(next)) return fallback
  let url: URL
  try {
    const base = 'https://receita.invalid'
    url = new URL(next, base)
    if (url.origin !== base) return fallback
  } catch {
    return fallback
  }
  if (AUTH_PATHS.includes(url.pathname)) return fallback
  const path = `${url.pathname}${url.search}${url.hash}`
  return isInternalPath(path) ? path : fallback
}

/** Monta /entrar?next=<caminho atual> para mandar quem não está logado de volta depois. */
export function loginPath(next?: string): string {
  const target = next ? safeNext(next, '') : ''
  return target ? `/entrar?next=${encodeURIComponent(target)}` : '/entrar'
}
