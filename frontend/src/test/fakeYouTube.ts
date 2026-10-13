import { act } from '@testing-library/react'
import { vi } from 'vitest'

import { resetYouTubeApiForTests } from '../components/youtube/loadYouTubeApi'

/** Player falso da YouTube IFrame API: guarda as opções e expõe os métodos como mocks. */
export class FakePlayer {
  static instances: FakePlayer[] = []
  readonly options: YT.PlayerOptions
  readonly iframe: HTMLIFrameElement
  readonly seekTo = vi.fn()
  readonly playVideo = vi.fn()
  readonly destroy = vi.fn(() => {
    this.destroyed = true
    this.iframe.remove()
  })
  destroyed = false

  constructor(element: HTMLElement, options: YT.PlayerOptions) {
    this.options = options
    this.iframe = document.createElement('iframe')
    element.replaceWith(this.iframe)
    FakePlayer.instances.push(this)
  }

  getIframe() {
    return this.iframe
  }

  ready() {
    act(() => this.options.events?.onReady?.({ target: this } as unknown as YT.PlayerEvent))
  }

  fail(code: number) {
    act(() =>
      this.options.events?.onError?.({ target: this, data: code } as unknown as YT.OnErrorEvent),
    )
  }

  static get active(): FakePlayer[] {
    return FakePlayer.instances.filter((player) => !player.destroyed)
  }
}

/** Instala o `window.YT` falso (como se o script da API já tivesse carregado). */
export function installFakeYouTube() {
  FakePlayer.instances = []
  resetYouTubeApiForTests()
  vi.stubGlobal('YT', { Player: FakePlayer })
}
