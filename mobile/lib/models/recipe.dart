/// Espelha `VideoOut` em `backend/app/schemas/recipes.py`.
class VideoInfo {
  final String youtubeId;
  final String title;
  final String? channel;
  final String? thumbnailUrl;
  final int durationS;

  VideoInfo({
    required this.youtubeId,
    required this.title,
    this.channel,
    this.thumbnailUrl,
    required this.durationS,
  });

  factory VideoInfo.fromJson(Map<String, dynamic> json) {
    return VideoInfo(
      youtubeId: json['youtube_id'] as String,
      title: json['title'] as String,
      channel: json['channel'] as String?,
      thumbnailUrl: json['thumbnail_url'] as String?,
      durationS: json['duration_s'] as int,
    );
  }
}

/// Espelha `IngredientOut` em `backend/app/schemas/recipes.py`.
class Ingredient {
  final String name;
  final String? quantity;
  final String? unit;
  final String? note;
  final String? group;

  Ingredient({required this.name, this.quantity, this.unit, this.note, this.group});

  factory Ingredient.fromJson(Map<String, dynamic> json) {
    return Ingredient(
      name: json['name'] as String,
      quantity: json['quantity'] as String?,
      unit: json['unit'] as String?,
      note: json['note'] as String?,
      group: json['group'] as String?,
    );
  }
}

/// Espelha `StepOut` em `backend/app/schemas/recipes.py`.
///
/// `videoTimestampS` existe no contrato mas, de propósito, não é usado em nenhum lugar
/// da UI mobile — a tela de receita (estilo livro) não tem player de vídeo nem chips de
/// tempo, diferente da web.
class Step {
  final int order;
  final String text;
  final int? videoTimestampS;

  Step({required this.order, required this.text, this.videoTimestampS});

  factory Step.fromJson(Map<String, dynamic> json) {
    return Step(
      order: json['order'] as int,
      text: json['text'] as String,
      videoTimestampS: json['video_timestamp_s'] as int?,
    );
  }
}

const List<String> difficulties = ['fácil', 'média', 'difícil'];

/// Espelha `RecipeSummary` em `backend/app/schemas/recipes.py` (usado na lista/livro).
class RecipeSummary {
  final String id;
  final String title;
  final String summary;
  final int? prepTimeMin;
  final int? cookTimeMin;
  final String? difficulty;
  final List<String> tags;
  final bool isFavorite;
  final int? rating;
  final DateTime createdAt;
  final DateTime updatedAt;
  final VideoInfo video;

  RecipeSummary({
    required this.id,
    required this.title,
    required this.summary,
    this.prepTimeMin,
    this.cookTimeMin,
    this.difficulty,
    required this.tags,
    required this.isFavorite,
    this.rating,
    required this.createdAt,
    required this.updatedAt,
    required this.video,
  });

  factory RecipeSummary.fromJson(Map<String, dynamic> json) {
    return RecipeSummary(
      id: json['id'] as String,
      title: json['title'] as String,
      summary: json['summary'] as String,
      prepTimeMin: json['prep_time_min'] as int?,
      cookTimeMin: json['cook_time_min'] as int?,
      difficulty: json['difficulty'] as String?,
      tags: (json['tags'] as List).cast<String>(),
      isFavorite: json['is_favorite'] as bool,
      rating: json['rating'] as int?,
      createdAt: DateTime.parse(json['created_at'] as String),
      updatedAt: DateTime.parse(json['updated_at'] as String),
      video: VideoInfo.fromJson((json['video'] as Map).cast<String, dynamic>()),
    );
  }
}

/// Espelha `RecipeOut` em `backend/app/schemas/recipes.py` (detalhe completo da receita).
class Recipe extends RecipeSummary {
  final String? servings;
  final List<Ingredient> ingredients;
  final List<Step> steps;
  final List<String> tips;
  final String? userNotes;

  Recipe({
    required super.id,
    required super.title,
    required super.summary,
    super.prepTimeMin,
    super.cookTimeMin,
    super.difficulty,
    required super.tags,
    required super.isFavorite,
    super.rating,
    required super.createdAt,
    required super.updatedAt,
    required super.video,
    this.servings,
    required this.ingredients,
    required this.steps,
    required this.tips,
    this.userNotes,
  });

  factory Recipe.fromJson(Map<String, dynamic> json) {
    return Recipe(
      id: json['id'] as String,
      title: json['title'] as String,
      summary: json['summary'] as String,
      prepTimeMin: json['prep_time_min'] as int?,
      cookTimeMin: json['cook_time_min'] as int?,
      difficulty: json['difficulty'] as String?,
      tags: (json['tags'] as List).cast<String>(),
      isFavorite: json['is_favorite'] as bool,
      rating: json['rating'] as int?,
      createdAt: DateTime.parse(json['created_at'] as String),
      updatedAt: DateTime.parse(json['updated_at'] as String),
      video: VideoInfo.fromJson((json['video'] as Map).cast<String, dynamic>()),
      servings: json['servings'] as String?,
      ingredients: (json['ingredients'] as List)
          .map((e) => Ingredient.fromJson((e as Map).cast<String, dynamic>()))
          .toList(),
      steps: (json['steps'] as List)
          .map((e) => Step.fromJson((e as Map).cast<String, dynamic>()))
          .toList(),
      tips: (json['tips'] as List).cast<String>(),
      userNotes: json['user_notes'] as String?,
    );
  }
}
