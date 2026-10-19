import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../models/recipe.dart';
import '../../../models/recipe_update.dart';
import '../../../providers/core_providers.dart';

/// Estado e ações da tela de receita — papel equivalente a `useRecipe` +
/// `useUpdateRecipe`/`useDeleteRecipe`/`useResetRecipe` de `frontend/src/api/queries.ts`,
/// todos agindo sobre o mesmo registro em cache (aqui, o mesmo `state`).
///
/// Riverpod 3 não injeta mais o argumento da `family` como parâmetro de `build()`
/// nem como getter `arg` herdado — o id é passado pelo construtor (ver a factory em
/// `recipeDetailProvider` abaixo) e guardado aqui como campo.
class RecipeDetailNotifier extends AsyncNotifier<Recipe> {
  final String recipeId;

  RecipeDetailNotifier(this.recipeId);

  @override
  Future<Recipe> build() => ref.read(recipesRepositoryProvider).get(recipeId);

  /// Atualiza sem piscar um spinner (mutação pequena): se a API falhar, volta pro dado
  /// anterior e relança o erro para a tela decidir como avisar o usuário (ex.: SnackBar).
  Future<void> _applyUpdate(RecipeUpdate update) async {
    final previousData = state.value;
    try {
      final updated = await ref.read(recipesRepositoryProvider).update(recipeId, update);
      state = AsyncData(updated);
    } catch (e, st) {
      state = previousData != null ? AsyncData(previousData) : AsyncError(e, st);
      rethrow;
    }
  }

  Future<void> toggleFavorite() async {
    final current = state.value;
    if (current == null) return;
    await _applyUpdate(RecipeUpdate()..setIsFavorite(!current.isFavorite));
  }

  Future<void> setRating(int? rating) => _applyUpdate(RecipeUpdate()..setRating(rating));

  Future<void> saveNotes(String? notes) => _applyUpdate(RecipeUpdate()..setUserNotes(notes));

  Future<void> applyEdits(RecipeUpdate update) => _applyUpdate(update);

  Future<void> resetToOriginal() async {
    state = await AsyncValue.guard(() => ref.read(recipesRepositoryProvider).reset(recipeId));
  }

  Future<void> delete() => ref.read(recipesRepositoryProvider).remove(recipeId);
}

final recipeDetailProvider =
    AsyncNotifierProvider.family<RecipeDetailNotifier, Recipe, String>(RecipeDetailNotifier.new);
