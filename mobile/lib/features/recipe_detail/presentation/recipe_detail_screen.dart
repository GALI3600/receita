import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../api/api_exception.dart';
import '../../../models/recipe.dart';
import '../../../widgets/error_banner.dart';
import '../application/recipe_detail_providers.dart';
import 'widgets/ingredient_checklist.dart';
import 'widgets/notes_section.dart';
import 'widgets/recipe_edit_sheet.dart';
import 'widgets/step_list_plain.dart';
import 'widgets/time_facts_header.dart';
import 'widgets/tips_section.dart';

/// Tela de receita em estilo "página de livro": título, fatos, ingredientes em
/// checklist, passos em texto puro, dicas e notas — igual ao visual da impressão
/// (`@media print` em `frontend/src/index.css`). De propósito, sem player de vídeo e
/// sem chips de timestamp, diferente da visão on-screen da web.
class RecipeDetailScreen extends ConsumerWidget {
  final String recipeId;

  const RecipeDetailScreen({super.key, required this.recipeId});

  void _showError(BuildContext context, Object error) {
    final message = error is ApiException ? error.message : 'Algo deu errado.';
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
  }

  Future<void> _edit(BuildContext context, WidgetRef ref, Recipe recipe) async {
    final update = await Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => RecipeEditSheet(recipe: recipe)),
    );
    if (update == null) return;
    try {
      await ref.read(recipeDetailProvider(recipeId).notifier).applyEdits(update);
    } on ApiException catch (e) {
      if (context.mounted) _showError(context, e);
    }
  }

  Future<void> _confirmAndRun(
    BuildContext context,
    String title,
    String message,
    Future<void> Function() action,
  ) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(title),
        content: Text(message),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancelar')),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Confirmar')),
        ],
      ),
    );
    if (confirmed == true) await action();
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final recipeState = ref.watch(recipeDetailProvider(recipeId));

    return Scaffold(
      appBar: AppBar(
        title: Text(recipeState.value?.title ?? 'Receita', overflow: TextOverflow.ellipsis),
        actions: recipeState.value == null
            ? null
            : [
                IconButton(
                  icon: Icon(
                    recipeState.value!.isFavorite ? Icons.favorite : Icons.favorite_border,
                  ),
                  onPressed: () async {
                    try {
                      await ref.read(recipeDetailProvider(recipeId).notifier).toggleFavorite();
                    } on ApiException catch (e) {
                      if (context.mounted) _showError(context, e);
                    }
                  },
                ),
                IconButton(
                  icon: const Icon(Icons.edit_outlined),
                  onPressed: () => _edit(context, ref, recipeState.value!),
                ),
                PopupMenuButton<String>(
                  onSelected: (value) async {
                    if (value == 'reset') {
                      await _confirmAndRun(
                        context,
                        'Restaurar receita original',
                        'Isso descarta suas edições e volta para o que a IA gerou. Continuar?',
                        () => ref.read(recipeDetailProvider(recipeId).notifier).resetToOriginal(),
                      );
                    } else if (value == 'delete') {
                      await _confirmAndRun(
                        context,
                        'Excluir receita',
                        'Essa ação não pode ser desfeita. Continuar?',
                        () async {
                          await ref.read(recipeDetailProvider(recipeId).notifier).delete();
                          if (context.mounted) context.go('/livro');
                        },
                      );
                    }
                  },
                  itemBuilder: (context) => const [
                    PopupMenuItem(value: 'reset', child: Text('Restaurar receita original')),
                    PopupMenuItem(value: 'delete', child: Text('Excluir')),
                  ],
                ),
              ],
      ),
      body: recipeState.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (error, _) => Center(
          child: Padding(padding: const EdgeInsets.all(24), child: ErrorBanner(error: error)),
        ),
        data: (recipe) => SingleChildScrollView(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              if (recipe.summary.isNotEmpty) ...[
                Text(recipe.summary, style: Theme.of(context).textTheme.bodyLarge),
                const SizedBox(height: 12),
              ],
              _RatingStars(
                rating: recipe.rating,
                onChanged: (value) async {
                  try {
                    await ref.read(recipeDetailProvider(recipeId).notifier).setRating(value);
                  } on ApiException catch (e) {
                    if (context.mounted) _showError(context, e);
                  }
                },
              ),
              TimeFactsHeader(recipe: recipe),
              const SizedBox(height: 16),
              Text('Ingredientes', style: Theme.of(context).textTheme.titleLarge),
              const SizedBox(height: 8),
              IngredientChecklist(ingredients: recipe.ingredients),
              const SizedBox(height: 16),
              Text('Modo de preparo', style: Theme.of(context).textTheme.titleLarge),
              StepListPlain(steps: recipe.steps),
              const SizedBox(height: 16),
              TipsSection(tips: recipe.tips),
              const SizedBox(height: 16),
              NotesSection(
                notes: recipe.userNotes,
                onSave: (value) async {
                  try {
                    await ref.read(recipeDetailProvider(recipeId).notifier).saveNotes(value);
                  } on ApiException catch (e) {
                    if (context.mounted) _showError(context, e);
                  }
                },
              ),
              const SizedBox(height: 32),
            ],
          ),
        ),
      ),
    );
  }
}

class _RatingStars extends StatelessWidget {
  final int? rating;
  final ValueChanged<int?> onChanged;

  const _RatingStars({required this.rating, required this.onChanged});

  @override
  Widget build(BuildContext context) {
    return Row(
      children: List.generate(5, (i) {
        final value = i + 1;
        final filled = rating != null && value <= rating!;
        return IconButton(
          icon: Icon(filled ? Icons.star : Icons.star_border, color: Colors.amber),
          onPressed: () => onChanged(rating == value ? null : value),
        );
      }),
    );
  }
}
