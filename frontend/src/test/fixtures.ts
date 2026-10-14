import type { ImportOut, Me, Recipe } from '../api/types'

export function makeMe(overrides: Partial<Me> = {}): Me {
  return {
    id: 'user-1',
    name: 'Ana Souza',
    email: 'ana@example.com',
    email_verified: true,
    plan: 'free',
    created_at: '2026-10-01T12:00:00Z',
    quota: { used: 2, limit: 10, remaining: 8, resets_at: '2026-10-14T00:00:00Z' },
    ...overrides,
  }
}

export function makeImport(overrides: Partial<ImportOut> = {}): ImportOut {
  const now = new Date().toISOString()
  return {
    id: 'imp-1',
    url: 'https://youtu.be/-pRC-FQXLEI',
    youtube_id: '-pRC-FQXLEI',
    status: 'pending',
    recipe_id: null,
    error: null,
    queue_position: null,
    created_at: now,
    updated_at: now,
    ...overrides,
  }
}

export function makeRecipe(overrides: Partial<Recipe> = {}): Recipe {
  return {
    id: 'rec-1',
    title: 'Bolo de cenoura com calda',
    summary: 'Bolo fofinho de liquidificador.',
    servings: '12 fatias',
    prep_time_min: 20,
    cook_time_min: 40,
    difficulty: 'fácil',
    tags: ['bolo', 'sobremesa'],
    is_favorite: false,
    rating: null,
    created_at: '2026-10-10T12:00:00Z',
    updated_at: '2026-10-10T12:00:00Z',
    video: {
      youtube_id: '-pRC-FQXLEI',
      title: 'Bolo de cenoura | Rita Lobo',
      channel: 'Receitas',
      thumbnail_url: 'https://i.ytimg.com/vi/-pRC-FQXLEI/hqdefault.jpg',
      duration_s: 533,
    },
    ingredients: [
      {
        name: 'farinha de trigo',
        quantity: '2',
        unit: 'xícaras',
        note: 'peneirada',
        group: 'massa',
      },
      { name: 'cenoura', quantity: '3', unit: null, note: null, group: 'massa' },
      { name: 'chocolate em pó', quantity: '1/2', unit: 'xícara', note: null, group: 'calda' },
      { name: 'sal', quantity: null, unit: null, note: 'a gosto', group: 'massa' },
    ],
    steps: [
      { order: 1, text: 'Preaqueça o forno a 180 °C.', video_timestamp_s: 0 },
      { order: 2, text: 'Bata as cenouras com os ovos.', video_timestamp_s: 113 },
      { order: 3, text: 'Sirva com a calda.', video_timestamp_s: null },
    ],
    tips: ['Teste o fermento antes.'],
    user_notes: null,
    ...overrides,
  }
}
