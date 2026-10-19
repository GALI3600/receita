import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'api/api_client.dart';
import 'app_theme.dart';
import 'providers/core_providers.dart';
import 'router.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final dio = await buildApiClient();

  runApp(
    ProviderScope(
      overrides: [dioProvider.overrideWithValue(dio)],
      child: const ReceitaApp(),
    ),
  );
}

class ReceitaApp extends ConsumerWidget {
  const ReceitaApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final router = ref.watch(routerProvider);
    return MaterialApp.router(
      title: 'Receita',
      debugShowCheckedModeBanner: false,
      theme: buildAppTheme(),
      routerConfig: router,
    );
  }
}
