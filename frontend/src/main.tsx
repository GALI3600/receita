import '@fontsource-variable/fraunces/opsz.css'
import '@fontsource-variable/fraunces/opsz-italic.css'
import '@fontsource-variable/source-sans-3'
import { QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { createBrowserRouter, RouterProvider } from 'react-router-dom'

import App from './App.tsx'
import { createQueryClient } from './api/queries'
import { ErrorBoundary } from './components/ErrorBoundary'
import './index.css'
import { SessionProvider } from './session/SessionProvider'

const queryClient = createQueryClient()

// Roteador "de dados" (createBrowserRouter) para o aviso de alterações não salvas (useBlocker);
// as rotas continuam declaradas em <App> com <Routes>.
const router = createBrowserRouter([
  {
    path: '*',
    element: (
      <SessionProvider>
        <App />
      </SessionProvider>
    ),
  },
])

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </ErrorBoundary>
  </StrictMode>,
)
