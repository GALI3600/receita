const IFRAME_API_SRC = 'https://www.youtube.com/iframe_api'

type YouTubeWindow = Window & {
  YT?: typeof YT
  onYouTubeIframeAPIReady?: () => void
}

let apiPromise: Promise<typeof YT> | null = null

/**
 * Carrega a YouTube IFrame Player API uma única vez por página e devolve o namespace `YT`.
 * Chamadas simultâneas recebem a mesma promise; se o script falhar, a próxima tenta de novo.
 */
export function loadYouTubeApi(): Promise<typeof YT> {
  const win = window as YouTubeWindow
  if (win.YT?.Player) return Promise.resolve(win.YT)
  if (apiPromise) return apiPromise

  apiPromise = new Promise<typeof YT>((resolve, reject) => {
    const previousCallback = win.onYouTubeIframeAPIReady
    win.onYouTubeIframeAPIReady = () => {
      previousCallback?.()
      if (win.YT?.Player) resolve(win.YT)
      else reject(new Error('YouTube IFrame API carregou sem YT.Player'))
    }
    const script = document.createElement('script')
    script.src = IFRAME_API_SRC
    script.async = true
    script.onerror = () => {
      apiPromise = null
      script.remove()
      reject(new Error('Não foi possível carregar a YouTube IFrame API'))
    }
    document.head.appendChild(script)
  })
  return apiPromise
}

/** Só para testes: esquece a promise em cache. */
export function resetYouTubeApiForTests() {
  apiPromise = null
}
