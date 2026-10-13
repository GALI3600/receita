/** Chave pública do Cloudflare Turnstile; sem ela o cadastro não mostra captcha. */
export const TURNSTILE_SITE_KEY: string | undefined =
  import.meta.env.VITE_TURNSTILE_SITE_KEY || undefined
