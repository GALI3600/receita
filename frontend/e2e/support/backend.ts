import { execFileSync, spawnSync } from 'node:child_process'

import type { APIRequestContext } from '@playwright/test'

// Acesso ao backend do Docker Compose para o que só existe no servidor: o link de confirmação
// (o backend de e-mail "console" escreve no log da API) e o seed de desenvolvimento.
const PROJECT = process.env.COMPOSE_PROJECT ?? 'receita'

function container(service: string): string {
  const id = execFileSync(
    'docker',
    [
      'ps',
      '-q',
      '--filter',
      `label=com.docker.compose.project=${PROJECT}`,
      '--filter',
      `label=com.docker.compose.service=${service}`,
    ],
    { encoding: 'utf8' },
  )
    .trim()
    .split('\n')[0]
  if (!id) throw new Error(`container do serviço "${service}" não está rodando`)
  return id
}

/** Log da API (stdout + stderr) desde `since` (ISO 8601). */
export function apiLogs(since: string): string {
  const result = spawnSync('docker', ['logs', '--since', since, container('api')], {
    encoding: 'utf8',
    maxBuffer: 64 * 1024 * 1024,
  })
  if (result.status !== 0) throw new Error(`docker logs falhou: ${result.stderr}`)
  return `${result.stdout}\n${result.stderr}`
}

function escapeRegExp(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

/** Espera o e-mail de confirmação de `email` aparecer no log e devolve o link. */
export async function verificationLink(email: string, since: string): Promise<string> {
  const pattern = new RegExp(
    `para ${escapeRegExp(email)}: Confirme seu e-mail[\\s\\S]*?(https?://\\S+/verificar-email\\?token=[\\w.-]+)`,
    'g',
  )
  for (let attempt = 0; attempt < 40; attempt++) {
    const matches = [...apiLogs(since).matchAll(pattern)]
    if (matches.length) return matches[matches.length - 1][1]
    await new Promise((resolve) => setTimeout(resolve, 500))
  }
  throw new Error(`link de confirmação para ${email} não apareceu no log da API`)
}

/** `python -m app.cli seed-demo --email <email>` no container da API. */
export function seedDemo(email: string): string {
  return execFileSync(
    'docker',
    ['exec', container('api'), 'python', '-m', 'app.cli', 'seed-demo', '--email', email],
    { encoding: 'utf8' },
  )
}

/** Zera os contadores de rate limit (cadastro/login por IP) para a suíte poder rodar de novo. */
export function resetRateLimits() {
  execFileSync('docker', [
    'exec',
    container('redis'),
    'sh',
    '-c',
    "redis-cli --scan --pattern 'receita:rate:*' | xargs -r redis-cli del > /dev/null",
  ])
}

export function uniqueEmail(prefix = 'e2e'): string {
  return `${prefix}+${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`
}

export const PASSWORD = 'senha-de-teste-e2e'
const CSRF = { 'X-Requested-With': 'playwright' }

/**
 * Conta pronta pela API: cadastro, confirmação pelo link do log, login (o cookie fica no
 * contexto do `request`) e, se pedido, as receitas de demonstração.
 */
export async function createVerifiedUser(
  request: APIRequestContext,
  { seed = false, name = 'Ana Teste' }: { seed?: boolean; name?: string } = {},
): Promise<{ email: string; seedOutput?: string }> {
  const email = uniqueEmail()
  const since = new Date(Date.now() - 2000).toISOString()
  const register = await request.post('/api/auth/register', {
    headers: CSRF,
    data: { name, email, password: PASSWORD },
  })
  if (register.status() !== 202) throw new Error(`cadastro: ${register.status()}`)
  const link = await verificationLink(email, since)
  const token = new URL(link).searchParams.get('token')
  const verify = await request.post('/api/auth/verify', { headers: CSRF, data: { token } })
  if (verify.status() !== 204) throw new Error(`verificação: ${verify.status()}`)
  const login = await request.post('/api/auth/login', {
    headers: CSRF,
    data: { email, password: PASSWORD },
  })
  if (!login.ok()) throw new Error(`login: ${login.status()}`)
  return { email, seedOutput: seed ? seedDemo(email) : undefined }
}
