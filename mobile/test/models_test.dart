import 'package:app/api/api_exception.dart';
import 'package:app/features/book/application/recipe_list_providers.dart';
import 'package:app/models/import_out.dart';
import 'package:app/models/recipe.dart';
import 'package:app/models/recipe_update.dart';
import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('RecipeListFilters.copyWith', () {
    test('clearQuery actually clears q, instead of keeping the old value', () {
      const filters = RecipeListFilters(q: 'bolo');
      final cleared = filters.copyWith(clearQuery: true);
      expect(cleared.q, isNull);
    });

    test('clearFavorite clears favorite without touching q', () {
      const filters = RecipeListFilters(q: 'bolo', favorite: true);
      final cleared = filters.copyWith(clearFavorite: true);
      expect(cleared.favorite, isNull);
      expect(cleared.q, 'bolo');
    });
  });

  group('Recipe.fromJson', () {
    test('parses a full recipe payload matching RecipeOut', () {
      final json = {
        'id': 'r1',
        'title': 'Bolo de Chocolate',
        'summary': 'Bolo denso e úmido.',
        'prep_time_min': 20,
        'cook_time_min': 35,
        'difficulty': 'média',
        'tags': ['sobremesa', 'chocolate'],
        'is_favorite': true,
        'rating': 5,
        'created_at': '2026-01-01T00:00:00Z',
        'updated_at': '2026-01-02T00:00:00Z',
        'video': {
          'youtube_id': 'abc123',
          'title': 'Como fazer o bolo',
          'channel': 'Chef Maria',
          'thumbnail_url': 'https://example.com/thumb.jpg',
          'duration_s': 480,
        },
        'servings': '8 fatias',
        'ingredients': [
          {'name': 'farinha de trigo', 'quantity': '2', 'unit': 'xícaras', 'note': 'peneirada', 'group': 'massa'},
        ],
        'steps': [
          {'order': 1, 'text': 'Peneira a farinha.', 'video_timestamp_s': 45},
        ],
        'tips': ['Use chocolate de qualidade'],
        'user_notes': 'Meu favorito',
      };

      final recipe = Recipe.fromJson(json);

      expect(recipe.title, 'Bolo de Chocolate');
      expect(recipe.servings, '8 fatias');
      expect(recipe.ingredients, hasLength(1));
      expect(recipe.ingredients.first.group, 'massa');
      expect(recipe.steps.single.videoTimestampS, 45);
      expect(recipe.video.youtubeId, 'abc123');
      expect(recipe.isFavorite, isTrue);
    });
  });

  group('RecipeUpdate', () {
    test('only serializes fields that were explicitly set', () {
      final update = RecipeUpdate()..setIsFavorite(true);
      expect(update.toJson(), {'is_favorite': true});
    });

    test('explicit null clears an optional field like user_notes', () {
      final update = RecipeUpdate()..setUserNotes(null);
      expect(update.toJson(), {'user_notes': null});
      expect(update.toJson().containsKey('title'), isFalse);
    });
  });

  group('import polling helpers', () {
    test('stops polling once terminal', () {
      final imp = _import(status: ImportStatus.done);
      expect(importPollIntervalMs(imp, Duration.zero), isNull);
    });

    test('polls slowly while deferred', () {
      final imp = _import(status: ImportStatus.deferred);
      expect(importPollIntervalMs(imp, Duration.zero), 60000);
    });

    test('stage states mark earlier stages as done', () {
      final states = importStageStates(ImportStatus.generating);
      expect(states, [StageState.done, StageState.done, StageState.current]);
    });
  });

  group('ApiException.fromDioException', () {
    test('parses the backend {"error": {...}} shape', () {
      final requestOptions = RequestOptions(path: '/recipes/1');
      final response = Response(
        requestOptions: requestOptions,
        statusCode: 404,
        data: {
          'error': {'code': 'not_found', 'message': 'Não encontramos o que você procurou.'}
        },
      );
      final dioError = DioException(requestOptions: requestOptions, response: response);

      final apiException = ApiException.fromDioException(dioError);

      expect(apiException.status, 404);
      expect(apiException.code, 'not_found');
      expect(apiException.message, 'Não encontramos o que você procurou.');
    });
  });
}

ImportOut _import({required ImportStatus status, int? queuePosition}) {
  return ImportOut(
    id: 'i1',
    url: 'https://youtube.com/watch?v=abc',
    youtubeId: 'abc',
    status: status,
    queuePosition: queuePosition,
    createdAt: DateTime.now(),
    updatedAt: DateTime.now(),
  );
}
