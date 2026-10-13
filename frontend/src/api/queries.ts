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
import { accountApi, authApi, importsApi, recipesApi } from './endpoints'
import type { ImportOut, Me, Recipe, RecipeFilters, RecipePage, RecipeUpdate } from './types'

export const queryKeys = {
  me: ['me'] as const,
  import: (id: string) => ['import', id] as const,
  recipes: ['recipes'] as const,
  recipeList: (filters: RecipeFilters) => ['recipes', 'list', filters] as const,
  recipe: (id: string) => ['recipes', 'detail', id] as const,
  recipeTags: ['recipes', 'tags'] as const,
}

function isClientError(error: unknown): boolean {
  return error instanceof ApiError && error.status >= 400 && error.status < 500
}

function shouldRetry(failureCount: number, error: unknown): boolean {
  // Erros do cliente (4xx) não melhoram tentando de novo; rede e 5xx, até duas vezes.
  if (isClientError(error)) return false
  return failureCount < 2
}

/** QueryClient do app: uma sessão expirada (401 em qualquer pedido) desloga a interface. */
export function createQueryClient(): QueryClient {
  const client: QueryClient = new QueryClient({
    queryCache: new QueryCache({ onError: (error) => handleUnauthorized(client, error) }),
    mutationCache: new MutationCache({ onError: (error) => handleUnauthorized(client, error) }),
    defaultOptions: {
      // networkMode 'always': sem internet o fetch falha na hora e vira ApiError network_error
      // (com mensagem), em vez de o pedido ficar pausado sem aviso até a conexão voltar.
      queries: {
        retry: shouldRetry,
        refetchOnWindowFocus: false,
        staleTime: 15_000,
        networkMode: 'always',
      },
      mutations: { retry: false, networkMode: 'always' },
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
  return useQuery({
    queryKey: queryKeys.me,
    queryFn: ({ signal }) => fetchMe(signal),
    // Voltar para a aba atualiza a cota e a confirmação do e-mail feitas em outra aba.
    refetchOnWindowFocus: true,
  })
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

/** Esquece a sessão no cliente: o usuário vira anônimo e o cache dele some. */
export function clearSession(client: QueryClient) {
  client.removeQueries({ predicate: (query) => query.queryKey[0] !== 'me' })
  client.setQueryData(queryKeys.me, null)
}

/**
 * POST /auth/logout. Não mexe no cache: quem chama (SessionProvider) limpa a sessão só depois
 * do sucesso. 401 conta como sucesso (a sessão já tinha acabado); outros erros (rede, 5xx)
 * deixam o cookie valendo, então a interface continua logada e mostra o erro.
 */
export function useLogout() {
  return useMutation({
    mutationFn: async () => {
      try {
        await authApi.logout()
      } catch (error) {
        if (!(error instanceof ApiError && error.status === 401)) throw error
      }
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
    onError: (error) => {
      // Cota ou limite atingidos (talvez em outra aba): a cota mostrada precisa acompanhar.
      if (error instanceof ApiError && error.status === 429) {
        void client.invalidateQueries({ queryKey: queryKeys.me })
      }
    },
  })
}

/**
 * Acompanha um import com polling adaptativo. Para sozinho em done/failed, num erro 4xx (import
 * inexistente, de outra conta ou id inválido) e num erro sem nada carregado; uma falha
 * passageira (rede, 5xx) depois de já ter o import continua tentando no ritmo normal.
 */
export function useImport(id: string | null) {
  return useQuery({
    queryKey: queryKeys.import(id ?? ''),
    queryFn: ({ signal }) => importsApi.get(id as string, signal),
    enabled: Boolean(id),
    staleTime: 0,
    refetchInterval: (query) => {
      const imp = query.state.data as ImportOut | undefined
      if (query.state.status === 'error' && (!imp || isClientError(query.state.error))) {
        return false
      }
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

/** Todas as tags do livro (para o filtro), independentes da busca e da paginação. */
export function useRecipeTags() {
  return useQuery({
    queryKey: queryKeys.recipeTags,
    queryFn: ({ signal }) => recipesApi.tags(signal),
    select: (data) => data.tags.map((tag) => tag.name),
  })
}

export function useRecipe(id: string) {
  return useQuery({
    queryKey: queryKeys.recipe(id),
    queryFn: ({ signal }) => recipesApi.get(id, signal),
  })
}

// Campos do usuário (não da receita): mudam na hora na tela, antes de a API responder.
const OPTIMISTIC_FIELDS = ['is_favorite', 'rating', 'user_notes'] as const

function pick<T extends object>(source: T, keys: string[]): Partial<T> {
  const result: Partial<T> = {}
  for (const key of keys) {
    if (key in source) result[key as keyof T] = source[key as keyof T]
  }
  return result
}

/**
 * PATCH /recipes/{id}. Favorito, avaliação e notas são otimistas (desfeitos se a API recusar);
 * as edições da receita só aparecem com a resposta. Cada pedido só mexe no cache nos campos que
 * enviou: favoritar enquanto a nota ainda está sendo salva não desfaz a nota.
 */
export function useUpdateRecipe(id: string) {
  const client = useQueryClient()
  return useMutation({
    mutationKey: ['updateRecipe', id],
    mutationFn: (changes: RecipeUpdate) => recipesApi.update(id, changes),
    onMutate: async (changes) => {
      const optimistic = pick(changes, [...OPTIMISTIC_FIELDS]) as Partial<Recipe>
      const keys = Object.keys(optimistic)
      if (keys.length === 0) return { previous: {} as Partial<Recipe> }
      await client.cancelQueries({ queryKey: queryKeys.recipe(id) })
      const current = client.getQueryData<Recipe>(queryKeys.recipe(id))
      if (!current) return { previous: {} as Partial<Recipe> }
      client.setQueryData<Recipe>(queryKeys.recipe(id), { ...current, ...optimistic })
      return { previous: pick(current, keys) }
    },
    onError: (_error, _changes, context) => {
      if (!context || Object.keys(context.previous).length === 0) return
      client.setQueryData<Recipe>(queryKeys.recipe(id), (current) =>
        current ? { ...current, ...context.previous } : current,
      )
    },
    onSuccess: (recipe, changes) => {
      client.setQueryData<Recipe>(queryKeys.recipe(id), (current) =>
        current
          ? { ...current, ...pick(recipe, Object.keys(changes)), updated_at: recipe.updated_at }
          : recipe,
      )
    },
    onSettled: () =>
      Promise.all([
        client.invalidateQueries({ queryKey: ['recipes', 'list'] }),
        client.invalidateQueries({ queryKey: queryKeys.recipeTags }),
      ]),
  })
}

/** POST /recipes/{id}/reset: volta à receita gerada para o vídeo. */
export function useResetRecipe(id: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: () => recipesApi.reset(id),
    onSuccess: (recipe) => {
      client.setQueryData(queryKeys.recipe(id), recipe)
      void client.invalidateQueries({ queryKey: ['recipes', 'list'] })
      void client.invalidateQueries({ queryKey: queryKeys.recipeTags })
    },
  })
}

export function useDeleteRecipe(id: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: () => recipesApi.remove(id),
    onSuccess: () => {
      client.removeQueries({ queryKey: queryKeys.recipe(id) })
      void client.invalidateQueries({ queryKey: ['recipes', 'list'] })
      void client.invalidateQueries({ queryKey: queryKeys.recipeTags })
    },
  })
}

// --- Conta ---------------------------------------------------------------------------------

/** GET /account/export: os dados chegam como JSON e viram um arquivo para baixar. */
export function useExportAccount() {
  return useMutation({ mutationFn: accountApi.export })
}

/** DELETE /account (com a senha). Quem chama encerra a sessão na interface depois do sucesso. */
export function useDeleteAccount() {
  return useMutation({ mutationFn: accountApi.remove })
}
