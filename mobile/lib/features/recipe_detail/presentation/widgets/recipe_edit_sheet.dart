import 'package:flutter/material.dart' hide Step;

import '../../../../models/recipe.dart';
import '../../../../models/recipe_update.dart';

class _IngredientRowControllers {
  final TextEditingController name;
  final TextEditingController quantity;
  final TextEditingController unit;
  final TextEditingController note;
  final TextEditingController group;

  _IngredientRowControllers({Ingredient? from})
      : name = TextEditingController(text: from?.name ?? ''),
        quantity = TextEditingController(text: from?.quantity ?? ''),
        unit = TextEditingController(text: from?.unit ?? ''),
        note = TextEditingController(text: from?.note ?? ''),
        group = TextEditingController(text: from?.group ?? '');

  IngredientIn toIngredientIn() => IngredientIn(
        name: name.text.trim(),
        quantity: quantity.text.trim().isEmpty ? null : quantity.text.trim(),
        unit: unit.text.trim().isEmpty ? null : unit.text.trim(),
        note: note.text.trim().isEmpty ? null : note.text.trim(),
        group: group.text.trim().isEmpty ? null : group.text.trim(),
      );

  void dispose() {
    name.dispose();
    quantity.dispose();
    unit.dispose();
    note.dispose();
    group.dispose();
  }
}

class _StepRowControllers {
  final TextEditingController text;
  final int? videoTimestampS;

  _StepRowControllers({Step? from})
      : text = TextEditingController(text: from?.text ?? ''),
        videoTimestampS = from?.videoTimestampS;

  StepIn toStepIn() => StepIn(text: text.text.trim(), videoTimestampS: videoTimestampS);

  void dispose() => text.dispose();
}

/// Formulário de edição — espelha os campos editáveis de `RecipeUpdate`
/// (`backend/app/schemas/recipes.py`): título, resumo, porções, tempos, ingredientes, passos e
/// dicas. Dificuldade e tags não têm mais campo aqui (removidos da UI); como só os campos
/// realmente alterados são enviados (`RecipeUpdate.setX`), o backend simplesmente preserva o
/// que já estava salvo para eles.
class RecipeEditSheet extends StatefulWidget {
  final Recipe recipe;

  const RecipeEditSheet({super.key, required this.recipe});

  @override
  State<RecipeEditSheet> createState() => _RecipeEditSheetState();
}

class _RecipeEditSheetState extends State<RecipeEditSheet> {
  late final TextEditingController _title;
  late final TextEditingController _summary;
  late final TextEditingController _servings;
  late final TextEditingController _prepTime;
  late final TextEditingController _cookTime;
  late final TextEditingController _tips;
  late final List<_IngredientRowControllers> _ingredients;
  late final List<_StepRowControllers> _steps;

  @override
  void initState() {
    super.initState();
    final recipe = widget.recipe;
    _title = TextEditingController(text: recipe.title);
    _summary = TextEditingController(text: recipe.summary);
    _servings = TextEditingController(text: recipe.servings ?? '');
    _prepTime = TextEditingController(text: recipe.prepTimeMin?.toString() ?? '');
    _cookTime = TextEditingController(text: recipe.cookTimeMin?.toString() ?? '');
    _tips = TextEditingController(text: recipe.tips.join('\n'));
    _ingredients = recipe.ingredients.map((i) => _IngredientRowControllers(from: i)).toList();
    _steps = recipe.steps.map((s) => _StepRowControllers(from: s)).toList();
  }

  @override
  void dispose() {
    _title.dispose();
    _summary.dispose();
    _servings.dispose();
    _prepTime.dispose();
    _cookTime.dispose();
    _tips.dispose();
    for (final i in _ingredients) {
      i.dispose();
    }
    for (final s in _steps) {
      s.dispose();
    }
    super.dispose();
  }

