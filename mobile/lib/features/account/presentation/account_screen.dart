import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';

import '../../../widgets/error_banner.dart';
import '../../auth/application/auth_providers.dart';

/// Espelha `/conta` na web: dados da conta e cota de importações
/// (`GET /api/auth/me` → `MeOut`/`QuotaOut` em `backend/app/schemas/auth.py`) e logout.
class AccountScreen extends ConsumerWidget {
  const AccountScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final session = ref.watch(sessionProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('Conta')),
      body: session.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (error, _) => Center(
          child: Padding(padding: const EdgeInsets.all(24), child: ErrorBanner(error: error)),
        ),
        data: (me) {
          if (me == null) {
            return const Center(child: Text('Você não está conectado.'));
          }
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              ListTile(
                leading: const Icon(Icons.person_outline),
                title: Text(me.name),
                subtitle: Text(me.email),
                trailing: me.emailVerified
                    ? const Icon(Icons.verified, color: Colors.green)
                    : const Icon(Icons.warning_amber, color: Colors.orange),
              ),
              const Divider(),
              ListTile(
                leading: const Icon(Icons.bolt_outlined),
                title: const Text('Importações hoje'),
                subtitle: Text('${me.quota.used} de ${me.quota.limit} usadas'),
              ),
              ListTile(
                leading: const Icon(Icons.restart_alt),
                title: const Text('Cota renova em'),
                subtitle: Text(DateFormat('dd/MM/yyyy HH:mm').format(me.quota.resetsAt.toLocal())),
              ),
              const SizedBox(height: 24),
              OutlinedButton.icon(
                onPressed: () async {
                  await ref.read(sessionProvider.notifier).logout();
                  if (context.mounted) context.go('/entrar');
                },
                icon: const Icon(Icons.logout),
                label: const Text('Sair'),
              ),
            ],
          );
        },
      ),
    );
  }
}
