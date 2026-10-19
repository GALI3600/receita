import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../models/import_out.dart';
import '../../../providers/core_providers.dart';

/// Submete um vídeo e acompanha o status com polling, no mesmo ritmo de
/// `pollInterval`/`IMPORT_STAGES` de `frontend/src/lib/importStatus.ts`.
class ImportController extends AsyncNotifier<ImportOut?> {
  Timer? _timer;
  DateTime? _startedAt;

  @override
  Future<ImportOut?> build() {
    ref.onDispose(() => _timer?.cancel());
    return Future.value(null);
  }

  Future<void> submit(String url) async {
    _timer?.cancel();
    state = const AsyncLoading();
    try {
      final imp = await ref.read(importsRepositoryProvider).submit(url);
      _startedAt = DateTime.now();
      state = AsyncData(imp);
      _scheduleNextPoll(imp);
    } catch (e, st) {
      state = AsyncError(e, st);
    }
  }

  void reset() {
    _timer?.cancel();
    state = const AsyncData(null);
  }

  void _scheduleNextPoll(ImportOut imp) {
    final elapsed = DateTime.now().difference(_startedAt ?? DateTime.now());
    final intervalMs = importPollIntervalMs(imp, elapsed);
    if (intervalMs == null) return;
    _timer = Timer(Duration(milliseconds: intervalMs), () => _poll(imp.id));
  }

  Future<void> _poll(String id) async {
    try {
      final imp = await ref.read(importsRepositoryProvider).get(id);
      state = AsyncData(imp);
      _scheduleNextPoll(imp);
    } catch (e, st) {
      state = AsyncError(e, st);
    }
  }
}

final importControllerProvider =
    AsyncNotifierProvider<ImportController, ImportOut?>(ImportController.new);
