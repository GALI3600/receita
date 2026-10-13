import type { Ingredient } from '../api/types'

/** 65 → "1:05"; 3725 → "1:02:05". */
export function formatTimestamp(totalSeconds: number): string {
  const seconds = Math.max(0, Math.floor(totalSeconds))
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = seconds % 60
  const ss = String(s).padStart(2, '0')
  return h > 0 ? `${h}:${String(m).padStart(2, '0')}:${ss}` : `${m}:${ss}`
}

/** Minutos por extenso curto: 45 → "45 min"; 90 → "1 h 30 min"; 120 → "2 h". */
export function formatMinutes(minutes: number): string {
  if (minutes < 60) return `${minutes} min`
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  return m ? `${h} h ${m} min` : `${h} h`
}

export function totalMinutes(recipe: {
  prep_time_min: number | null
  cook_time_min: number | null
}): number | null {
  const { prep_time_min: prep, cook_time_min: cook } = recipe
  if (prep === null && cook === null) return null
  return (prep ?? 0) + (cook ?? 0)
}

/** Segundos até algo em texto: "alguns segundos", "5 minutos", "2 horas". */
export function formatWait(seconds: number): string {
  if (seconds < 60) return 'alguns segundos'
  const minutes = Math.ceil(seconds / 60)
  if (minutes < 60) return minutes === 1 ? '1 minuto' : `${minutes} minutos`
  const hours = Math.round(minutes / 60)
  return hours === 1 ? '1 hora' : `${hours} horas`
}

/** Quantidade e unidade de um ingrediente ("2 xícaras"), ou null para "a gosto". */
export function ingredientAmount(ingredient: Ingredient): string | null {
  const parts = [ingredient.quantity, ingredient.unit].filter(Boolean)
  return parts.length ? parts.join(' ') : null
}

/** Agrupa os ingredientes por `group`, na ordem em que os grupos aparecem. */
export function groupIngredients(
  ingredients: Ingredient[],
): Array<{ group: string | null; items: Array<{ ingredient: Ingredient; index: number }> }> {
  const groups = new Map<string | null, Array<{ ingredient: Ingredient; index: number }>>()
  ingredients.forEach((ingredient, index) => {
    const key = ingredient.group?.trim() || null
    const list = groups.get(key) ?? []
    list.push({ ingredient, index })
    groups.set(key, list)
  })
  return [...groups].map(([group, items]) => ({ group, items }))
}

/** Thumbnail pública do YouTube para o vídeo. */
export function youtubeThumbnail(youtubeId: string, quality: 'hq' | 'mq' | 'sd' = 'hq'): string {
  return `https://i.ytimg.com/vi/${encodeURIComponent(youtubeId)}/${quality}default.jpg`
}

const THUMBNAIL_HOSTS = new Set(['i.ytimg.com', 'i9.ytimg.com'])

/**
 * Thumbnail salva para o vídeo (vem do yt-dlp) só se for https em i.ytimg.com; qualquer outra
 * coisa é trocada pela montada a partir do youtube_id.
 */
export function safeThumbnail(url: string | null | undefined, youtubeId: string): string {
  if (url) {
    try {
      const parsed = new URL(url)
      if (
        parsed.protocol === 'https:' &&
        THUMBNAIL_HOSTS.has(parsed.hostname) &&
        !parsed.port &&
        !parsed.username &&
        !parsed.password
      ) {
        return parsed.href
      }
    } catch {
      // URL inválida: usa a montada pelo id.
    }
  }
  return youtubeThumbnail(youtubeId)
}

export function youtubeWatchUrl(youtubeId: string, seconds?: number | null): string {
  const t = seconds ? `&t=${Math.floor(seconds)}s` : ''
  return `https://www.youtube.com/watch?v=${encodeURIComponent(youtubeId)}${t}`
}

const YOUTUBE_HOSTS = [
  'youtube.com',
  'www.youtube.com',
  'm.youtube.com',
  'music.youtube.com',
  'youtu.be',
  'www.youtube-nocookie.com',
  'youtube-nocookie.com',
]

/**
 * Validação leve do link antes de enviar (o backend faz a validação completa):
 * precisa parecer um endereço do YouTube, com ou sem https://.
 */
export function validateYoutubeLink(value: string): string | null {
  const raw = value.trim()
  if (!raw) return 'Cole o link de um vídeo do YouTube.'
  if (/\s/.test(raw)) return 'O link não pode ter espaços.'
  let url: URL
  try {
    url = new URL(raw.includes('://') ? raw : `https://${raw}`)
  } catch {
    return 'Isso não parece um link. Copie o endereço do vídeo no YouTube e cole aqui.'
  }
  if (!['http:', 'https:'].includes(url.protocol) || !YOUTUBE_HOSTS.includes(url.hostname)) {
    return 'Por enquanto só aceitamos vídeos do YouTube (youtube.com ou youtu.be).'
  }
  return null
}

const dateTimeFormat = new Intl.DateTimeFormat('pt-BR', {
  day: 'numeric',
  month: 'long',
  hour: '2-digit',
  minute: '2-digit',
})

export function formatDateTime(iso: string): string {
  return dateTimeFormat.format(new Date(iso))
}

const dateFormat = new Intl.DateTimeFormat('pt-BR', {
  day: 'numeric',
  month: 'long',
  year: 'numeric',
})

export function formatDate(iso: string): string {
  return dateFormat.format(new Date(iso))
}
