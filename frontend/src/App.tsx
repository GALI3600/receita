import { useQuery } from '@tanstack/react-query'
import { Route, Routes } from 'react-router-dom'

async function fetchHealth(): Promise<{ status: string }> {
  const response = await fetch('/api/health')
  if (!response.ok) throw new Error(`HTTP ${response.status}`)
  return response.json()
}

function Home() {
  const health = useQuery({ queryKey: ['health'], queryFn: fetchHealth })

  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-4 bg-amber-50 text-stone-800">
      <h1 className="font-serif text-5xl">Receita</h1>
      <p className="text-stone-600">Seu livro de receitas a partir de vídeos do YouTube.</p>
      <p className="text-sm text-stone-500">
        API:{' '}
        {health.isPending ? 'verificando…' : health.isError ? 'indisponível' : health.data.status}
      </p>
    </main>
  )
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
    </Routes>
  )
}
