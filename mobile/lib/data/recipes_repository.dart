import 'package:dio/dio.dart';

import '../api/api_exception.dart';
import '../models/recipe.dart';
import '../models/recipe_page.dart';
import '../models/recipe_update.dart';

/// Espelha `recipesApi` em `frontend/src/api/endpoints.ts` e as rotas de
/// `backend/app/api/recipes.py`.
class RecipesRepository {
  final Dio _dio;
  RecipesRepository(this._dio);

  Future<RecipePage> list({
    String? q,
    String? tag,
    bool? favorite,
    int limit = 20,
    String? cursor,
  }) async {
    try {
      final response = await _dio.get('/recipes', queryParameters: {
        if (q != null && q.isNotEmpty) 'q': q,
        if (tag != null && tag.isNotEmpty) 'tag': tag,
        'favorite': ?favorite,
        'limit': limit,
        'cursor': ?cursor,
      });
      return RecipePage.fromJson((response.data as Map).cast<String, dynamic>());
    } on DioException catch (e) {
      throw apiExceptionFrom(e);
    }
  }

  Future<RecipeTags> tags() async {
    try {
      final response = await _dio.get('/recipes/tags');
      return RecipeTags.fromJson((response.data as Map).cast<String, dynamic>());
    } on DioException catch (e) {
      throw apiExceptionFrom(e);
    }
  }

  Future<Recipe> get(String id) async {
    try {
      final response = await _dio.get('/recipes/$id');
      return Recipe.fromJson((response.data as Map).cast<String, dynamic>());
    } on DioException catch (e) {
      throw apiExceptionFrom(e);
    }
  }

  Future<Recipe> update(String id, RecipeUpdate body) async {
    try {
      final response = await _dio.patch('/recipes/$id', data: body.toJson());
      return Recipe.fromJson((response.data as Map).cast<String, dynamic>());
    } on DioException catch (e) {
      throw apiExceptionFrom(e);
    }
  }

  Future<void> remove(String id) async {
    try {
      await _dio.delete('/recipes/$id');
    } on DioException catch (e) {
      throw apiExceptionFrom(e);
    }
  }

  Future<Recipe> reset(String id) async {
    try {
      final response = await _dio.post('/recipes/$id/reset');
      return Recipe.fromJson((response.data as Map).cast<String, dynamic>());
    } on DioException catch (e) {
      throw apiExceptionFrom(e);
    }
  }
}
