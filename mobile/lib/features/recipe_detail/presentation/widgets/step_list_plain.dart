import 'package:flutter/material.dart' hide Step;

import '../../../../models/recipe.dart';

/// Passos numerados em texto puro — a diferença central em relação à web: sem chips de
/// timestamp, sem `onSeek`, sem destaque de "passo ativo" ligado ao vídeo (que nem existe
/// aqui). Espelha o visual da impressão (`StepList` com `onSeek == null` em
/// `frontend/src/components/recipe/StepList.tsx`).
class StepListPlain extends StatelessWidget {
  final List<Step> steps;

  const StepListPlain({super.key, required this.steps});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        for (final step in steps)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 10),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                CircleAvatar(
                  radius: 14,
                  backgroundColor: theme.colorScheme.primaryContainer,
                  child: Text(
                    '${step.order}',
                    style: TextStyle(color: theme.colorScheme.onPrimaryContainer, fontSize: 13),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(child: Text(step.text, style: theme.textTheme.bodyLarge)),
              ],
            ),
          ),
      ],
    );
  }
}
