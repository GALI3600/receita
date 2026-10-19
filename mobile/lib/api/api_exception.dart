import 'dart:io';

import 'package:dio/dio.dart';

import '../models/error_response.dart';

const Map<int, String> _fallbackMessages = {
  401: 'Entre na sua conta para continuar.',
  403: 'Você não tem permissão para fazer isso.',
  404: 'Não encontramos o que você procurou.',
  429: 'Muitas tentativas em pouco tempo. Espere um pouco e tente de novo.',
};

const String _networkErrorMessage =
    'Não conseguimos falar com o servidor. Confira sua conexão e tente de novo.';

/// Erro da API no formato padrão `{"error": {"code", "message", "details?"}}`,
/// espelhando `ApiError`/`toApiError`/`parseRetryAfter` de `frontend/src/api/client.ts`.
class ApiException implements Exception {
  final int status;
  final String code;
  final String message;
  final List<FieldError>? details;
  final int? retryAfterSeconds;

  ApiException(
    this.status,
    this.code,
    this.message, {
    this.details,
    this.retryAfterSeconds,
  });

  bool get isUnauthorized => status == 401;
  bool get isNetworkError => code == 'network_error';

  factory ApiException.fromDioException(DioException error) {
    final response = error.response;
    if (response == null) {
      return ApiException(0, 'network_error', _networkErrorMessage);
    }

    final retryAfter = _parseRetryAfter(response.headers.value('retry-after'));
    final status = response.statusCode ?? 0;
    final body = response.data;

    if (body is Map && body['error'] is Map) {
      final errorBody = ErrorBody.fromJson((body['error'] as Map).cast<String, dynamic>());
      return ApiException(
        status,
        errorBody.code,
        errorBody.message,
        details: errorBody.details,
        retryAfterSeconds: retryAfter,
      );
    }

    final fallback = _fallbackMessages[status] ??
        (status >= 500
            ? 'O servidor está com problemas. Tente de novo em alguns minutos.'
            : 'Não foi possível atender o pedido.');
    return ApiException(status, 'http_$status', fallback, retryAfterSeconds: retryAfter);
  }

  static int? _parseRetryAfter(String? value) {
    if (value == null) return null;
    final trimmed = value.trim();
    if (trimmed.isEmpty) return null;
    final asInt = int.tryParse(trimmed);
    if (asInt != null) return asInt;
    try {
      final date = HttpDate.parse(trimmed);
      final diff = date.difference(DateTime.now()).inSeconds;
      return diff < 0 ? 0 : diff;
    } catch (_) {
      return null;
    }
  }

  @override
  String toString() => 'ApiException(status: $status, code: $code, message: $message)';
}

/// O interceptor de erro do Dio já converte toda `DioException` numa que carrega uma
/// `ApiException` em `.error`; isso só extrai (ou monta, de fallback) a exceção tipada.
ApiException apiExceptionFrom(DioException error) {
  final wrapped = error.error;
  return wrapped is ApiException ? wrapped : ApiException.fromDioException(error);
}
