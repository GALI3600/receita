import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../models/recipe.dart';
import '../../../models/recipe_page.dart';
import '../../../providers/core_providers.dart';

/// Filtros da lista — espelha os query params de `GET /api/recipes`
/// (`q`, `tag`, `favorite`). Usado como chave da `family` para cachear uma lista por
/// combinação de filtros, igual à chave de cache (`['recipes', filters]`) da web.
class RecipeListFilters {
  final String? q;
  final String? tag;
  final bool? favorite;

  const RecipeListFilters({this.q, this.tag, this.favorite});

  RecipeListFilters copyWith({String? q, String? tag, bool? favorite, bool clearFavorite = false}) {
    return RecipeListFilters(
      q: q ?? this.q,
      tag: tag ?? this.tag,
      favorite: clearFavorite ? null : (favorite ?? this.favorite),
    );
  }

  @override
  bool operator ==(Object other) =>
      other is RecipeListFilters && other.q == q && other.tag == tag && other.favorite == favorite;

  @override
  int get hashCode => Object.hash(q, tag, favorite);
}

class RecipeListState {
  final List<RecipeSummary> items;
  final String? nextCursor;
  final bool isLoadingMore;

  RecipeListState({required this.items, this.nextCursor, this.isLoadingMore = false});

  bool get hasMore => nextCursor != null;

  RecipeListState copyWith({List<RecipeSummary>? items, String? nextCursor, bool? isLoadingMore}) {
    return RecipeListState(
      items: items ?? this.items,
      nextCursor: nextCursor ?? this.nextCursor,
      isLoadingMore: isLoadingMore ?? this.isLoadingMore,
    );
  }
}

/// Riverpod 3 não injeta mais o argumento da `family` como parâmetro de `build()`
/// nem como getter `arg` herdado — o filtro é passado pelo construtor (ver a factory
/// em `recipeListProvider` abaixo) e guardado aqui como campo.
class RecipeListNotifier extends AsyncNotifier<RecipeListState> {
  final RecipeListFilters filters;

  RecipeListNotifier(this.filters);

  @override
  Future<RecipeListState> build() async {
    final RecipePage page = await ref
        .read(recipesRepositoryProvider)
        .list(q: filters.q, tag: filters.tag, favorite: filters.favorite);
    return RecipeListState(items: page.items, nextCursor: page.nextCursor);
  }

  Future<void> loadMore() async {
    final current = state.value;
    if (current == null || !current.hasMore || current.isLoadingMore) return;
    state = AsyncData(current.copyWith(isLoadingMore: true));
    try {
      final page = await ref.read(recipesRepositoryProvider).list(
            q: filters.q,
            tag: filters.tag,
            favorite: filters.favorite,
            cursor: current.nextCursor,
          );
      state = AsyncData(RecipeListState(
        items: [...current.items, ...page.items],
        nextCursor: page.nextCursor,
      ));
    } catch (_) {
      // Falha ao carregar mais: mantém a lista atual, só desliga o indicador. O usuário
      // pode tentar de novo rolando até o fim novamente.
      state = AsyncData(current.copyWith(isLoadingMore: false));
    }
  }

  Future<void> refresh() async {
    state = const AsyncLoading();
    state = await AsyncValue.guard(build);
  }
}

final recipeListProvider =
    AsyncNotifierProvider.family<RecipeListNotifier, RecipeListState, RecipeListFilters>(
  RecipeListNotifier.new,
);

final recipeTagsProvider = FutureProvider((ref) => ref.read(recipesRepositoryProvider).tags());
