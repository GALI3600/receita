import 'recipe.dart';

/// Espelha `IngredientIn` em `backend/app/schemas/recipes.py`.
class IngredientIn {
  final String name;
  final String? quantity;
  final String? unit;
  final String? note;
  final String? group;

  IngredientIn({required this.name, this.quantity, this.unit, this.note, this.group});

  factory IngredientIn.fromIngredient(Ingredient ingredient) {
    return IngredientIn(
      name: ingredient.name,
      quantity: ingredient.quantity,
      unit: ingredient.unit,
      note: ingredient.note,
      group: ingredient.group,
    );
  }

  Map<String, dynamic> toJson() => {
        'name': name,
        'quantity': quantity,
        'unit': unit,
        'note': note,
        'group': group,
      };
}

/// Espelha `StepIn` em `backend/app/schemas/recipes.py` (a ordem é a da lista enviada;
/// o backend ignora qualquer `order` recebido e renumera pela posição).
class StepIn {
  final String text;
  final int? videoTimestampS;

  StepIn({required this.text, this.videoTimestampS});

  factory StepIn.fromStep(Step step) {
    return StepIn(text: step.text, videoTimestampS: step.videoTimestampS);
  }

  Map<String, dynamic> toJson() => {
        'text': text,
        'video_timestamp_s': videoTimestampS,
      };
}

/// Espelha `RecipeUpdate` em `backend/app/schemas/recipes.py`: só os campos
/// explicitamente definidos aqui (via os setters `set*`) são enviados ao `PATCH`.
///
/// Isso é importante porque o backend trata ausência de campo como "não mudar" e
/// `null` explícito como "limpar o campo" (`RecipeUpdate.changes()` no backend) — então
/// nunca basta montar um objeto completo e mandar; só o que o usuário de fato tocou.
class RecipeUpdate {
  final Map<String, dynamic> _fields = {};

  void setTitle(String value) => _fields['title'] = value;
  void setSummary(String? value) => _fields['summary'] = value;
  void setServings(String? value) => _fields['servings'] = value;
  void setPrepTimeMin(int? value) => _fields['prep_time_min'] = value;
  void setCookTimeMin(int? value) => _fields['cook_time_min'] = value;
  void setDifficulty(String? value) => _fields['difficulty'] = value;
  void setIngredients(List<IngredientIn> value) =>
      _fields['ingredients'] = value.map((e) => e.toJson()).toList();
  void setSteps(List<StepIn> value) => _fields['steps'] = value.map((e) => e.toJson()).toList();
  void setTips(List<String> value) => _fields['tips'] = value;
  void setTags(List<String> value) => _fields['tags'] = value;
  void setIsFavorite(bool value) => _fields['is_favorite'] = value;
  void setUserNotes(String? value) => _fields['user_notes'] = value;
  void setRating(int? value) => _fields['rating'] = value;

  bool get isEmpty => _fields.isEmpty;

  Map<String, dynamic> toJson() => Map.of(_fields);
}
