import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach, vi } from 'vitest'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  // Marcações de ingredientes guardadas por um teste não vazam para o próximo.
  try {
    window.localStorage.clear()
  } catch {
    // sem armazenamento
  }
})

// jsdom não implementa matchMedia nem scrollIntoView.
if (!window.matchMedia) {
  window.matchMedia = (query: string) =>
    ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      addListener: () => undefined,
      removeListener: () => undefined,
      dispatchEvent: () => false,
    }) as MediaQueryList
}
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => undefined
}
