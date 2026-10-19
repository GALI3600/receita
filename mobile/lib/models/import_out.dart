/// Espelha `ImportStatus` em `backend/app/models/enums.py`.
enum ImportStatus {
  pending,
  fetching,
  transcribing,
  generating,
  done,
  failed,
  deferred;

  static ImportStatus fromJson(String value) =>
      ImportStatus.values.firstWhere((s) => s.name == value);

  bool get isTerminal => this == ImportStatus.done || this == ImportStatus.failed;
}

/// Espelha `ImportFailure` em `backend/app/schemas/imports.py`.
class ImportFailure {
  final String code;
  final String message;

  ImportFailure({required this.code, required this.message});

  factory ImportFailure.fromJson(Map<String, dynamic> json) {
    return ImportFailure(code: json['code'] as String, message: json['message'] as String);
  }
}

/// Espelha `ImportOut` em `backend/app/schemas/imports.py`.
class ImportOut {
  final String id;
  final String url;
  final String youtubeId;
  final ImportStatus status;
  final String? recipeId;
  final ImportFailure? error;
  final int? queuePosition;
  final DateTime createdAt;
  final DateTime updatedAt;

  ImportOut({
    required this.id,
    required this.url,
    required this.youtubeId,
    required this.status,
    this.recipeId,
    this.error,
    this.queuePosition,
    required this.createdAt,
    required this.updatedAt,
  });

  factory ImportOut.fromJson(Map<String, dynamic> json) {
    return ImportOut(
      id: json['id'] as String,
      url: json['url'] as String,
      youtubeId: json['youtube_id'] as String,
      status: ImportStatus.fromJson(json['status'] as String),
      recipeId: json['recipe_id'] as String?,
      error: json['error'] != null
          ? ImportFailure.fromJson((json['error'] as Map).cast<String, dynamic>())
          : null,
      queuePosition: json['queue_position'] as int?,
      createdAt: DateTime.parse(json['created_at'] as String),
      updatedAt: DateTime.parse(json['updated_at'] as String),
    );
  }
}

/// Etapas mostradas no progresso, na ordem em que o worker passa por elas —
/// espelha `IMPORT_STAGES` em `frontend/src/lib/importStatus.ts`.
const List<({ImportStatus status, String label})> importStages = [
  (status: ImportStatus.fetching, label: 'Buscando vídeo'),
  (status: ImportStatus.transcribing, label: 'Transcrevendo'),
  (status: ImportStatus.generating, label: 'Escrevendo a receita'),
];

/// Frase curta do momento atual — espelha `statusAnnouncement` em
/// `frontend/src/lib/importStatus.ts`.
String importStatusAnnouncement(ImportOut imp) {
  switch (imp.status) {
    case ImportStatus.pending:
      return imp.queuePosition != null
          ? 'Na fila: ${imp.queuePosition}º lugar.'
          : 'Na fila, começando em instantes.';
    case ImportStatus.fetching:
      return 'Buscando o vídeo no YouTube.';
    case ImportStatus.transcribing:
      return imp.queuePosition != null
          ? 'Aguardando a transcrição: ${imp.queuePosition}º na fila.'
          : 'Transcrevendo o vídeo.';
    case ImportStatus.generating:
      return 'Escrevendo a receita.';
    case ImportStatus.deferred:
      return 'Importação adiada.';
    case ImportStatus.done:
      return 'Receita pronta!';
    case ImportStatus.failed:
      return 'Não foi possível importar esse vídeo.';
  }
}

enum StageState { done, current, upcoming }

/// Estado de cada etapa de `importStages` para o status atual — espelha `stageStates`
/// em `frontend/src/lib/importStatus.ts`.
List<StageState> importStageStates(ImportStatus status) {
  if (status == ImportStatus.done) {
    return List.filled(importStages.length, StageState.done);
  }
  final currentIndex = importStages.indexWhere((stage) => stage.status == status);
  if (currentIndex == -1) {
    return List.filled(importStages.length, StageState.upcoming);
  }
  return List.generate(importStages.length, (i) {
    if (i < currentIndex) return StageState.done;
    if (i == currentIndex) return StageState.current;
    return StageState.upcoming;
  });
}

/// Intervalo do polling de `GET /imports/{id}`, em ms, ou `null` para parar —
/// espelha `pollInterval` em `frontend/src/lib/importStatus.ts`.
int? importPollIntervalMs(ImportOut? imp, Duration elapsed) {
  if (imp == null) return 1000;
  if (imp.status.isTerminal) return null;
  if (imp.status == ImportStatus.deferred) return 60000;
  if (imp.queuePosition != null && imp.queuePosition! > 5) return 10000;
  final elapsedMs = elapsed.inMilliseconds;
  if (elapsedMs < 15000) return 1000;
  if (elapsedMs < 60000) return 2000;
  if (elapsedMs < 5 * 60000) return 5000;
  return 10000;
}
