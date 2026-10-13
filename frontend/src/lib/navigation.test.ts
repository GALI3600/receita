import { describe, expect, it } from 'vitest'

import { DEFAULT_AFTER_LOGIN, loginPath, safeNext } from './navigation'

describe('safeNext', () => {
  it.each([
    ['/nova', '/nova'],
    ['/nova?import=abc', '/nova?import=abc'],
    ['/receitas/123#passo-2', '/receitas/123#passo-2'],
    ['/livro?q=bolo%20de%20milho&tag=doce', '/livro?q=bolo%20de%20milho&tag=doce'],
    ['/a/../conta', '/conta'],
    ['/%0a/evil', '/%0a/evil'],
  ])('aceita o caminho interno %s', (next, expected) => {
    expect(safeNext(next)).toBe(expected)
  })

  it.each([
    null,
    '',
    'https://evil.example/',
    '//evil.example',
    '///evil.example',
    '/\\evil.example',
    '\\\\evil.example',
    'javascript:alert(1)',
    'livro',
    '/\t/evil.example',
    '/entrar?next=/conta',
    '/cadastro',
    `/${'a'.repeat(3000)}`,
  ])('recusa %s', (next) => {
    expect(safeNext(next)).toBe(DEFAULT_AFTER_LOGIN)
  })

  it('usa o fallback informado', () => {
    expect(safeNext('//evil.example', '/')).toBe('/')
  })
})

describe('loginPath', () => {
  it('codifica o caminho de volta', () => {
    expect(loginPath('/nova?import=abc')).toBe('/entrar?next=%2Fnova%3Fimport%3Dabc')
    expect(loginPath('//evil.example')).toBe('/entrar')
    expect(loginPath()).toBe('/entrar')
  })
})
