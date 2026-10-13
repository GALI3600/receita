import { Component, type ErrorInfo, type ReactNode } from 'react'

interface ErrorBoundaryState {
  error: Error | null
}

/**
 * Um erro de renderização mostra uma página de erro em vez de deixar a tela em branco.
 * Usa um <a> simples (não o Link do roteador): a página de erro também precisa funcionar fora
 * do <Router>, na raiz do app.
 */
export class ErrorBoundary extends Component<{ children: ReactNode }, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Erro de renderização', error, info.componentStack)
  }

  render() {
    if (!this.state.error) return this.props.children
    return (
      <div className="mx-auto max-w-xl px-4 py-16 text-center" role="alert">
        <h1 className="text-3xl font-semibold">Algo deu errado nesta página</h1>
        <p className="mt-2 text-ink-soft">
          Recarregue a página ou volte para o início. Suas receitas continuam salvas.
        </p>
        <div className="mt-6 flex flex-wrap justify-center gap-3">
          <button type="button" className="btn-primary" onClick={() => window.location.reload()}>
            Recarregar a página
          </button>
          <a href="/" className="btn-secondary">
            Ir para o início
          </a>
        </div>
      </div>
    )
  }
}
