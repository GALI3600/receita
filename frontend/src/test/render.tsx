import { QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import type { ReactElement } from 'react'
import { createMemoryRouter, Route, RouterProvider, Routes, useLocation } from 'react-router-dom'

import { createQueryClient } from '../api/queries'
import { SessionProvider } from '../session/SessionProvider'

/** Mostra a rota atual (caminho + query) para os testes conferirem redirecionamentos. */
export function LocationProbe() {
  const location = useLocation()
  return <output data-testid="location">{location.pathname + location.search}</output>
}

export function renderApp(routes: ReactElement, { route = '/' }: { route?: string } = {}) {
  const client = createQueryClient()
  // setDefaultOptions troca tudo: mantém as opções das mutations do app.
  const defaults = client.getDefaultOptions()
  client.setDefaultOptions({ ...defaults, queries: { ...defaults.queries, retry: false } })
  // Roteador de dados, como no app (useBlocker só funciona nele).
  const router = createMemoryRouter(
    [
      {
        path: '*',
        element: (
          <SessionProvider>
            <Routes>{routes}</Routes>
            <LocationProbe />
          </SessionProvider>
        ),
      },
    ],
    { initialEntries: [route] },
  )
  const result = render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  )
  return { ...result, client, router }
}

export { Route }
