/// URL base da API, definida em tempo de build via `--dart-define=API_BASE_URL=...`.
///
/// Dev: aponta para a porta 8005 da VM de projetos (remapeada pelo
/// `docker-compose.override.yml` do repo, já que a porta 8000 é usada pelo Portainer
/// nesta VM). Produção: deve ser a URL absoluta do domínio real + `/api` — o Caddy não
/// expõe a API numa porta própria em produção, diferente da web que usa `/api` relativo.
const String apiBaseUrl = String.fromEnvironment(
  'API_BASE_URL',
  defaultValue: 'http://10.10.10.10:8005/api',
);
