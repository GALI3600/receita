import 'package:flutter/material.dart';

import '../../../../models/recipe.dart';

/// Ingredientes como checklist — espelha a lista de 2 colunas com caixinhas vazias
/// da impressão (`.ingredient-check` em `frontend/src/index.css`), mas aqui a caixinha
/// é de fato marcável (o estado é só local/visual, não persiste no backend — assim como
/// a marcação no papel impresso também não persiste em lugar algum).
class IngredientChecklist extends StatefulWidget {
  final List<Ingredient> ingredients;

  const IngredientChecklist({super.key, required this.ingredients});

  @override
  State<IngredientChecklist> createState() => _IngredientChecklistState();
}

class _IngredientChecklistState extends State<IngredientChecklist> {
  final Set<int> _checked = {};

  @override
  Widget build(BuildContext context) {
    final groups = <String?, List<MapEntry<int, Ingredient>>>{};
    for (final entry in widget.ingredients.asMap().entries) {
      groups.putIfAbsent(entry.value.group, () => []).add(entry);
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        for (final group in groups.entries) ...[
          if (group.key != null) ...[
            Padding(
              padding: const EdgeInsets.only(top: 12, bottom: 4),
              child: Text(
                group.key!,
                style: Theme.of(context)
                    .textTheme
                    .labelLarge
                    ?.copyWith(fontWeight: FontWeight.bold),
              ),
            ),
          ],
          for (final entry in group.value) _IngredientRow(
            ingredient: entry.value,
            checked: _checked.contains(entry.key),
            onChanged: (value) => setState(() {
              if (value) {
                _checked.add(entry.key);
              } else {
                _checked.remove(entry.key);
              }
            }),
          ),
        ],
      ],
    );
  }
}

class _IngredientRow extends StatelessWidget {
  final Ingredient ingredient;
  final bool checked;
  final ValueChanged<bool> onChanged;

  const _IngredientRow({required this.ingredient, required this.checked, required this.onChanged});

  @override
  Widget build(BuildContext context) {
    final parts = [
      if (ingredient.quantity != null) ingredient.quantity!,
      if (ingredient.unit != null) ingredient.unit!,
      ingredient.name,
    ].join(' ');

    return CheckboxListTile(
      value: checked,
      onChanged: (value) => onChanged(value ?? false),
      controlAffinity: ListTileControlAffinity.leading,
      contentPadding: EdgeInsets.zero,
      dense: true,
      title: Text(
        parts,
        style: checked
            ? const TextStyle(decoration: TextDecoration.lineThrough, color: Colors.black38)
            : null,
      ),
      subtitle: ingredient.note != null ? Text(ingredient.note!) : null,
    );
  }
}
