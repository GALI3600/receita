import { useEffect, useImperativeHandle, useRef, type Ref } from 'react'

interface TurnstileApi {
  render: (
    element: HTMLElement,
    options: {
      sitekey: string
      callback: (token: string) => void
      'expired-callback'?: () => void
      'error-callback'?: () => void
      language?: string
      theme?: 'light' | 'dark' | 'auto'
    },
  ) => string
  reset: (widgetId: string) => void
  remove: (widgetId: string) => void
}

type TurnstileWindow = Window & { turnstile?: TurnstileApi }

const SCRIPT_SRC = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit'

let scriptPromise: Promise<TurnstileApi> | null = null

function loadTurnstile(): Promise<TurnstileApi> {
  const win = window as TurnstileWindow
  if (win.turnstile) return Promise.resolve(win.turnstile)
  scriptPromise ??= new Promise((resolve, reject) => {
    const script = document.createElement('script')
    script.src = SCRIPT_SRC
    script.async = true
    script.onload = () => (win.turnstile ? resolve(win.turnstile) : reject(new Error('turnstile')))
    script.onerror = () => {
      scriptPromise = null
      script.remove()
      reject(new Error('Não foi possível carregar o captcha'))
    }
    document.head.appendChild(script)
  })
  return scriptPromise
}

export interface TurnstileHandle {
  reset: () => void
}

/** Widget do Turnstile (só é montado quando há VITE_TURNSTILE_SITE_KEY). */
export function Turnstile({
  siteKey,
  onToken,
  onError,
  ref,
}: {
  siteKey: string
  onToken: (token: string | null) => void
  onError?: () => void
  ref?: Ref<TurnstileHandle>
}) {
  const containerRef = useRef<HTMLDivElement>(null)
  const widgetId = useRef<string | null>(null)
  const callbacks = useRef({ onToken, onError })
  useEffect(() => {
    callbacks.current = { onToken, onError }
  })

  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    let cancelled = false
    loadTurnstile()
      .then((api) => {
        if (cancelled) return
        widgetId.current = api.render(container, {
          sitekey: siteKey,
          language: 'pt-br',
          theme: 'light',
          callback: (token) => callbacks.current.onToken(token),
          'expired-callback': () => callbacks.current.onToken(null),
          'error-callback': () => {
            callbacks.current.onToken(null)
            callbacks.current.onError?.()
          },
        })
      })
      .catch(() => {
        if (!cancelled) callbacks.current.onError?.()
      })
    return () => {
      cancelled = true
      const api = (window as TurnstileWindow).turnstile
      if (api && widgetId.current) api.remove(widgetId.current)
      widgetId.current = null
    }
  }, [siteKey])

  useImperativeHandle(ref, () => ({
    reset() {
      const api = (window as TurnstileWindow).turnstile
      if (api && widgetId.current) api.reset(widgetId.current)
      callbacks.current.onToken(null)
    },
  }))

  return <div ref={containerRef} className="min-h-[65px]" />
}