  void _save() {
    final update = RecipeUpdate()
      ..setTitle(_title.text.trim())
      ..setSummary(_summary.text.trim())
      ..setServings(_servings.text.trim().isEmpty ? null : _servings.text.trim())
      ..setPrepTimeMin(int.tryParse(_prepTime.text.trim()))
      ..setCookTimeMin(int.tryParse(_cookTime.text.trim()))
      ..setTips(_tips.text.split('\n').map((t) => t.trim()).where((t) => t.isNotEmpty).toList())
      ..setIngredients(
        _ingredients.map((i) => i.toIngredientIn()).where((i) => i.name.isNotEmpty).toList(),
      )
      ..setSteps(
        _steps.map((s) => s.toStepIn()).where((s) => s.text.isNotEmpty).toList(),
      );
    Navigator.pop(context, update);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Editar receita'),
        actions: [
          TextButton(
            onPressed: _save,
            child: const Text('Salvar'),
          ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          TextField(controller: _title, decoration: const InputDecoration(labelText: 'Título')),
          const SizedBox(height: 12),
          TextField(
            controller: _summary,
            decoration: const InputDecoration(labelText: 'Resumo'),
            maxLines: 3,
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _servings,
            decoration: const InputDecoration(labelText: 'Porções'),
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded(
                child: TextField(
                  controller: _prepTime,
                  decoration: const InputDecoration(labelText: 'Preparo (min)'),
                  keyboardType: TextInputType.number,
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: TextField(
                  controller: _cookTime,
                  decoration: const InputDecoration(labelText: 'Forno/fogo (min)'),
                  keyboardType: TextInputType.number,
                ),
              ),
            ],
          ),
          const SizedBox(height: 24),
          Text('Ingredientes', style: Theme.of(context).textTheme.titleMedium),
          for (final ingredient in _ingredients) _IngredientEditRow(
            controllers: ingredient,
            onRemove: () => setState(() => _ingredients.remove(ingredient)),
          ),
          OutlinedButton.icon(
            onPressed: () => setState(() => _ingredients.add(_IngredientRowControllers())),
            icon: const Icon(Icons.add),
            label: const Text('Adicionar ingrediente'),
          ),
          const SizedBox(height: 24),
          Text('Passos', style: Theme.of(context).textTheme.titleMedium),
          for (var i = 0; i < _steps.length; i++) _StepEditRow(
            order: i + 1,
            controllers: _steps[i],
            onRemove: () => setState(() => _steps.removeAt(i)),
          ),
          OutlinedButton.icon(
            onPressed: () => setState(() => _steps.add(_StepRowControllers())),
            icon: const Icon(Icons.add),
            label: const Text('Adicionar passo'),
          ),
          const SizedBox(height: 24),
          TextField(
            controller: _tips,
            decoration: const InputDecoration(labelText: 'Dicas (uma por linha)'),
            maxLines: 4,
          ),
          const SizedBox(height: 32),
        ],
      ),
    );
  }
}

/// Cada ingrediente ocupa duas linhas (qtd./unidade numa, nome na outra) em vez de três
/// campos espremidos numa linha só — numa tela de celular, "colheres de sopa" não cabia e
/// o texto digitado ficava ilegível dentro da caixa estreita.
class _IngredientEditRow extends StatelessWidget {
  final _IngredientRowControllers controllers;
  final VoidCallback onRemove;

  const _IngredientEditRow({required this.controllers, required this.onRemove});

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.symmetric(vertical: 6),
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        border: Border.all(color: Theme.of(context).dividerColor),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                flex: 2,
                child: TextField(
                  controller: controllers.quantity,
                  decoration: const InputDecoration(labelText: 'Qtd.', isDense: true),
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                flex: 3,
                child: TextField(
                  controller: controllers.unit,
                  decoration: const InputDecoration(labelText: 'Unidade', isDense: true),
                ),
              ),
              IconButton(
                icon: const Icon(Icons.close, size: 18),
                onPressed: onRemove,
                tooltip: 'Remover ingrediente',
              ),
            ],
          ),
          const SizedBox(height: 8),
          TextField(
            controller: controllers.name,
            decoration: const InputDecoration(labelText: 'Ingrediente', isDense: true),
          ),
        ],
      ),
    );
  }
}

class _StepEditRow extends StatelessWidget {
  final int order;
  final _StepRowControllers controllers;
  final VoidCallback onRemove;

  const _StepEditRow({required this.order, required this.controllers, required this.onRemove});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.only(top: 14, right: 8),
            child: Text('$order.'),
          ),
          Expanded(
            child: TextField(
              controller: controllers.text,
              decoration: const InputDecoration(isDense: true),
              maxLines: 3,
            ),
          ),
          IconButton(icon: const Icon(Icons.close, size: 18), onPressed: onRemove),
        ],
      ),
    );
  }
}
