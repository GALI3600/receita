import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../../../models/recipe.dart';

class RecipeCard extends StatelessWidget {
  final RecipeSummary recipe;

  const RecipeCard({super.key, required this.recipe});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: () => context.push('/receitas/${recipe.id}'),
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              ClipRRect(
                borderRadius: BorderRadius.circular(8),
                child: recipe.video.thumbnailUrl != null
                    ? Image.network(
                        recipe.video.thumbnailUrl!,
                        width: 88,
                        height: 88,
                        fit: BoxFit.cover,
                        errorBuilder: (_, error, stackTrace) => _placeholderThumb(),
                      )
                    : _placeholderThumb(),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Expanded(
                          child: Text(
                            recipe.title,
                            style: theme.textTheme.titleMedium,
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                        if (recipe.isFavorite)
                          Icon(Icons.favorite, size: 18, color: theme.colorScheme.primary),
                      ],
                    ),
                    if (recipe.summary.isNotEmpty) ...[
                      const SizedBox(height: 4),
                      Text(
                        recipe.summary,
                        style: theme.textTheme.bodySmall,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ],
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _placeholderThumb() {
    return Container(
      width: 88,
      height: 88,
      color: Colors.black12,
      child: const Icon(Icons.menu_book, color: Colors.black38),
    );
  }
}
