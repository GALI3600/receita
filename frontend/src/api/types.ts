// Tipos que espelham os schemas da API (backend/app/schemas). Datas chegam como texto ISO 8601.

export type Difficulty = 'fácil' | 'média' | 'difícil'

export interface FieldError {
  field: string
  type: string
  message: string
}

export interface ErrorBody {
  code: string
  message: string
  details?: FieldError[]
}

export interface ErrorResponse {
  error: ErrorBody
}

export interface MessageOut {
  message: string
}

export interface Quota {
  /** Receitas novas de hoje, contando as que ainda estão em andamento. */
  used: number
  limit: number
  remaining: number
  /** Quando a cota zera (meia-noite UTC). */
  resets_at: string
}

export interface Me {
  id: string
  name: string
  email: string
  email_verified: boolean
  plan: 'free'
  created_at: string
  quota: Quota
}

export interface RegisterIn {
  name: string
  email: string
  password: string
  'cf-turnstile-response'?: string
}

export interface LoginIn {
  email: string
  password: string
}

export type ImportStatus =
  'pending' | 'fetching' | 'transcribing' | 'generating' | 'done' | 'failed' | 'deferred'

export interface ImportFailure {
  code: string
  message: string
}

export interface ImportOut {
  id: string
  url: string
  youtube_id: string
  status: ImportStatus
  recipe_id: string | null
  /** Por que o import falhou ou, em `deferred`, por que está esperando. */
  error: ImportFailure | null
  /** Posição aproximada na fila (1 = próximo); só enquanto espera. */
  queue_position: number | null
  created_at: string
  updated_at: string
}

export interface Ingredient {
  name: string
  quantity: string | null
  unit: string | null
  note: string | null
  group: string | null
}

export interface Step {
  order: number
  text: string
  video_timestamp_s: number | null
}

export interface VideoOut {
  youtube_id: string
  title: string
  channel: string | null
  thumbnail_url: string | null
  duration_s: number
}

export interface RecipeSummary {
  id: string
  title: string
  summary: string
  prep_time_min: number | null
  cook_time_min: number | null
  difficulty: Difficulty | null
  tags: string[]
  is_favorite: boolean
  rating: number | null
  created_at: string
  updated_at: string
  video: VideoOut
}

export interface Recipe extends RecipeSummary {
  servings: string | null
  ingredients: Ingredient[]
  steps: Step[]
  tips: string[]
  user_notes: string | null
}

/** GET /recipes/tags: as tags do livro, com quantas receitas usam cada uma. */
export interface RecipeTags {
  tags: Array<{ name: string; count: number }>
}

export interface RecipePage {
  items: RecipeSummary[]
  /** Passe em `cursor` para buscar a próxima página; null na última. */
  next_cursor: string | null
}

export interface RecipeFilters {
  q?: string
  tag?: string
  favorite?: boolean
}

export interface RecipeUpdate {
  title?: string
  summary?: string
  servings?: string | null
  prep_time_min?: number | null
  cook_time_min?: number | null
  difficulty?: Difficulty | null
  tips?: string[]
  tags?: string[]
  is_favorite?: boolean
  user_notes?: string | null
  rating?: number | null
}
