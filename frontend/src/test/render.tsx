import { QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import type { ReactElement } from 'react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'

import { createQueryClient } from '../api/queries'
import { SessionProvider } from '../session/SessionProvider'

/** Mostra a rota atual (caminho + query) para os testes conferirem redirecionamentos. */
export function LocationProbe() {
  const location = useLocation()
  return <output data-testid="location">{location.pathname + location.search}</output>
}

export function renderApp(routes: ReactElement, { route = '/' }: { route?: string } = {}) {
  const client = createQueryClient()
  client.setDefaultOptions({
    queries: { ...client.getDefaultOptions().queries, retry: false },
  })
  const result = render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[route]}>
        <SessionProvider>
          <Routes>{routes}</Routes>
          <LocationProbe />
        </SessionProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return { ...result, client }
}

export { Route }
