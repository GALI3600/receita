import 'package:flutter/material.dart';

import '../api/api_exception.dart';

/// Mensagem de erro inline, no mesmo espírito do componente `Alert` da web
/// (`frontend/src/components/ui`): usada para mostrar `ApiException.message` em
/// formulários e telas que falharam ao carregar.
class ErrorBanner extends StatelessWidget {
  final Object error;

  const ErrorBanner({super.key, required this.error});

  String get _message {
    if (error is ApiException) return (error as ApiException).message;
    return 'Algo deu errado. Tente de novo em alguns instantes.';
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: scheme.errorContainer,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        children: [
          Icon(Icons.error_outline, color: scheme.onErrorContainer),
          const SizedBox(width: 8),
          Expanded(
            child: Text(_message, style: TextStyle(color: scheme.onErrorContainer)),
          ),
        ],
      ),
    );
  }
}
