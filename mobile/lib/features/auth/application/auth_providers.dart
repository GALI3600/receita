import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../models/me.dart';
import '../../../providers/core_providers.dart';

/// Sessão atual do usuário — papel equivalente a `useMe` combinado com o
/// `handleUnauthorized` (cache-clearing em 401) de `frontend/src/api/queries.ts`.
class SessionNotifier extends AsyncNotifier<Me?> {
  @override
  Future<Me?> build() => _tryLoad();

  Future<Me?> _tryLoad() async {
    try {
      return await ref.read(authRepositoryProvider).me();
    } on Object {
      // Sem sessão válida (401) ou servidor fora: trata como deslogado. A tela que
      // precisar distinguir "deslogado" de "erro de rede" deve chamar os métodos do
      // AuthRepository diretamente (ex.: na tela de login) em vez de depender deste provider.
      return null;
    }
  }

  Future<void> login({required String email, required String password}) async {
    state = const AsyncLoading();
    state = await AsyncValue.guard(
      () => ref.read(authRepositoryProvider).login(email: email, password: password),
    );
  }

  Future<void> logout() async {
    await ref.read(authRepositoryProvider).logout();
    state = const AsyncData(null);
  }

  Future<void> refresh() async {
    state = await AsyncValue.guard(_tryLoad);
  }

  /// Usado quando qualquer outra chamada à API recebe 401: a sessão expirou.
  void clear() {
    state = const AsyncData(null);
  }
}

final sessionProvider = AsyncNotifierProvider<SessionNotifier, Me?>(SessionNotifier.new);
