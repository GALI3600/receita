import 'package:dio/dio.dart';

import '../api/api_exception.dart';
import '../models/me.dart';

/// Espelha `authApi` em `frontend/src/api/endpoints.ts` e as rotas de
/// `backend/app/api/auth.py`.
class AuthRepository {
  final Dio _dio;
  AuthRepository(this._dio);

  Future<String> register({
    required String name,
    required String email,
    required String password,
    String? turnstileToken,
  }) async {
    try {
      final response = await _dio.post('/auth/register', data: {
        'name': name,
        'email': email,
        'password': password,
        'cf-turnstile-response': ?turnstileToken,
      });
      return response.data['message'] as String;
    } on DioException catch (e) {
      throw apiExceptionFrom(e);
    }
  }

  Future<Me> login({required String email, required String password}) async {
    try {
      final response = await _dio.post('/auth/login', data: {
        'email': email,
        'password': password,
      });
      return Me.fromJson((response.data as Map).cast<String, dynamic>());
    } on DioException catch (e) {
      throw apiExceptionFrom(e);
    }
  }

  Future<void> logout() async {
    try {
      await _dio.post('/auth/logout');
    } on DioException catch (e) {
      throw apiExceptionFrom(e);
    }
  }

  Future<Me> me() async {
    try {
      final response = await _dio.get('/auth/me');
      return Me.fromJson((response.data as Map).cast<String, dynamic>());
    } on DioException catch (e) {
      throw apiExceptionFrom(e);
    }
  }

  Future<void> verifyEmail(String token) async {
    try {
      await _dio.post('/auth/verify', data: {'token': token});
    } on DioException catch (e) {
      throw apiExceptionFrom(e);
    }
  }

  Future<String> forgotPassword(String email) async {
    try {
      final response = await _dio.post('/auth/forgot-password', data: {'email': email});
      return response.data['message'] as String;
    } on DioException catch (e) {
      throw apiExceptionFrom(e);
    }
  }

  Future<void> resetPassword({required String token, required String password}) async {
    try {
      await _dio.post('/auth/reset-password', data: {'token': token, 'password': password});
    } on DioException catch (e) {
      throw apiExceptionFrom(e);
    }
  }

  Future<String> resendVerification(String email) async {
    try {
      final response = await _dio.post('/auth/resend-verification', data: {'email': email});
      return response.data['message'] as String;
    } on DioException catch (e) {
      throw apiExceptionFrom(e);
    }
  }
}
