import 'recipe.dart';

/// Espelha `RecipePage` em `backend/app/schemas/recipes.py` (paginação por cursor).
class RecipePage {
  final List<RecipeSummary> items;
  final String? nextCursor;

  RecipePage({required this.items, this.nextCursor});

  factory RecipePage.fromJson(Map<String, dynamic> json) {
    return RecipePage(
      items: (json['items'] as List)
          .map((e) => RecipeSummary.fromJson((e as Map).cast<String, dynamic>()))
          .toList(),
      nextCursor: json['next_cursor'] as String?,
    );
  }
}

/// Espelha `RecipeTag` em `backend/app/schemas/recipes.py`.
class RecipeTag {
  final String name;
  final int count;

  RecipeTag({required this.name, required this.count});

  factory RecipeTag.fromJson(Map<String, dynamic> json) {
    return RecipeTag(name: json['name'] as String, count: json['count'] as int);
  }
}

/// Espelha `RecipeTags` em `backend/app/schemas/recipes.py`.
class RecipeTags {
  final List<RecipeTag> tags;

  RecipeTags({required this.tags});

  factory RecipeTags.fromJson(Map<String, dynamic> json) {
    return RecipeTags(
      tags: (json['tags'] as List)
          .map((e) => RecipeTag.fromJson((e as Map).cast<String, dynamic>()))
          .toList(),
    );
  }
}
