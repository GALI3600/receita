import 'package:dio/dio.dart';

import '../api/api_exception.dart';
import '../models/import_out.dart';

/// Espelha `importsApi` em `frontend/src/api/endpoints.ts` e as rotas de
/// `backend/app/api/imports.py`.
class ImportsRepository {
  final Dio _dio;
  ImportsRepository(this._dio);

  Future<ImportOut> submit(String url) async {
    try {
      final response = await _dio.post('/imports', data: {'url': url});
      return ImportOut.fromJson((response.data as Map).cast<String, dynamic>());
    } on DioException catch (e) {
      throw apiExceptionFrom(e);
    }
  }

  Future<ImportOut> get(String id) async {
    try {
      final response = await _dio.get('/imports/$id');
      return ImportOut.fromJson((response.data as Map).cast<String, dynamic>());
    } on DioException catch (e) {
      throw apiExceptionFrom(e);
    }
  }
}
