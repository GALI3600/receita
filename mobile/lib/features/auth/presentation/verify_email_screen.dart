import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../api/api_exception.dart';
import '../../../providers/core_providers.dart';
import '../../../widgets/error_banner.dart';

/// Confirmação de e-mail. Na web o token vem de um link no e-mail (query param);
/// como ainda não há deep link configurado no app (ver plano: ponto aberto), o token é
/// colado manualmente aqui.
class VerifyEmailScreen extends ConsumerStatefulWidget {
  const VerifyEmailScreen({super.key});

  @override
  ConsumerState<VerifyEmailScreen> createState() => _VerifyEmailScreenState();
}

class _VerifyEmailScreenState extends ConsumerState<VerifyEmailScreen> {
  final _tokenController = TextEditingController();
  bool _submitting = false;
  Object? _error;
  bool _verified = false;

  @override
  void dispose() {
    _tokenController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final token = _tokenController.text.trim();
    if (token.isEmpty) return;
    setState(() {
      _submitting = true;
      _error = null;
    });
    try {
      await ref.read(authRepositoryProvider).verifyEmail(token);
      if (!mounted) return;
      setState(() => _verified = true);
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() => _error = e);
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_verified) {
      return Scaffold(
        appBar: AppBar(title: const Text('E-mail confirmado')),
        body: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const Text('Conta confirmada! Agora você já pode entrar.'),
              const SizedBox(height: 16),
              FilledButton(
                onPressed: () => context.go('/entrar'),
                child: const Text('Ir para o login'),
              ),
            ],
          ),
        ),
      );
    }

    return Scaffold(
      appBar: AppBar(title: const Text('Confirmar e-mail')),
      body: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              'Cole aqui o código do link que enviamos para o seu e-mail.',
              style: Theme.of(context).textTheme.bodyMedium,
            ),
            const SizedBox(height: 16),
            if (_error != null) ...[
              ErrorBanner(error: _error!),
              const SizedBox(height: 16),
            ],
            TextField(
              controller: _tokenController,
              decoration: const InputDecoration(labelText: 'Código de confirmação'),
            ),
            const SizedBox(height: 24),
            FilledButton(
              onPressed: _submitting ? null : _submit,
              child: _submitting
                  ? const SizedBox(
                      height: 16, width: 16, child: CircularProgressIndicator(strokeWidth: 2))
                  : const Text('Confirmar'),
            ),
          ],
        ),
      ),
    );
  }
}
