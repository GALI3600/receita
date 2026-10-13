import { useEffect, useImperativeHandle, useRef, useState, type Ref } from 'react'

import { youtubeThumbnail, youtubeWatchUrl } from '../../lib/format'
import { Spinner } from '../ui'
import { loadYouTubeApi } from './loadYouTubeApi'

/** O que a página da receita pode fazer com o player (via ref). */
export interface YouTubePlayerHandle {
  /** Pula para `seconds` e dá play; antes de o player ficar pronto, guarda o pedido. */
  seekTo: (seconds: number) => void
  /** Rola a página até o player (usado no celular, onde ele não fica fixo na tela). */
  scrollIntoView: () => void
}

type PlayerStatus = 'loading' | 'ready' | 'unavailable' | 'error'

// 100: removido/privado; 101 e 150: o dono não permite incorporar; 153: embed sem referer.
const UNAVAILABLE_ERRORS = new Set([100, 101, 150, 153])

interface YouTubePlayerProps {
  videoId: string
  title: string
  thumbnailUrl?: string | null
  ref?: Ref<YouTubePlayerHandle>
}

export function YouTubePlayer({ videoId, title, thumbnailUrl, ref }: YouTubePlayerProps) {
  const wrapperRef = useRef<HTMLDivElement>(null)
  const hostRef = useRef<HTMLDivElement>(null)
  const playerRef = useRef<YT.Player | null>(null)
  const pendingSeek = useRef<number | null>(null)
  const [status, setStatus] = useState<PlayerStatus>('loading')
  const [lastSeek, setLastSeek] = useState<number | null>(null)

  useEffect(() => {
    const host = hostRef.current
    if (!host) return
    let cancelled = false
    let player: YT.Player | null = null
    // O YT.Player troca o elemento recebido por um iframe: usamos um filho criado aqui, fora
    // do controle do React, e o removemos na limpeza (o StrictMode monta duas vezes).
    const mount = document.createElement('div')
    mount.className = 'size-full'
    host.appendChild(mount)

    loadYouTubeApi()
      .then((api) => {
        if (cancelled) return
        player = new api.Player(mount, {
          videoId,
          host: 'https://www.youtube-nocookie.com',
          width: '100%',
          height: '100%',
          playerVars: { rel: 0, playsinline: 1, origin: window.location.origin },
          events: {
            onReady: (event) => {
              if (cancelled) return
              playerRef.current = event.target
              event.target.getIframe().title = `Vídeo: ${title}`
              setStatus('ready')
              if (pendingSeek.current !== null) {
                event.target.seekTo(pendingSeek.current, true)
                event.target.playVideo()
                pendingSeek.current = null
              }
            },
            onError: (event) => {
              if (cancelled) return
              if (UNAVAILABLE_ERRORS.has(event.data)) setStatus('unavailable')
            },
          },
        })
      })
      .catch(() => {
        if (!cancelled) setStatus('error')
      })

    return () => {
      cancelled = true
      playerRef.current = null
      try {
        player?.destroy()
      } catch {
        // O iframe pode já ter saído da página.
      }
      host.replaceChildren()
    }
    // O título só nomeia o iframe; trocar o título não recria o player.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [videoId])

  useImperativeHandle(
    ref,
    () => ({
      seekTo(seconds: number) {
        setLastSeek(seconds)
        const player = playerRef.current
        if (player) {
          player.seekTo(seconds, true)
          player.playVideo()
        } else {
          pendingSeek.current = seconds
        }
      },
      scrollIntoView() {
        wrapperRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
      },
    }),
    [],
  )

  const unavailable = status === 'unavailable' || status === 'error'
  const thumbnail = thumbnailUrl || youtubeThumbnail(videoId)

  return (
    <div
      ref={wrapperRef}
      className="relative aspect-video w-full scroll-mt-4 overflow-hidden rounded-md bg-ink shadow-cover"
      data-player-status={status}
      data-last-seek={lastSeek ?? undefined}
    >
      <div ref={hostRef} className={`absolute inset-0 ${unavailable ? 'hidden' : ''}`} />
      {status === 'loading' && (
        <div className="pointer-events-none absolute inset-0">
          <img src={thumbnail} alt="" className="size-full object-cover opacity-70" />
          <div className="absolute inset-0 flex items-center justify-center" role="status">
            <span className="flex items-center gap-2 rounded-full bg-card/95 px-4 py-2 text-ink">
              <Spinner /> Carregando o vídeo…
            </span>
          </div>
        </div>
      )}
      {unavailable && (
        <div className="absolute inset-0">
          <img src={thumbnail} alt={`Capa do vídeo ${title}`} className="size-full object-cover" />
          <div className="absolute inset-0 flex items-end bg-gradient-to-t from-ink/90 via-ink/50 to-transparent p-4">
            <div className="text-white" role="status">
              <p className="font-serif text-xl font-semibold">Vídeo indisponível</p>
              <p className="text-sm text-white/90">
                {status === 'error'
                  ? 'Não conseguimos carregar o player do YouTube agora.'
                  : 'O vídeo foi removido, ficou privado ou não pode mais ser exibido aqui.'}{' '}
                A receita continua no seu livro.
              </p>
              <a
                className="mt-1 inline-block text-sm font-semibold text-white underline underline-offset-4"
                href={youtubeWatchUrl(videoId)}
                target="_blank"
                rel="noreferrer"
              >
                Tentar abrir no YouTube
              </a>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
