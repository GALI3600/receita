import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'features/account/presentation/account_screen.dart';
import 'features/auth/application/auth_providers.dart';
import 'features/auth/presentation/forgot_password_screen.dart';
import 'features/auth/presentation/login_screen.dart';
import 'features/auth/presentation/register_screen.dart';
import 'features/auth/presentation/reset_password_screen.dart';
import 'features/auth/presentation/verify_email_screen.dart';
import 'features/book/presentation/book_screen.dart';
import 'features/import/presentation/new_import_screen.dart';
import 'features/landing/presentation/landing_screen.dart';
import 'features/recipe_detail/presentation/recipe_detail_screen.dart';

const Set<String> _publicRoutes = {
  '/',
  '/entrar',
  '/cadastro',
  '/verificar-email',
  '/esqueci-senha',
  '/redefinir-senha',
};

/// Reage a mudanças de `sessionProvider` para o go_router recalcular o `redirect`
/// (guarda de autenticação) sempre que o usuário entra/sai.
class _AuthRefreshNotifier extends ChangeNotifier {
  _AuthRefreshNotifier(Ref ref) {
    ref.listen(sessionProvider, (previous, next) => notifyListeners());
  }
}

final routerProvider = Provider<GoRouter>((ref) {
  final authRefresh = _AuthRefreshNotifier(ref);

  return GoRouter(
    initialLocation: '/',
    refreshListenable: authRefresh,
    redirect: (context, state) {
      final session = ref.read(sessionProvider);
      if (session.isLoading) return null;

      final loggedIn = session.value != null;
      final isPublic = _publicRoutes.contains(state.matchedLocation);

      if (!loggedIn && !isPublic) return '/entrar';
      if (loggedIn && (state.matchedLocation == '/' || state.matchedLocation == '/entrar')) {
        return '/livro';
      }
      return null;
    },
    routes: [
      GoRoute(path: '/', builder: (context, state) => const LandingScreen()),
      GoRoute(path: '/cadastro', builder: (context, state) => const RegisterScreen()),
      GoRoute(path: '/entrar', builder: (context, state) => const LoginScreen()),
      GoRoute(path: '/verificar-email', builder: (context, state) => const VerifyEmailScreen()),
      GoRoute(path: '/esqueci-senha', builder: (context, state) => const ForgotPasswordScreen()),
      GoRoute(path: '/redefinir-senha', builder: (context, state) => const ResetPasswordScreen()),
      GoRoute(path: '/livro', builder: (context, state) => const BookScreen()),
      GoRoute(path: '/nova', builder: (context, state) => const NewImportScreen()),
      GoRoute(
        path: '/receitas/:id',
        builder: (context, state) =>
            RecipeDetailScreen(recipeId: state.pathParameters['id']!),
      ),
      GoRoute(path: '/conta', builder: (context, state) => const AccountScreen()),
    ],
    errorBuilder: (context, state) => Scaffold(
      appBar: AppBar(title: const Text('Página não encontrada')),
      body: const Center(child: Text('Não encontramos o que você procurou.')),
    ),
  );
});
