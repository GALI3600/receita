import 'package:flutter/material.dart';

/// Lista de dicas, mostrada só quando não vazia — espelha a seção `Dicas` da impressão.
class TipsSection extends StatelessWidget {
  final List<String> tips;

  const TipsSection({super.key, required this.tips});

  @override
  Widget build(BuildContext context) {
    if (tips.isEmpty) return const SizedBox.shrink();
    final theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text('Dicas', style: theme.textTheme.titleMedium),
        const SizedBox(height: 8),
        for (final tip in tips)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 4),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text('•  '),
                Expanded(child: Text(tip, style: theme.textTheme.bodyMedium)),
              ],
            ),
          ),
      ],
    );
  }
}
