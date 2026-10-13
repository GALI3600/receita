import { useEffect, useRef, useState } from 'react'
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'

import { useSession } from '../session/context'
import { ErrorBoundary } from './ErrorBoundary'

function BookMark() {
  return (
    <svg viewBox="0 0 32 32" className="size-8" aria-hidden="true">
      <path
        d="M6 5.5c3.5-1 7-.6 10 1.6 3-2.2 6.5-2.6 10-1.6v20c-3.5-1-7-.6-10 1.6-3-2.2-6.5-2.6-10-1.6z"
        fill="var(--color-card)"
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
  `inline-flex min-h-11 items-center rounded-full px-3 py-2 font-semibold transition-colors ${
    isActive ? 'bg-paper-deep text-ink' : 'text-ink-soft hover:bg-paper-deep hover:text-ink'
  }`

const mobileLinkClass = ({ isActive }: { isActive: boolean }) =>
  `flex min-h-12 items-center gap-3 rounded-lg px-4 font-serif text-xl transition-colors ${
    isActive
      ? 'bg-paper-deep font-semibold text-ink'
      : 'text-ink-soft hover:bg-paper-deep hover:text-ink'
  }`

const MAIN_LINKS = [
  { to: '/livro', label: 'Meu livro' },
  { to: '/nova', label: 'Nova receita' },
  { to: '/conta', label: 'Conta' },
]

function MenuIcon({ open }: { open: boolean }) {
  return (
    <svg viewBox="0 0 24 24" className="size-6" aria-hidden="true">
      <path
        d={open ? 'M6 6l12 12M18 6 6 18' : 'M4 7h16M4 12h16M4 17h16'}
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
    </svg>
  )
}

/** Navegação de quem está logado: links no desktop, menu recolhido no celular. */
function MainNav() {
  const { pathname } = useLocation()
  const [open, setOpen] = useState(false)
  const [openedAt, setOpenedAt] = useState(pathname)
  const buttonRef = useRef<HTMLButtonElement>(null)
  // Escolheu uma página: o menu fecha.
  if (open && pathname !== openedAt) setOpen(false)

  useEffect(() => {
    if (!open) return
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        setOpen(false)
        buttonRef.current?.focus()
      }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [open])

  return (
    <nav
      aria-label="Principal"
      onBlur={(event) => {
        // O foco saiu do menu (Tab depois do último link): fecha, senão o painel aberto cobriria
        // o elemento que acabou de receber o foco.
        const next = event.relatedTarget
        if (open && next instanceof Node && !event.currentTarget.contains(next)) setOpen(false)
      }}
    >
      <ul className="hidden items-center gap-1 sm:flex">
        {MAIN_LINKS.map((link) => (
          <li key={link.to}>
            <NavLink to={link.to} className={navLinkClass}>
              {link.label}
            </NavLink>
          </li>
        ))}
      </ul>
      <button
        ref={buttonRef}
        type="button"
        className="inline-flex min-h-11 items-center gap-2 rounded-full px-3 font-semibold text-ink hover:bg-paper-deep sm:hidden"
        aria-expanded={open}
        aria-controls="menu-celular"
        onClick={() => {
          setOpenedAt(pathname)
          setOpen((value) => !value)
        }}
      >
        <MenuIcon open={open} />
        Menu
      </button>
      <div
        id="menu-celular"
        hidden={!open}
        className="menu-panel absolute inset-x-0 top-full z-30 border-b border-line bg-paper px-4 pt-2 pb-4 shadow-page sm:hidden"
      >
        <ul className="space-y-1">
          {MAIN_LINKS.map((link) => (
            <li key={link.to}>
              <NavLink to={link.to} className={mobileLinkClass} onClick={() => setOpen(false)}>
                {link.label}
              </NavLink>
            </li>
          ))}
        </ul>
      </div>
    </nav>
  )
}

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
      <header className="relative z-30 border-b border-line/80 bg-paper/90 backdrop-blur print:hidden">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-2 px-4 py-3">
          <Link
            to={status === 'authenticated' ? '/livro' : '/'}
            className="flex items-center gap-2 py-1.5 text-terracotta"
          >
            <BookMark />
            <span className="font-serif text-2xl font-semibold text-ink">Receita</span>
          </Link>
          {status === 'authenticated' ? (
            <MainNav />
          ) : status === 'anonymous' ? (
            <nav aria-label="Principal">
              <ul className="flex items-center gap-1">
                <li>
                  <NavLink to="/entrar" className={navLinkClass}>
                    Entrar
                  </NavLink>
                </li>
                <li>
                  <Link to="/cadastro" className="btn-primary px-4">
                    Criar conta
                  </Link>
                </li>
              </ul>
            </nav>
          ) : null}
        </div>
      </header>
      <main id="conteudo" ref={mainRef} tabIndex={-1} className="flex-1 focus:outline-none">
        {/* A chave reinicia a página de erro ao navegar para outra rota. */}
        <ErrorBoundary key={location.pathname}>
          <Outlet />
        </ErrorBoundary>
      </main>
      <footer className="border-t border-line/80 px-4 py-6 text-center text-sm text-ink-soft print:hidden">
        <p>Receita · seu livro de receitas a partir de vídeos do YouTube</p>
      </footer>
    </div>
  )
}
