import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../widgets/error_banner.dart';
import '../../../widgets/password_field.dart';
import '../application/auth_providers.dart';

class LoginScreen extends ConsumerStatefulWidget {
  const LoginScreen({super.key});

  @override
  ConsumerState<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends ConsumerState<LoginScreen> {
  final _formKey = GlobalKey<FormState>();
  final _emailController = TextEditingController();
  final _passwordController = TextEditingController();
  bool _submitting = false;
  Object? _lastError;

  @override
  void dispose() {
    _emailController.dispose();
    _passwordController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() {
      _submitting = true;
      _lastError = null;
    });
    await ref.read(sessionProvider.notifier).login(
          email: _emailController.text.trim(),
          password: _passwordController.text,
        );
    final session = ref.read(sessionProvider);
    if (!mounted) return;
    if (session.hasValue && session.value != null) {
      context.go('/livro');
      return;
    }
    setState(() {
      _submitting = false;
      _lastError = session.hasError ? session.error : null;
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Entrar')),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: Form(
            key: _formKey,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text('Receita', style: Theme.of(context).textTheme.headlineMedium),
                const SizedBox(height: 4),
                Text(
                  'Entre para ver o seu livro de receitas.',
                  style: Theme.of(context).textTheme.bodyMedium,
                ),
                const SizedBox(height: 24),
                if (_lastError != null) ...[
                  ErrorBanner(error: _lastError!),
                  const SizedBox(height: 16),
                ],
                TextFormField(
                  controller: _emailController,
                  decoration: const InputDecoration(labelText: 'E-mail'),
                  keyboardType: TextInputType.emailAddress,
                  autofillHints: const [AutofillHints.email],
                  validator: (value) =>
                      (value == null || value.trim().isEmpty) ? 'Informe o e-mail' : null,
                ),
                const SizedBox(height: 12),
                PasswordField(
                  controller: _passwordController,
                  label: 'Senha',
                  autofillHints: const [AutofillHints.password],
                  validator: (value) =>
                      (value == null || value.isEmpty) ? 'Informe a senha' : null,
                  onFieldSubmitted: (_) => _submit(),
                ),
                const SizedBox(height: 24),
                FilledButton(
                  onPressed: _submitting ? null : _submit,
                  child: _submitting
                      ? const SizedBox(
                          height: 16,
                          width: 16,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Text('Entrar'),
                ),
                const SizedBox(height: 12),
                TextButton(
                  onPressed: () => context.push('/esqueci-senha'),
                  child: const Text('Esqueci minha senha'),
                ),
                TextButton(
                  onPressed: () => context.push('/cadastro'),
                  child: const Text('Criar uma conta'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
