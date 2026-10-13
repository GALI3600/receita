import { useEffect, useRef } from 'react'
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'

import { useSession } from '../session/context'

function BookMark() {
  return (
    <svg viewBox="0 0 32 32" className="size-8" aria-hidden="true">
      <path
        d="M6 5.5c3.5-1 7-.6 10 1.6 3-2.2 6.5-2.6 10-1.6v20c-3.5-1-7-.6-10 1.6-3-2.2-6.5-2.6-10-1.6z"
        fill="#fffdf8"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
      <path d="M16 7.1v20" stroke="currentColor" strokeWidth="1.8" />
      <path d="M20 10.5h3M20 14h3M9 10.5h3.5M9 14h3.5" stroke="currentColor" strokeWidth="1.4" />
    </svg>
  )
}

const navLinkClass = ({ isActive }: { isActive: boolean }) =>
  `rounded-full px-3 py-2 font-semibold transition-colors ${
    isActive ? 'bg-paper-deep text-ink' : 'text-ink-soft hover:bg-paper-deep hover:text-ink'
  }`

export function Layout() {
  const { status } = useSession()
  const location = useLocation()
  const mainRef = useRef<HTMLElement>(null)
  const firstRender = useRef(true)

  // Ao trocar de página, o foco vai para o conteúdo (leitores de tela anunciam a página nova).
  useEffect(() => {
    if (firstRender.current) {
      firstRender.current = false
      return
    }
    mainRef.current?.focus({ preventScroll: true })
    window.scrollTo({ top: 0 })
  }, [location.pathname])

  return (
    <div className="flex min-h-dvh flex-col">
      <a
        href="#conteudo"
        className="sr-only z-50 rounded-md bg-card px-4 py-2 font-semibold focus:not-sr-only focus:fixed focus:top-2 focus:left-2"
      >
        Pular para o conteúdo
      </a>
      <header className="border-b border-line/80 bg-paper/90 backdrop-blur print:hidden">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-2 px-4 py-3">
          <Link
            to={status === 'authenticated' ? '/livro' : '/'}
            className="flex items-center gap-2 text-terracotta"
          >
            <BookMark />
            <span className="font-serif text-2xl font-semibold text-ink">Receita</span>
          </Link>
          <nav aria-label="Principal">
            {status === 'authenticated' ? (
              <ul className="flex items-center gap-0.5 sm:gap-1">
                <li>
                  <NavLink to="/livro" className={navLinkClass}>
                    <span className="sm:hidden">Livro</span>
                    <span className="hidden sm:inline">Meu livro</span>
                  </NavLink>
                </li>
                <li>
                  <NavLink to="/nova" className={navLinkClass}>
                    <span className="sm:hidden">Nova</span>
                    <span className="hidden sm:inline">Nova receita</span>
                  </NavLink>
                </li>
                <li>
                  <NavLink to="/conta" className={navLinkClass}>
                    Conta
                  </NavLink>
                </li>
              </ul>
            ) : status === 'anonymous' ? (
              <ul className="flex items-center gap-1">
                <li>
                  <NavLink to="/entrar" className={navLinkClass}>
                    Entrar
                  </NavLink>
                </li>
                <li>
                  <Link to="/cadastro" className="btn-primary min-h-10 px-4">
                    Criar conta
                  </Link>
                </li>
              </ul>
            ) : null}
          </nav>
        </div>
      </header>
      <main id="conteudo" ref={mainRef} tabIndex={-1} className="flex-1 focus:outline-none">
        <Outlet />
      </main>
      <footer className="border-t border-line/80 px-4 py-6 text-center text-sm text-ink-soft print:hidden">
        <p>Receita · seu livro de receitas a partir de vídeos do YouTube</p>
      </footer>
    </div>
  )
}
