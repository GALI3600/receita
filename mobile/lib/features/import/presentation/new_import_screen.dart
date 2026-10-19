import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../models/import_out.dart';
import '../../../widgets/error_banner.dart';
import '../application/import_providers.dart';

class NewImportScreen extends ConsumerStatefulWidget {
  const NewImportScreen({super.key});

  @override
  ConsumerState<NewImportScreen> createState() => _NewImportScreenState();
}

class _NewImportScreenState extends ConsumerState<NewImportScreen> {
  final _urlController = TextEditingController();

  @override
  void initState() {
    super.initState();
    // Começa limpo a cada visita à tela, mesmo que um import anterior tenha terminado.
    Future.microtask(() => ref.read(importControllerProvider.notifier).reset());
  }

  @override
  void dispose() {
    _urlController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    ref.listen(importControllerProvider, (previous, next) {
      final imp = next.value;
      if (imp != null && imp.status == ImportStatus.done && imp.recipeId != null) {
        context.go('/receitas/${imp.recipeId}');
      }
    });

    final importState = ref.watch(importControllerProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('Importar vídeo')),
      body: Padding(
        padding: const EdgeInsets.all(24),
        child: importState.when(
          data: (imp) => imp == null
              ? _UrlForm(controller: _urlController)
              : _ImportProgress(imp: imp),
          loading: () => const Center(child: CircularProgressIndicator()),
          error: (error, _) => Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              ErrorBanner(error: error),
              const SizedBox(height: 16),
              _UrlForm(controller: _urlController),
            ],
          ),
        ),
      ),
    );
  }
}

class _UrlForm extends ConsumerWidget {
  final TextEditingController controller;
  const _UrlForm({required this.controller});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          'Cole o link de um vídeo de receita do YouTube.',
          style: Theme.of(context).textTheme.bodyMedium,
        ),
        const SizedBox(height: 16),
        TextField(
          controller: controller,
          decoration: const InputDecoration(labelText: 'URL do vídeo'),
          keyboardType: TextInputType.url,
        ),
        const SizedBox(height: 24),
        FilledButton(
          onPressed: () {
            final url = controller.text.trim();
            if (url.isEmpty) return;
            ref.read(importControllerProvider.notifier).submit(url);
          },
          child: const Text('Importar'),
        ),
      ],
    );
  }
}

class _ImportProgress extends ConsumerWidget {
  final ImportOut imp;
  const _ImportProgress({required this.imp});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    if (imp.status == ImportStatus.failed) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          ErrorBanner(
            error: Exception(imp.error?.message ?? 'Não foi possível importar esse vídeo.'),
          ),
          const SizedBox(height: 16),
          FilledButton(
            onPressed: () => ref.read(importControllerProvider.notifier).reset(),
            child: const Text('Tentar outro vídeo'),
          ),
        ],
      );
    }

    final states = importStageStates(imp.status);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(importStatusAnnouncement(imp), style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 24),
        for (var i = 0; i < importStages.length; i++)
          _StageRow(label: importStages[i].label, state: states[i]),
      ],
    );
  }
}

class _StageRow extends StatelessWidget {
  final String label;
  final StageState state;
  const _StageRow({required this.label, required this.state});

  @override
  Widget build(BuildContext context) {
    final icon = switch (state) {
      StageState.done => const Icon(Icons.check_circle, color: Colors.green),
      StageState.current => const SizedBox(
          height: 20, width: 20, child: CircularProgressIndicator(strokeWidth: 2)),
      StageState.upcoming => const Icon(Icons.radio_button_unchecked, color: Colors.black26),
    };
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Row(
        children: [
          icon,
          const SizedBox(width: 12),
          Text(label, style: Theme.of(context).textTheme.bodyLarge),
        ],
      ),
    );
  }
}
