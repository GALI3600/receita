import 'package:flutter/material.dart';

/// Notas pessoais, com edição — espelha `PersonalNotes` de
/// `frontend/src/components/recipe/PersonalNotes.tsx` e a seção dedicada que aparece na
/// impressão.
class NotesSection extends StatelessWidget {
  final String? notes;
  final ValueChanged<String?> onSave;

  const NotesSection({super.key, required this.notes, required this.onSave});

  Future<void> _edit(BuildContext context) async {
    final controller = TextEditingController(text: notes ?? '');
    final result = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Minhas anotações'),
        content: TextField(
          controller: controller,
          maxLines: 6,
          autofocus: true,
          decoration: const InputDecoration(hintText: 'Escreva aqui suas observações…'),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Cancelar'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, controller.text),
            child: const Text('Salvar'),
          ),
        ],
      ),
    );
    if (result != null) onSave(result.trim().isEmpty ? null : result.trim());
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return InkWell(
      onTap: () => _edit(context),
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          border: Border.all(color: theme.dividerColor),
          borderRadius: BorderRadius.circular(8),
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Minhas anotações', style: theme.textTheme.titleSmall),
                  const SizedBox(height: 4),
                  Text(
                    (notes == null || notes!.isEmpty) ? 'Toque para adicionar uma nota.' : notes!,
                    style: theme.textTheme.bodyMedium?.copyWith(
                      color: (notes == null || notes!.isEmpty) ? Colors.black38 : null,
                    ),
                  ),
                ],
              ),
            ),
            const Icon(Icons.edit_outlined, size: 18),
          ],
        ),
      ),
    );
  }
}
