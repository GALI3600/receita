import 'package:flutter/material.dart';

import '../../../../models/recipe.dart';

String _formatMinutes(int minutes) {
  if (minutes < 60) return '$minutes min';
  final hours = minutes ~/ 60;
  final rest = minutes % 60;
  return rest == 0 ? '${hours}h' : '${hours}h${rest}min';
}

/// Fatos da receita (porções/preparo/forno/total) — espelha a seção de `TimeFacts` em
/// `frontend/src/pages/RecipePage.tsx`, que também é o que aparece na impressão.
class TimeFactsHeader extends StatelessWidget {
  final Recipe recipe;

  const TimeFactsHeader({super.key, required this.recipe});

  @override
  Widget build(BuildContext context) {
    final facts = <(String, String)>[];
    if (recipe.servings != null && recipe.servings!.isNotEmpty) {
      facts.add(('Rende', recipe.servings!));
    }
    if (recipe.prepTimeMin != null) facts.add(('Preparo', _formatMinutes(recipe.prepTimeMin!)));
    if (recipe.cookTimeMin != null) facts.add(('Forno/fogo', _formatMinutes(recipe.cookTimeMin!)));
    if (recipe.prepTimeMin != null && recipe.cookTimeMin != null) {
      facts.add(('Total', _formatMinutes(recipe.prepTimeMin! + recipe.cookTimeMin!)));
    }

    if (facts.isEmpty) return const SizedBox.shrink();

    final theme = Theme.of(context);
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 12),
      decoration: BoxDecoration(
        border: Border(
          top: BorderSide(color: theme.dividerColor),
          bottom: BorderSide(color: theme.dividerColor),
        ),
      ),
      child: Wrap(
        spacing: 24,
        runSpacing: 12,
        children: facts.map((fact) {
          return SizedBox(
            width: 120,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  fact.$1.toUpperCase(),
                  style: theme.textTheme.labelSmall?.copyWith(letterSpacing: 0.5),
                ),
                Text(fact.$2, style: theme.textTheme.titleMedium),
              ],
            ),
          );
        }).toList(),
      ),
    );
  }
}
