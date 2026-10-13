import { render, screen, waitFor } from '@testing-library/react'
import { StrictMode, createRef } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { FakePlayer, installFakeYouTube } from '../../test/fakeYouTube'
import { YouTubePlayer, type YouTubePlayerHandle } from './YouTubePlayer'
import { loadYouTubeApi, resetYouTubeApiForTests } from './loadYouTubeApi'

describe('loadYouTubeApi', () => {
  afterEach(() => {
    document.head.querySelectorAll('script[src*="iframe_api"]').forEach((s) => s.remove())
    resetYouTubeApiForTests()
  })

  it('insere o script uma única vez e resolve quando a API avisa que está pronta', async () => {
    const first = loadYouTubeApi()
    const second = loadYouTubeApi()
    expect(first).toBe(second)
    expect(
      document.head.querySelectorAll('script[src="https://www.youtube.com/iframe_api"]'),
    ).toHaveLength(1)

    vi.stubGlobal('YT', { Player: FakePlayer })
    ;(window as unknown as { onYouTubeIframeAPIReady: () => void }).onYouTubeIframeAPIReady()

    await expect(first).resolves.toMatchObject({ Player: FakePlayer })
  })
})

describe('YouTubePlayer', () => {
  beforeEach(() => installFakeYouTube())

  it('cria o player no youtube-nocookie e destrói o da montagem descartada pelo StrictMode', async () => {
    const { unmount } = render(
      <StrictMode>
        <YouTubePlayer videoId="-pRC-FQXLEI" title="Bolo" />
      </StrictMode>,
    )

    await waitFor(() => expect(FakePlayer.active).toHaveLength(1))
    const player = FakePlayer.active[0]
    expect(player.options.videoId).toBe('-pRC-FQXLEI')
    expect(player.options.host).toBe('https://www.youtube-nocookie.com')
    expect(player.options.playerVars).toMatchObject({ playsinline: 1, rel: 0 })

    unmount()
    expect(player.destroy).toHaveBeenCalled()
    expect(FakePlayer.active).toHaveLength(0)
  })

  it('seekTo antes de ficar pronto é aplicado no onReady, e depois vai direto', async () => {
    const ref = createRef<YouTubePlayerHandle>()
    render(<YouTubePlayer ref={ref} videoId="abcdefghijk" title="Bolo" />)
    await waitFor(() => expect(FakePlayer.active).toHaveLength(1))
    const player = FakePlayer.active[0]

    ref.current?.seekTo(65)
    expect(player.seekTo).not.toHaveBeenCalled()

    player.ready()
    expect(player.seekTo).toHaveBeenCalledWith(65, true)
    expect(player.playVideo).toHaveBeenCalledTimes(1)
    expect(player.iframe.title).toBe('Vídeo: Bolo')

    ref.current?.seekTo(300)
    expect(player.seekTo).toHaveBeenLastCalledWith(300, true)
    expect(player.playVideo).toHaveBeenCalledTimes(2)
  })

  it.each([100, 101, 150])('mostra a thumbnail e "vídeo indisponível" no erro %i', async (code) => {
    render(
      <YouTubePlayer
        videoId="abcdefghijk"
        title="Bolo"
        thumbnailUrl="https://i.ytimg.com/vi/abcdefghijk/maxresdefault.jpg"
      />,
    )
    await waitFor(() => expect(FakePlayer.active).toHaveLength(1))

    FakePlayer.active[0].fail(code)

    expect(await screen.findByText('Vídeo indisponível')).toBeInTheDocument()
    expect(screen.getByAltText('Capa do vídeo Bolo')).toHaveAttribute(
      'src',
      'https://i.ytimg.com/vi/abcdefghijk/maxresdefault.jpg',
    )
  })

  it('erros que não são de disponibilidade mantêm o player', async () => {
    const { container } = render(<YouTubePlayer videoId="abcdefghijk" title="Bolo" />)
    await waitFor(() => expect(FakePlayer.active).toHaveLength(1))
    FakePlayer.active[0].ready()

    FakePlayer.active[0].fail(5)

    expect(screen.queryByText('Vídeo indisponível')).not.toBeInTheDocument()
    expect(container.querySelector('[data-player-status]')).toHaveAttribute(
      'data-player-status',
      'ready',
    )
  })

  it.each([
    ['https://evil.example/x.jpg'],
    ['http://i.ytimg.com/vi/abcdefghijk/hqdefault.jpg'],
    ['javascript:alert(1)'],
  ])('thumbnail_url fora do i.ytimg.com (%s) é trocada pela do youtube_id', async (url) => {
    render(<YouTubePlayer videoId="abcdefghijk" title="Bolo" thumbnailUrl={url} />)
    await waitFor(() => expect(FakePlayer.active).toHaveLength(1))

    FakePlayer.active[0].fail(100)

    expect(await screen.findByAltText('Capa do vídeo Bolo')).toHaveAttribute(
      'src',
      'https://i.ytimg.com/vi/abcdefghijk/hqdefault.jpg',
    )
  })

  it('avisa a página quando o vídeo fica indisponível', async () => {
    const statuses: string[] = []
    render(
      <YouTubePlayer
        videoId="abcdefghijk"
        title="Bolo"
        onStatusChange={(status) => statuses.push(status)}
      />,
    )
    await waitFor(() => expect(FakePlayer.active).toHaveLength(1))
    FakePlayer.active[0].ready()
    FakePlayer.active[0].fail(101)

    await waitFor(() => expect(statuses).toEqual(['loading', 'ready', 'unavailable']))
  })
})
