# Receita Mobile (Flutter, Android)

App Android nativo do Receita, consumindo a mesma API do backend (`../backend`) usada
pelo frontend web (`../frontend`). Paridade de funcionalidades com a web, com uma
diferença intencional: a tela de receita mostra o conteúdo no estilo "página de livro"
(igual à visão de impressão da web) — sem player de vídeo e sem os chips de timestamp.

## Stack

- Flutter 3.44.7 / Dart 3.12.2 (SDK já instalado na VM de projetos em
  `/home/serverapp/flutter`, fora do `PATH` — invocar pelo caminho completo).
- Riverpod (`flutter_riverpod`) para estado, `go_router` para navegação.
- `dio` + `dio_cookie_manager` + `cookie_jar` para o cliente HTTP: a API usa cookie de
  sessão httpOnly (`receita_session`), não Bearer token, então o cookie precisa
  persistir em disco entre reinícios do app, igual a um cookie de navegador.
- Modelos de dados escritos à mão (sem `freezed`/`json_serializable`), espelhando os
  schemas Pydantic do backend campo a campo.

## Configuração da API

A URL base é definida em tempo de build via `--dart-define=API_BASE_URL=...`
(`lib/api/env.dart`). Sem isso, usa o padrão de desenvolvimento:
`http://10.10.10.10:8005/api` (porta 8005 porque a 8000 é do Portainer nesta VM —
ver `docker-compose.override.yml` na raiz do repo).

```bash
# Dev, contra a API da VM de projetos:
flutter run --dart-define=API_BASE_URL=http://10.10.10.10:8005/api

# Produção, contra o domínio real (o Caddy só expõe /api sob HTTPS, sem porta própria):
flutter build apk --release --dart-define=API_BASE_URL=https://<dominio>/api
```

## Setup e verificação

```bash
flutter pub get
flutter analyze
flutter test
```

### Limitação conhecida: sem build de APK nesta VM

Esta VM (Linux) não tem Android SDK nem JDK instalados — só o Flutter SDK. Isso é
suficiente para `pub get`, `analyze` e `test` (que correm na Dart VM, sem precisar de
toolchain Android), mas `flutter build apk`/`flutter run` em um dispositivo Android
vão falhar no passo do Gradle por falta do SDK.

Para gerar um APK de fato, uma das opções:
1. Instalar JDK + Android SDK nesta VM (`sdkmanager "platform-tools" "platforms;android-34" "build-tools;34.0.0"`).
2. Puxar esta branch numa máquina com Android Studio já configurado.
3. Configurar CI (ex.: GitHub Actions com `subosito/flutter-action`).

## Pontos abertos

- **Cadastro com Cloudflare Turnstile**: se `TURNSTILE_SECRET_KEY` estiver configurado
  no backend em produção, o cadastro exige um token do widget Turnstile
  (`cf-turnstile-response`). A tela de cadastro tem um campo opcional para colar esse
  token manualmente; não há (ainda) um WebView embutindo o widget.
- **Verificação de e-mail / redefinição de senha**: sem deep link configurado, o
  usuário cola manualmente o código recebido por e-mail em vez de abrir um link direto.
- **`applicationId`**: `com.receita.app`, assumido (não há domínio/Play Console
  registrado conhecido). Trocar depois exige editar `android/app/build.gradle.kts` e a
  estrutura de pastas Kotlin.
