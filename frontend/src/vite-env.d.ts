/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Chave pública do Cloudflare Turnstile; vazia desliga o captcha no cadastro. */
  readonly VITE_TURNSTILE_SITE_KEY?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
