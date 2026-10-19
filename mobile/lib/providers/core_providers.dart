import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../data/auth_repository.dart';
import '../data/imports_repository.dart';
import '../data/recipes_repository.dart';

/// Sobrescrito em `main.dart` (via `ProviderScope(overrides: [...])`) depois que
/// `buildApiClient()` resolve — montar o Dio exige `await` (cookie jar persistente em
/// disco via `path_provider`), então não dá para inicializar de forma síncrona aqui.
final dioProvider = Provider<Dio>((ref) {
  throw UnimplementedError('dioProvider precisa ser sobrescrito em main.dart');
});

final authRepositoryProvider =
    Provider<AuthRepository>((ref) => AuthRepository(ref.watch(dioProvider)));

final recipesRepositoryProvider =
    Provider<RecipesRepository>((ref) => RecipesRepository(ref.watch(dioProvider)));

final importsRepositoryProvider =
    Provider<ImportsRepository>((ref) => ImportsRepository(ref.watch(dioProvider)));
