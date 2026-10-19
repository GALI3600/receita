import 'package:cookie_jar/cookie_jar.dart';
import 'package:dio/dio.dart';
import 'package:dio_cookie_manager/dio_cookie_manager.dart';
import 'package:path_provider/path_provider.dart';

import 'api_exception.dart';
import 'env.dart';

/// Header anti-CSRF exigido pelo backend em todo pedido que muda estado,
/// espelhando `CSRF_HEADER` de `frontend/src/api/client.ts`.
const String csrfHeader = 'X-Requested-With';
const String csrfHeaderValue = 'XMLHttpRequest';

const Set<String> _mutatingMethods = {'POST', 'PUT', 'PATCH', 'DELETE'};

/// Monta o cliente Dio único do app: cookie de sessão persistente (equivalente ao
/// `credentials: 'same-origin'` do browser) + header CSRF nas mutações + erros tipados.
Future<Dio> buildApiClient() async {
  final dio = Dio(
    BaseOptions(
      baseUrl: apiBaseUrl,
      headers: const {'Accept': 'application/json'},
    ),
  );

  final appDocDir = await getApplicationDocumentsDirectory();
  final cookieJar = PersistCookieJar(storage: FileStorage('${appDocDir.path}/.cookies/'));
  dio.interceptors.add(CookieManager(cookieJar));

  dio.interceptors.add(
    InterceptorsWrapper(
      onRequest: (options, handler) {
        if (_mutatingMethods.contains(options.method.toUpperCase())) {
          options.headers[csrfHeader] = csrfHeaderValue;
        }
        handler.next(options);
      },
      onError: (error, handler) {
        handler.next(DioException(
          requestOptions: error.requestOptions,
          response: error.response,
          type: error.type,
          error: ApiException.fromDioException(error),
        ));
      },
    ),
  );

  return dio;
}
