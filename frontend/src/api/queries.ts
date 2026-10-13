import {
  MutationCache,
  QueryCache,
  QueryClient,
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query'
import { pollInterval } from '../lib/importStatus'
import { ApiError } from './client'
import { authApi, importsApi, recipesApi } from './endpoints'
import type { ImportOut, Me, Recipe, RecipeFilters, RecipePage, RecipeUpdate } from './types'

export const queryKeys = {
  me: ['me'] as const,
  import: (id: string) => ['import', id] as const,
  recipes: ['recipes'] as const,
  recipeList: (filters: RecipeFilters) => ['recipes', 'list', filters] as const,
  recipe: (id: string) => ['recipes', 'detail', id] as const,
}

function shouldRetry(failureCount: number, error: unknown): boolean {
  // Erros do cliente (4xx) não melhoram tentando de novo; rede e 5xx, até duas vezes.
  if (error instanceof ApiError && error.status >= 400 && error.status < 500) return false
  return failureCount < 2
}

/** QueryClient do app: uma sessão expirada (401 em qualquer pedido) desloga a interface. */
export function createQueryClient(): QueryClient {
  const client: QueryClient = new QueryClient({
    queryCache: new QueryCache({ onError: (error) => handleUnauthorized(client, error) }),
    mutationCache: new MutationCache({ onError: (error) => handleUnauthorized(client, error) }),
    defaultOptions: {
      queries: { retry: shouldRetry, refetchOnWindowFocus: false, staleTime: 15_000 },
      mutations: { retry: false },
    },
  })
  return client
}

function handleUnauthorized(client: QueryClient, error: unknown) {
  if (error instanceof ApiError && error.status === 401) {
    client.setQueryData(queryKeys.me, null)
  }
}

// --- Sessão --------------------------------------------------------------------------------

/** Usuário logado (GET /auth/me) ou null; 401 não é erro, é "sem sessão". */
export async function fetchMe(signal?: AbortSignal): Promise<Me | null> {
  try {
    return await authApi.me(signal)
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return null
    throw error
  }
}

export function useMe() {
  return useQuery({ queryKey: queryKeys.me, queryFn: ({ signal }) => fetchMe(signal) })
}

export function useLogin() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: authApi.login,
    onSuccess: (me) => {
      // Outra conta pode ter usado este navegador: nada do cache anterior vale mais.
      client.removeQueries({ predicate: (query) => query.queryKey[0] !== 'me' })
      client.setQueryData(queryKeys.me, me)
    },
  })
}

export function useLogout() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: authApi.logout,
    onSettled: () => {
      client.removeQueries({ predicate: (query) => query.queryKey[0] !== 'me' })
      client.setQueryData(queryKeys.me, null)
    },
  })
}

export function useRegister() {
  return useMutation({ mutationFn: authApi.register })
}

export function useVerifyEmail() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: authApi.verify,
    onSuccess: () => client.invalidateQueries({ queryKey: queryKeys.me }),
  })
}

export function useResendVerification() {
  return useMutation({ mutationFn: authApi.resendVerification })
}

export function useForgotPassword() {
  return useMutation({ mutationFn: authApi.forgotPassword })
}

export function useResetPassword() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ token, password }: { token: string; password: string }) =>
      authApi.resetPassword(token, password),
    // Trocar a senha encerra todas as sessões, inclusive a deste navegador.
    onSuccess: () => client.setQueryData(queryKeys.me, null),
  })
}

// --- Imports -------------------------------------------------------------------------------

export function useCreateImport() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: importsApi.create,
    onSuccess: (imp) => {
      client.setQueryData(queryKeys.import(imp.id), imp)
      void client.invalidateQueries({ queryKey: queryKeys.me })
      if (imp.status === 'done') void client.invalidateQueries({ queryKey: queryKeys.recipes })
    },
  })
}

/** Acompanha um import com polling adaptativo (para sozinho em done/failed). */
export function useImport(id: string | null) {
  return useQuery({
    queryKey: queryKeys.import(id ?? ''),
    queryFn: ({ signal }) => importsApi.get(id as string, signal),
    enabled: Boolean(id),
    staleTime: 0,
    refetchInterval: (query) => {
      const imp = query.state.data as ImportOut | undefined
      // Tempo desde a criação do import: o ritmo continua certo mesmo depois de recarregar.
      const elapsed = imp ? Date.now() - Date.parse(imp.created_at) : 0
      return pollInterval(imp, elapsed)
    },
    refetchIntervalInBackground: false,
  })
}

// --- Receitas ------------------------------------------------------------------------------

export function useRecipes(filters: RecipeFilters) {
  return useInfiniteQuery({
    queryKey: queryKeys.recipeList(filters),
    queryFn: ({ pageParam, signal }) => recipesApi.list(filters, pageParam, signal),
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage: RecipePage) => lastPage.next_cursor,
  })
}

export function useRecipe(id: string) {
  return useQuery({
    queryKey: queryKeys.recipe(id),
    queryFn: ({ signal }) => recipesApi.get(id, signal),
  })
}

export function useUpdateRecipe(id: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (changes: RecipeUpdate) => recipesApi.update(id, changes),
    onMutate: async (changes) => {
      // Atualização otimista (ex.: favoritar responde na hora); desfeita se a API recusar.
      await client.cancelQueries({ queryKey: queryKeys.recipe(id) })
      const previous = client.getQueryData<Recipe>(queryKeys.recipe(id))
      if (previous) {
        client.setQueryData<Recipe>(queryKeys.recipe(id), {
          ...previous,
          ...(changes as Partial<Recipe>),
        })
      }
      return { previous }
    },
    onError: (_error, _changes, context) => {
      if (context?.previous) client.setQueryData(queryKeys.recipe(id), context.previous)
    },
    onSuccess: (recipe) => client.setQueryData(queryKeys.recipe(id), recipe),
    onSettled: () => client.invalidateQueries({ queryKey: ['recipes', 'list'] }),
  })
}

export function useDeleteRecipe(id: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: () => recipesApi.remove(id),
    onSuccess: () => {
      client.removeQueries({ queryKey: queryKeys.recipe(id) })
      void client.invalidateQueries({ queryKey: ['recipes', 'list'] })
    },
  })
}
