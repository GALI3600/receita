# shellcheck shell=bash
# Funções comuns dos scripts de operação (incluído com "source"; não é executável sozinho).
#
# ENV_FILE: arquivo de variáveis do stack (padrão .env.production, na raiz do repositório).
# COMPOSE_FILES: arquivos do Compose separados por ":" (padrão docker-compose.prod.yml).

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT_DIR" || exit 1

ENV_FILE=${ENV_FILE:-.env.production}
COMPOSE_FILES=${COMPOSE_FILES:-docker-compose.prod.yml}

if [[ ! -f "$ENV_FILE" ]]; then
  echo "erro: $ENV_FILE não existe (defina ENV_FILE)" >&2
  exit 1
fi

# Valor de uma variável do ENV_FILE (sem "source": o arquivo tem JSON e "<" nos valores).
env_value() {
  grep -E "^$1=" "$ENV_FILE" | tail -n 1 | cut -d= -f2- || true
}

compose() {
  local args=() file
  IFS=: read -r -a files <<<"$COMPOSE_FILES"
  for file in "${files[@]}"; do
    args+=(-f "$file")
  done
  docker compose "${args[@]}" --env-file "$ENV_FILE" "$@"
}

log() {
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"
}
